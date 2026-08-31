"""Integration smoke tests for the distributed backend.

These assume the full system is already running (Redis, coordinator,
zone_a/b/c, gateway) — start it with scripts/start_all.ps1 first, e.g.:

    pytest tests/test_integration.py -v

They talk to the real services over gRPC / HTTP / Redis, the same way
the coordinator, gateway and browser do, rather than mocking anything.
"""

import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import httpx
import pytest

import config
from communication.grpc.grpc_client import coordinator_stub, zone_stub
from communication.grpc import parking_pb2
from communication.messaging.message_bus import read_recent_events

GATEWAY_URL = f"http://{config.HOST}:{config.GATEWAY_PORT}"


@pytest.fixture(scope="module")
def coord():
    return coordinator_stub(config.HOST, config.COORDINATOR_GRPC_PORT)


def test_node_registration(coord):
    resp = coord.GetSystemStatus(parking_pb2.SystemStatusRequest(), timeout=5)
    node_ids = {n.node_id for n in resp.nodes}
    assert {"ZONE_A", "ZONE_B", "ZONE_C"}.issubset(node_ids)


def test_rpc_get_available_slots():
    stub = zone_stub(config.HOST, config.ZONES["A"]["port"])
    resp = stub.GetAvailableSlots(parking_pb2.AvailableSlotsRequest(), timeout=5)
    assert resp.available_count >= 0
    assert len(resp.slot_ids) == resp.available_count


def test_reservation_and_release_roundtrip(coord):
    find_resp = coord.FindParking(parking_pb2.FindParkingRequest(), timeout=5)
    assert find_resp.success
    assert find_resp.reservation_id.startswith("RES-")

    release_resp = coord.ReleaseParking(
        parking_pb2.ReleaseParkingRequest(reservation_id=find_resp.reservation_id), timeout=5
    )
    assert release_resp.success


def test_redis_event_published(coord):
    coord.FindParking(parking_pb2.FindParkingRequest(), timeout=5)
    time.sleep(0.3)
    events = read_recent_events(10)
    event_types = [e["event"] for e in events]
    assert "PARKING_REQUESTED" in event_types


def test_p2p_capacity_query():
    from communication.p2p.p2p_client import send_p2p_message
    reply = send_p2p_message(config.HOST, config.ZONES["A"]["p2p_port"], "CAPACITY_REQUEST")
    assert reply is not None
    assert reply.startswith("AVAILABLE_SLOTS=")


def test_gateway_health():
    resp = httpx.get(f"{GATEWAY_URL}/health", timeout=5)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_gateway_system_status():
    resp = httpx.get(f"{GATEWAY_URL}/api/system/status", timeout=5)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["zones"]) == 3


def test_fault_tolerance_fail_and_recover():
    # Fail Zone C, confirm it is dropped from allocation, then recover it.
    fail_resp = httpx.post(
        f"{GATEWAY_URL}/api/admin/zone/C/failure", json={"simulate_failure": True}, timeout=5
    )
    assert fail_resp.json()["success"]

    time.sleep(config.HEARTBEAT_TIMEOUT_SEC + 2)

    status = httpx.get(f"{GATEWAY_URL}/api/system/status", timeout=5).json()
    zone_c = next(z for z in status["zones"] if z["node_id"] == "ZONE_C")
    assert zone_c["status"] == "OFFLINE"

    recover_resp = httpx.post(
        f"{GATEWAY_URL}/api/admin/zone/C/failure", json={"simulate_failure": False}, timeout=5
    )
    assert recover_resp.json()["success"]

    time.sleep(2)
    status = httpx.get(f"{GATEWAY_URL}/api/system/status", timeout=5).json()
    zone_c = next(z for z in status["zones"] if z["node_id"] == "ZONE_C")
    assert zone_c["status"] == "ONLINE"
