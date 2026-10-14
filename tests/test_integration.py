"""End-to-end tests against the running system (FA-1 + FA-2 features).

Start the stack first, either locally:
    python scripts/run_local.py
or with Docker:
    docker compose up --build -d
then:
    pytest tests/test_integration.py -v

The tests talk to the real gateway / coordinators / zones over HTTP and gRPC,
exactly like the browser does; nothing is mocked. They leave the system as they
found it (reservations are released, failed nodes recovered).
"""

import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import httpx
import pytest

import config
from communication.messaging.message_bus import read_recent_events

GATEWAY_URL = os.environ.get("GATEWAY_URL", f"http://localhost:{config.GATEWAY_PORT}")
client = httpx.Client(base_url=GATEWAY_URL, timeout=60)


def _wait(predicate, timeout=20.0, interval=0.5):
    end = time.time() + timeout
    while time.time() < end:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    return None


@pytest.fixture(scope="module", autouse=True)
def stack_is_up():
    try:
        client.get("/api/whoami")
    except httpx.HTTPError:
        pytest.skip("system is not running - start it with scripts/run_local.py or docker compose up")
    assert _wait(lambda: client.get("/api/coordinators").json()["leader"]), "no coordinator leader elected"
    assert _wait(lambda: len(client.get("/api/system/status").json()["zones"]) == 3), "zones did not register"


# ------------------------------------------------------------------ FA-1 behaviour

def test_gateway_is_reachable():
    body = client.get("/api/whoami").json()  # /api/* works both direct and through the Nginx entry point
    assert body["gateway"]


def test_zones_registered_with_leader():
    status = client.get("/api/system/status").json()
    assert {z["node_id"] for z in status["zones"]} == {"ZONE_A", "ZONE_B", "ZONE_C"}
    assert status["leader_id"] in config.COORDINATORS


def test_reserve_and_release_roundtrip():
    found = client.post("/api/parking/find").json()
    assert found["success"], found
    assert found["reservation_id"].startswith("RES-")
    assert found["price_per_hour"] > 0 and found["receipt"]
    released = client.post("/api/parking/release", json={"reservation_id": found["reservation_id"]}).json()
    assert released["success"]
    again = client.post("/api/parking/release", json={"reservation_id": found["reservation_id"]}).json()
    assert not again["success"]  # releasing twice is refused


def test_p2p_capacity_query():
    from communication.p2p.p2p_client import send_p2p_message
    cfg = config.ZONES["A"]
    reply = send_p2p_message("localhost", cfg["p2p_port"], "CAPACITY_REQUEST")
    if reply is None:
        pytest.skip("P2P TCP port is not reachable from the host (containerised run)")
    assert reply.startswith("AVAILABLE_SLOTS=")


def test_events_are_stamped_with_lamport_timestamps():
    client.post("/api/parking/find")
    time.sleep(0.5)
    stamped = [e for e in read_recent_events(30) if "lamport" in e]
    assert stamped, "no event carried a Lamport timestamp"
    assert all(isinstance(e["lamport"], int) and e["lamport"] > 0 for e in stamped)


# ------------------------------------------------------- Unit 3: mutual exclusion

def test_mutual_exclusion_prevents_overbooking():
    unsafe = client.post("/api/demo/mutex", params={"use_mutex": "false"}).json()
    assert unsafe["overbooked"] and unsafe["lost_update"] and unsafe["any_overlap"]

    safe = client.post("/api/demo/mutex", params={"use_mutex": "true"}).json()
    assert safe["accepted"] == safe["capacity"] and not safe["overbooked"]
    assert not safe["lost_update"] and not safe["any_overlap"]
    assert all(r["request_ts"] > 0 for r in safe["results"])  # every zone sent a Lamport-stamped REQUEST

    lot = client.get("/api/overflow").json()  # the demo leaves the real lot empty at full capacity
    assert lot["free"] == config.OVERFLOW_CAPACITY and lot["bookings"] == {}


def test_full_zones_fall_back_to_overflow_lot():
    reserved = []
    try:
        for _ in range(sum(z["total_slots"] for z in config.ZONES.values()) + 1):
            r = client.post("/api/parking/find").json()
            assert r["success"], r
            reserved.append(r["reservation_id"])
            if r["zone_id"] == "OVERFLOW":
                break
        assert r["zone_id"] == "OVERFLOW" and r["reservation_id"].startswith("RES-OVF-")

        lot = client.get("/api/overflow").json()
        assert lot["free"] == config.OVERFLOW_CAPACITY - 1 and r["reservation_id"] in lot["bookings"]
    finally:
        for rid in reserved:
            client.post("/api/parking/release", json={"reservation_id": rid})

    lot = client.get("/api/overflow").json()
    assert lot["free"] == config.OVERFLOW_CAPACITY and lot["bookings"] == {}


