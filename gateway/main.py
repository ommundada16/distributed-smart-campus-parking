"""API Gateway: the only HTTP-facing service. Bridges the React client to the
distributed backend (gRPC to the coordinator leader and zones, WebSocket to the browser).

Several gateway instances run behind the Nginx load balancer, so a gateway holds
no state of its own: it finds the current coordinator leader on demand
(communication.discovery) and keeps shared settings in Redis.

Run standalone:
    python -m gateway.main
"""

import sys
import os
import asyncio
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import grpc
import httpx
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import config
from communication.discovery import LeaderLocator, NoLeaderError
from communication.grpc import parking_pb2
from communication.grpc.grpc_client import replica_stub, zone_stub_for
from communication.messaging.message_bus import consume_events, get_redis_client, publish_event, read_recent_events
from communication.websocket.websocket_manager import manager
from distributed.clocks import compare_vc, decode_vc

app = FastAPI(title="Distributed Smart Campus Parking System - API Gateway")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

locator = LeaderLocator()
_http = httpx.Client(timeout=5.0)  # shared: a fresh httpx client per call costs ~150 ms


@app.middleware("http")
async def tag_response(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Served-By"] = config.GATEWAY_NAME  # which gateway replica answered (load-balancing demo)
    return response


def _error(exc: Exception) -> dict:
    if isinstance(exc, grpc.RpcError):
        return {"success": False, "message": f"{exc.code().name}: {exc.details()}"}
    return {"success": False, "message": str(exc)}


def _leader_call(method: str, request, timeout: float = 6.0, attempts: int = 3):
    return locator.call(method, request, timeout=timeout, attempts=attempts)


def _parallel(fn, items):
    items = list(items)
    if not items:
        return []
    with ThreadPoolExecutor(max_workers=len(items)) as pool:
        return list(pool.map(fn, items))


# ----------------------------------------------------------------------------- basics

@app.get("/health")
def health():
    return {"status": "ok", "service": "api-gateway", "gateway": config.GATEWAY_NAME, "port": config.GATEWAY_PORT}


@app.get("/api/whoami")
def whoami():
    return {"gateway": config.GATEWAY_NAME, "cached_leader": locator.cached}


# --------------------------------------------------------------------------- parking

@app.post("/api/parking/find")
def find_parking(policy: str = ""):
    try:
        resp = _leader_call("FindParking", parking_pb2.FindParkingRequest(policy=policy))
    except Exception as exc:
        return _error(exc)
    out = {
        "success": resp.success, "zone_id": resp.zone_id, "node_id": resp.node_id, "slot_id": resp.slot_id,
        "reservation_id": resp.reservation_id, "message": resp.message, "price_per_hour": resp.price_per_hour,
        "price_source": resp.price_source, "ledger_block": resp.ledger_block, "policy": resp.policy,
        "served_by_coordinator": resp.served_by, "gateway": config.GATEWAY_NAME, "lamport": resp.lamport,
    }
    if resp.success:  # receipt from the second serverless function (best effort)
        try:
            r = _http.post(f"{config.FAAS_URL}/invoke/receipt", timeout=1.5, json={
                "reservation_id": resp.reservation_id, "slot_id": resp.slot_id,
                "price_per_hour": resp.price_per_hour, "ledger_block": resp.ledger_block,
            })
            out["receipt"] = r.json()["result"]["receipt_no"]
        except Exception:
            out["receipt"] = None
    return out


class ReleaseRequest(BaseModel):
    reservation_id: str


@app.post("/api/parking/release")
def release_parking(body: ReleaseRequest):
    try:
        resp = _leader_call("ReleaseParking", parking_pb2.ReleaseParkingRequest(reservation_id=body.reservation_id))
    except Exception as exc:
        return _error(exc)
    return {"success": resp.success, "message": resp.message}


# ---------------------------------------------------------------- coordinators / status

def _replica_info(coord_id: int) -> dict:
    cfg = config.COORDINATORS[coord_id]
    base = {"id": coord_id, "node_id": cfg["node_id"], "host": cfg["host"], "port": cfg["port"]}
    try:
        info = replica_stub(coord_id).WhoIsLeader(parking_pb2.Empty(), timeout=1.0)
    except grpc.RpcError:
        return {**base, "state": "DOWN", "role": "DOWN", "leader_id": 0, "term": 0}
    if info.state == "FAILING":
        return {**base, "state": "FAILING", "role": "FAILING", "leader_id": 0, "term": info.term}
    role = "LEADER" if info.leader_id == coord_id else ("FOLLOWER" if info.leader_id else "ELECTING")
    return {**base, "state": "UP", "role": role, "leader_id": info.leader_id, "term": info.term}


@app.get("/api/coordinators")
def coordinators():
    replicas = _parallel(_replica_info, config.coordinator_ids())
    leaders = [r for r in replicas if r["role"] == "LEADER"]
    best = max(leaders, key=lambda r: r["term"]) if leaders else None
    return {"replicas": replicas, "leader": best["node_id"] if best else None, "leader_id": best["id"] if best else None,
            "term": best["term"] if best else None, "gateway": config.GATEWAY_NAME}


class FailureRequest(BaseModel):
    simulate_failure: bool


@app.post("/api/admin/coordinator/{coord_id}/failure")
def set_coordinator_failure(coord_id: int, body: FailureRequest):
    if coord_id not in config.COORDINATORS:
        return {"success": False, "message": "Unknown coordinator"}
    try:
        resp = replica_stub(coord_id).SetFailureMode(parking_pb2.SetFailureModeRequest(simulate_failure=body.simulate_failure), timeout=3)
    except grpc.RpcError as exc:
        return _error(exc)
    locator._leader_id = None
    return {"success": resp.success, "status": resp.status}


def _http_health(url: str) -> str:
    try:
        return "ONLINE" if _http.get(url + "/health", timeout=1.0).status_code == 200 else "OFFLINE"
    except Exception:
        return "OFFLINE"


@app.get("/api/system/status")
def system_status():
    replicas = _parallel(_replica_info, config.coordinator_ids())
    services = [{
        "service": f"Coordinator {r['id']}", "node_id": r["node_id"], "port": r["port"], "host": r["host"],
        "status": "ONLINE" if r["state"] == "UP" else "OFFLINE", "role": r["role"], "term": r["term"],
    } for r in replicas]
    services.append({"service": "API Gateway", "node_id": config.GATEWAY_NAME, "port": config.GATEWAY_PORT, "host": config.GATEWAY_NAME,
                     "status": "ONLINE", "role": "gateway"})

    def probe_http(item):
        name, url = item
        return {"service": name, "node_id": name.upper().replace(" ", "_"), "port": int(url.rsplit(":", 1)[1]),
                "host": url.split("//")[1].split(":")[0], "status": _http_health(url), "role": "serverless" if "FaaS" in name else "batch"}

    services += _parallel(probe_http, [("FaaS runtime", config.FAAS_URL), ("Analytics", config.ANALYTICS_URL)])
    try:
        get_redis_client().ping()
        redis_status = "ONLINE"
    except Exception:
        redis_status = "OFFLINE"
    services.append({"service": "Redis", "node_id": "REDIS", "port": config.REDIS_PORT, "host": config.REDIS_HOST, "status": redis_status, "role": "message bus"})

    zones, leader_id, term = [], 0, 0
    try:
        resp = _leader_call("GetSystemStatus", parking_pb2.SystemStatusRequest(), timeout=3, attempts=1)
        leader_id, term = resp.leader_id, resp.term
        for node in resp.nodes:
            zones.append({
                "service": f"Zone {node.zone_id[-1]}", "node_id": node.node_id, "zone_id": node.zone_id,
                "host": node.host, "port": node.port, "status": node.status,
                "last_heartbeat": node.last_heartbeat, "total_slots": node.total_slots,
                "available_slots": node.available_slots, "occupied_slots": node.occupied_slots,
                "reserved_slots": node.reserved_slots, "flex_bays": node.flex_bays, "ledger_length": node.ledger_length,
            })
    except Exception:
        pass

    try:
        policy = get_redis_client().get(config.POLICY_KEY) or config.DEFAULT_POLICY
    except Exception:
        policy = config.DEFAULT_POLICY
    return {"services": services, "zones": sorted(zones, key=lambda z: z["node_id"]),
            "leader_id": leader_id, "term": term, "policy": policy, "gateway": config.GATEWAY_NAME}


@app.get("/api/edge/summary")
def edge_summary():
    """Public, read-only availability summary. Identical for every visitor, so the
    Nginx edge layer caches it for a few seconds (Cloudflare-style CDN caching)."""
    try:
        resp = _leader_call("GetSystemStatus", parking_pb2.SystemStatusRequest(), timeout=3, attempts=1)
    except Exception:
        return {"available": None, "zones": {}, "generated_at": time.time(), "generated_by": config.GATEWAY_NAME}
    zones = {n.zone_id: n.available_slots for n in resp.nodes if n.status == "ONLINE"}
    return {"available": sum(zones.values()), "zones": zones, "generated_at": time.time(), "generated_by": config.GATEWAY_NAME}


@app.get("/api/nodes")
def nodes_topology():
    """Deployment table: the declared topology (deploy/topology.json) joined with live status."""
    path = os.path.join(os.path.dirname(__file__), "..", "deploy", "topology.json")
    try:
        with open(path, encoding="utf-8") as f:
            topology = json.load(f)
    except OSError:
        topology = []
    return {"nodes": topology, "gateway": config.GATEWAY_NAME}


@app.get("/api/events/recent")
def recent_events(count: int = 40):
    return {"events": read_recent_events(count)}


@app.post("/api/admin/zone/{zone_key}/failure")
def set_zone_failure(zone_key: str, body: FailureRequest):
    zone_key = zone_key.upper()
    if zone_key not in config.ZONES:
        return {"success": False, "message": "Unknown zone"}
    try:
        resp = zone_stub_for(zone_key).SetFailureMode(parking_pb2.SetFailureModeRequest(simulate_failure=body.simulate_failure), timeout=3)
    except grpc.RpcError as exc:
        return _error(exc)
    return {"success": resp.success, "status": resp.status}


# ------------------------------------------------------------------ load balancing

class PolicyRequest(BaseModel):
    policy: str


@app.get("/api/policy")
def get_policy():
    try:
        value = get_redis_client().get(config.POLICY_KEY)
    except Exception:
        value = None
    return {"policy": value if value in config.POLICIES else config.DEFAULT_POLICY, "options": list(config.POLICIES)}


@app.post("/api/policy")
def set_policy(body: PolicyRequest):
    if body.policy not in config.POLICIES:
        raise HTTPException(400, f"policy must be one of {config.POLICIES}")
    get_redis_client().set(config.POLICY_KEY, body.policy)
    publish_event("POLICY_CHANGED", source="gateway", data={"policy": body.policy})
    return {"policy": body.policy}


def _run_policy_load(policy: str, n: int) -> dict:
    allocated, reservations, latencies = {}, [], []
    for _ in range(n):
        t0 = time.perf_counter()
        try:
            resp = _leader_call("FindParking", parking_pb2.FindParkingRequest(policy=policy), timeout=8, attempts=2)
        except Exception:
            continue
        latencies.append((time.perf_counter() - t0) * 1000)
        if resp.success:
            allocated[resp.zone_id] = allocated.get(resp.zone_id, 0) + 1
            reservations.append(resp.reservation_id)

    status = _leader_call("GetSystemStatus", parking_pb2.SystemStatusRequest(), timeout=4)
    occupancy = {}
    for node in status.nodes:
        used = node.total_slots - node.available_slots
        occupancy[node.zone_id] = round(100 * used / max(node.total_slots, 1), 1)
    values = list(occupancy.values())
    mean = sum(values) / len(values) if values else 0
    stddev = (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5 if values else 0

    for rid in reservations:  # put the system back the way it was
        try:
            _leader_call("ReleaseParking", parking_pb2.ReleaseParkingRequest(reservation_id=rid), timeout=6, attempts=2)
        except Exception:
            pass
    return {
        "policy": policy, "requests": n, "allocated": sum(allocated.values()), "per_zone": dict(sorted(allocated.items())),
        "occupancy_after_pct": dict(sorted(occupancy.items())), "imbalance_stddev": round(stddev, 2),
        "max_occupancy_pct": max(values) if values else 0, "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else None,
    }


@app.post("/api/loadtest/compare")
def loadtest_compare(n: int = 24):
    """Run the same burst of requests under every policy and compare the resulting balance."""
    n = max(1, min(n, 40))
    return {"results": [_run_policy_load(p, n) for p in config.POLICIES], "requests_each": n}


# ------------------------------------------------------------------------- clocks

def _clock_row(target):
    kind, key = target
    try:
        if kind == "zone":
            info = zone_stub_for(key).GetClockInfo(parking_pb2.Empty(), timeout=1.5)
        else:
            info = replica_stub(key).GetClockInfo(parking_pb2.Empty(), timeout=1.5)
    except grpc.RpcError:
        name = config.ZONES[key]["node_id"] if kind == "zone" else config.COORDINATORS[key]["node_id"]
        return {"node_id": name, "status": "OFFLINE"}
    return {"node_id": info.node_id, "status": "ONLINE", "lamport": info.lamport, "vclock": decode_vc(info.vclock_json),
            "physical_time": info.physical_time, "offset": info.offset}


@app.get("/api/clocks")
def clocks_state():
    targets = [("zone", k) for k in config.ZONES] + [("coord", i) for i in config.coordinator_ids()]
    rows = _parallel(_clock_row, targets)
    now = time.time()
    for r in rows:
        if r["status"] == "ONLINE":
            r["skew_vs_real_ms"] = round((r["physical_time"] - now) * 1000)
    return {"rows": rows, "real_time": now}


@app.post("/api/clocks/sync")
def clocks_sync():
    try:
        resp = _leader_call("SyncClocks", parking_pb2.Empty(), timeout=10)
    except Exception as exc:
        return _error(exc)
    return {"success": resp.success, "method": resp.method, "message": resp.message, "rows": [
        {"node_id": r.node_id, "offset_before_ms": round(r.offset_before * 1000, 1), "adjustment_ms": round(r.adjustment * 1000, 1),
         "offset_after_ms": round(r.offset_after * 1000, 1), "rtt_ms": round(r.rtt_ms, 2)} for r in resp.rows]}


@app.post("/api/clocks/skew")
def clocks_reskew():
    """Demo reset: put every node's clock back to its deliberate skew."""
    def apply(target):
        kind, key = target
        cfg = config.ZONES[key] if kind == "zone" else config.COORDINATORS[key]
        stub = zone_stub_for(key) if kind == "zone" else replica_stub(key)
        try:
            stub.AdjustClock(parking_pb2.AdjustClockRequest(delta=config.CLOCK_SKEW[cfg["node_id"]], absolute=True), timeout=2)
            return True
        except grpc.RpcError:
            return False

    ok = _parallel(apply, [("zone", k) for k in config.ZONES] + [("coord", i) for i in config.coordinator_ids()])
    return {"success": any(ok), "reset": sum(ok)}


# --------------------------------------------------------- mutual exclusion demo

@app.post("/api/demo/mutex")
def demo_mutex(use_mutex: bool = True, capacity: int = 2, hold_ms: int = 300):
    """Three zones try to take the last slots of the shared overflow lot at the same instant."""
    capacity = max(1, min(capacity, 2))
    r = get_redis_client()
    r.set(config.OVERFLOW_KEY, capacity)
    r.delete(config.OVERFLOW_BOOKINGS_KEY)
    run = f"run{int(time.time()) % 100000}"

    def book(key):
        try:
            return key, zone_stub_for(key).OverflowBook(
                parking_pb2.OverflowBookRequest(use_mutex=use_mutex, hold_ms=hold_ms, booking_id=run), timeout=60)
        except grpc.RpcError as exc:
            return key, exc

    results = dict(_parallel(book, list(config.ZONES)))
    rows = []
    for key, resp in results.items():
        if isinstance(resp, grpc.RpcError):
            rows.append({"node_id": config.ZONES[key]["node_id"], "error": f"{resp.code().name}"})
            continue
        rows.append({
            "node_id": resp.node_id, "success": resp.success, "message": resp.message, "saw_free": resp.saw_free,
            "lamport": resp.lamport, "vclock": decode_vc(resp.vclock_json),
            "entered_at": resp.entered_at, "exited_at": resp.exited_at, "trace": list(resp.trace),
        })

    good = [row for row in rows if "error" not in row]
    relations = []
    for i in range(len(good)):
        for j in range(i + 1, len(good)):
            a, b = good[i], good[j]
            overlap = min(a["exited_at"], b["exited_at"]) - max(a["entered_at"], b["entered_at"])
            relations.append({"a": a["node_id"], "b": b["node_id"], "relation": compare_vc(a["vclock"], b["vclock"]),
                              "overlap_ms": round(max(overlap, 0) * 1000)})

    accepted = sum(1 for row in good if row["success"])
    final_free = int(r.get(config.OVERFLOW_KEY) or 0)
    bookings = r.lrange(config.OVERFLOW_BOOKINGS_KEY, 0, -1)
    return {
        "use_mutex": use_mutex, "capacity": capacity, "accepted": accepted, "overbooked": accepted > capacity,
        "final_free_counter": final_free, "expected_free_counter": capacity - accepted,
        "lost_update": final_free != capacity - accepted, "bookings": bookings,
        "results": sorted(rows, key=lambda x: x["node_id"]), "relations": relations,
        "any_overlap": any(rel["overlap_ms"] > 0 for rel in relations),
    }


# --------------------------------------------------------------------- snapshot demo

@app.get("/api/flex")
def flex_state():
    def probe(key):
        try:
            st = zone_stub_for(key).GetZoneStatus(parking_pb2.ZoneStatusRequest(), timeout=1.5)
            return {"node_id": st.node_id, "flex_bays": st.flex_bays, "status": "ONLINE"}
        except grpc.RpcError:
            return {"node_id": config.ZONES[key]["node_id"], "flex_bays": None, "status": "OFFLINE"}
    rows = _parallel(probe, list(config.ZONES))
    return {"zones": rows, "total": sum(r["flex_bays"] or 0 for r in rows)}


@app.post("/api/demo/snapshot")
def demo_snapshot(amount: int = 3, delay_ms: int = 3000, src: str = "auto", dst: str = "auto", initiator: str = "A"):
    flex = {z["node_id"]: z["flex_bays"] for z in flex_state()["zones"]}
    if any(v is None for v in flex.values()):
        return {"success": False, "message": "all three zones must be online for the snapshot demo"}
    expected_total = sum(flex.values())
    by_node = {cfg["node_id"]: key for key, cfg in config.ZONES.items()}
    if src == "auto":
        src_node = max(flex, key=flex.get)
    else:
        src_node = config.ZONES[src.upper()]["node_id"]
    if dst == "auto":
        dst_node = min((n for n in flex if n != src_node), key=flex.get)
    else:
        dst_node = config.ZONES[dst.upper()]["node_id"]
    initiator_key = initiator.upper() if initiator.upper() in config.ZONES else "A"
    snapshot_id = f"SNAP-{int(time.time()) % 100000}"

    try:
        ack = zone_stub_for(by_node[src_node]).StartTransfer(
            parking_pb2.StartTransferRequest(to_node=dst_node, amount=amount, delay_ms=delay_ms), timeout=5)
    except grpc.RpcError as exc:
        return _error(exc)
    if not ack.success:
        return {"success": False, "message": ack.message}

    time.sleep(0.4)  # the transfer is now in flight
    naive = flex_state()
    try:
        zone_stub_for(initiator_key).StartSnapshot(parking_pb2.StartSnapshotRequest(snapshot_id=snapshot_id), timeout=5)
    except grpc.RpcError as exc:
        return _error(exc)

    deadline = time.time() + delay_ms / 1000.0 + 15
    snaps = {}
    while time.time() < deadline:
        snaps = {}
        for key in config.ZONES:
            try:
                snaps[key] = zone_stub_for(key).GetSnapshot(parking_pb2.GetSnapshotRequest(snapshot_id=snapshot_id), timeout=2)
            except grpc.RpcError:
                snaps[key] = None
        if all(s is not None and s.known and s.complete for s in snaps.values()):
            break
        time.sleep(0.3)

    nodes, in_flight_total, recorded_total = [], 0, 0
    for key, s in snaps.items():
        if s is None:
            nodes.append({"node_id": config.ZONES[key]["node_id"], "complete": False})
            continue
        channels = [{"from": c.from_node, "to": s.node_id, "in_flight": list(c.in_flight)} for c in s.channels]
        in_flight = sum(sum(c["in_flight"]) for c in channels)
        recorded_total += s.recorded_flex
        in_flight_total += in_flight
        nodes.append({"node_id": s.node_id, "complete": s.complete, "recorded_flex": s.recorded_flex,
                      "channels": channels, "waiting_on": list(s.waiting_on)})
    return {
        "success": True, "snapshot_id": snapshot_id, "initiator": config.ZONES[initiator_key]["node_id"],
        "transfer": {"from": src_node, "to": dst_node, "amount": amount, "delay_ms": delay_ms},
        "before": flex, "naive_reading": {z["node_id"]: z["flex_bays"] for z in naive["zones"]}, "naive_total": naive["total"],
        "recorded_total": recorded_total, "in_flight_total": in_flight_total,
        "snapshot_total": recorded_total + in_flight_total, "expected_total": expected_total,
        "consistent": recorded_total + in_flight_total == expected_total, "nodes": nodes,
    }


# ------------------------------------------------------------------------- ledger

def _ledger_status(key):
    try:
        st = zone_stub_for(key).VerifyLedger(parking_pb2.Empty(), timeout=2)
        return {"node_id": st.node_id, "status": "ONLINE", "length": st.length, "valid": st.valid,
                "bad_index": st.bad_index, "head_hash": st.head_hash}
    except grpc.RpcError:
        return {"node_id": config.ZONES[key]["node_id"], "status": "OFFLINE"}


@app.get("/api/ledger")
def ledger_view(limit: int = 25):
    replicas = _parallel(_ledger_status, list(config.ZONES))
    online = [r for r in replicas if r["status"] == "ONLINE"]
    heads = {r["head_hash"] for r in online}
    consistent = bool(online) and all(r["valid"] for r in online) and len(heads) == 1 and len({r["length"] for r in online}) == 1

    healthy = [r for r in online if r["valid"]]
    blocks = []
    if healthy:
        best = max(healthy, key=lambda r: r["length"])
        key = config.ZONE_BY_NODE[best["node_id"]]
        start = max(best["length"] - limit, 0)
        resp = zone_stub_for(key).GetBlocks(parking_pb2.GetBlocksRequest(from_index=start), timeout=3)
        blocks = [json.loads(b) for b in resp.blocks_json]
    return {"replicas": replicas, "consistent": consistent, "blocks": blocks, "majority_hash": next(iter(heads)) if len(heads) == 1 else None}


@app.post("/api/ledger/tamper")
def ledger_tamper(zone: str = "B", index: int = 0):
    key = zone.upper()
    if key not in config.ZONES:
        return {"success": False, "message": "unknown zone"}
    if index <= 0:
        index = max(_ledger_status(key).get("length", 1) - 2, 1)
    try:
        ack = zone_stub_for(key).TamperLedger(parking_pb2.TamperRequest(index=index), timeout=3)
    except grpc.RpcError as exc:
        return _error(exc)
    return {"success": ack.success, "message": ack.message, "index": index}


@app.post("/api/ledger/repair")
def ledger_repair(zone: str = "B"):
    key = zone.upper()
    if key not in config.ZONES:
        return {"success": False, "message": "unknown zone"}
    try:
        st = zone_stub_for(key).RepairLedger(parking_pb2.Empty(), timeout=8)
    except grpc.RpcError as exc:
        return _error(exc)
    return {"success": st.valid, "message": st.message, "length": st.length}


# -------------------------------------------------------------- serverless / batch

@app.get("/api/faas/functions")
def faas_functions():
    try:
        return _http.get(f"{config.FAAS_URL}/functions", timeout=2).json()
    except Exception as exc:
        return {"functions": [], "error": str(exc)}


@app.post("/api/faas/invoke/{name}")
def faas_invoke(name: str, event: dict):
    try:
        r = _http.post(f"{config.FAAS_URL}/invoke/{name}", json=event, timeout=5)
        return r.json()
    except Exception as exc:
        return {"error": str(exc)}


@app.post("/api/faas/evict/{name}")
def faas_evict(name: str):
    try:
        return _http.post(f"{config.FAAS_URL}/functions/{name}/evict", timeout=2).json()
    except Exception as exc:
        return {"error": str(exc)}


@app.post("/api/analytics/run")
def analytics_run(job: str = "peak_hours", source: str = "synthetic", n: int = 200000, workers: int = 4):
    try:
        r = _http.post(f"{config.ANALYTICS_URL}/run", params={"job": job, "source": source, "n": n, "workers": workers}, timeout=120)
        if r.status_code != 200:
            return {"error": r.json().get("detail", r.text)}
        return r.json()
    except Exception as exc:
        return {"error": str(exc)}


# ------------------------------------------------------------------------ websocket

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


def _start_event_bridge(loop: asyncio.AbstractEventLoop):
    """Background thread: consume Redis Streams events and fan them out over
    WebSocket to every connected browser (message bus -> stream bridge)."""

    def _run():
        for event in consume_events():
            asyncio.run_coroutine_threadsafe(manager.broadcast(event), loop)

    threading.Thread(target=_run, daemon=True).start()


@app.on_event("startup")
async def on_startup():
    loop = asyncio.get_event_loop()
    _start_event_bridge(loop)
    publish_event("GATEWAY_STARTED", source=config.GATEWAY_NAME, data={})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.BIND_HOST, port=config.GATEWAY_PORT)