# ------------------------------------------------------------------ Unit 3: election

def test_leader_failover_and_recovery():
    info = client.get("/api/coordinators").json()
    old_leader, old_term = info["leader_id"], info["term"]

    client.post(f"/api/admin/coordinator/{old_leader}/failure", json={"simulate_failure": True})
    try:
        new = _wait(lambda: (lambda d: d if d["leader_id"] not in (None, old_leader) else None)(client.get("/api/coordinators").json()), timeout=25)
        assert new, "no new leader elected after the leader failed"
        assert new["term"] > old_term

        found = _wait(lambda: (lambda r: r if r["success"] else None)(client.post("/api/parking/find").json()), timeout=15)
        assert found, "parking requests did not resume under the new leader"
        client.post("/api/parking/release", json={"reservation_id": found["reservation_id"]})
    finally:
        client.post(f"/api/admin/coordinator/{old_leader}/failure", json={"simulate_failure": False})

    # Bully: the recovered highest-id node takes leadership back
    back = _wait(lambda: (lambda d: d if d["leader_id"] == max(config.COORDINATORS) else None)(client.get("/api/coordinators").json()), timeout=25)
    assert back and back["term"] > new["term"]


# -------------------------------------------------------- Unit 2/3: zone fault tolerance

def test_zone_failure_is_detected_and_service_continues():
    client.post("/api/admin/zone/C/failure", json={"simulate_failure": True})
    try:
        offline = _wait(lambda: next((z for z in client.get("/api/system/status").json()["zones"]
                                      if z["node_id"] == "ZONE_C" and z["status"] == "OFFLINE"), None),
                        timeout=config.HEARTBEAT_TIMEOUT_SEC + 8)
        assert offline, "leader did not mark ZONE_C offline"

        found = client.post("/api/parking/find").json()  # the other zones keep serving
        assert found["success"] and found["zone_id"] != "PARKING_C"
        client.post("/api/parking/release", json={"reservation_id": found["reservation_id"]})
    finally:
        client.post("/api/admin/zone/C/failure", json={"simulate_failure": False})

    assert _wait(lambda: next((z for z in client.get("/api/system/status").json()["zones"]
                               if z["node_id"] == "ZONE_C" and z["status"] == "ONLINE"), None), timeout=15)


# ---------------------------------------------------------------- load balancing

def test_allocation_policies_differ():
    reserved = []
    try:
        zones = {}
        for policy in ("first_fit", "least_loaded"):
            chosen = []
            for _ in range(6):
                r = client.post("/api/parking/find", params={"policy": policy}).json()
                assert r["success"] and r["policy"] == policy
                reserved.append(r["reservation_id"])
                chosen.append(r["zone_id"])
            zones[policy] = chosen
        assert len(set(zones["first_fit"])) == 1                  # first-fit keeps hitting the same zone
        assert len(set(zones["least_loaded"])) >= 2               # least-loaded spreads out
    finally:
        for rid in reserved:
            client.post("/api/parking/release", json={"reservation_id": rid})


# ------------------------------------------------------------- serverless / MapReduce

def test_serverless_function_cold_then_warm():
    client.post("/api/faas/evict/pricing")
    first = client.post("/api/faas/invoke/pricing", json={"occupancy": 0.9, "hour": 9, "zone": "A"}).json()
    second = client.post("/api/faas/invoke/pricing", json={"occupancy": 0.9, "hour": 9, "zone": "A"}).json()
    assert first["cold_start"] and not second["cold_start"]
    assert first["duration_ms"] > second["duration_ms"]
    assert second["result"]["price_per_hour"] == round(20 * 1.5 * 1.1, 2)  # surge + peak hour


def test_mapreduce_job_runs_and_combiner_shrinks_shuffle():
    out = client.post("/api/analytics/run", params={"job": "peak_hours", "n": 50000, "workers": 3}).json()
    assert "error" not in out, out
    stats = out["stats"]
    assert stats["input_records"] == 50000 and stats["map_tasks"] == 3
    assert stats["pairs_shuffled_after_combiner"] < stats["pairs_emitted_by_mappers"] / 10
    assert sum(sum(z["histogram"]) for z in out["result"].values()) == 50000
