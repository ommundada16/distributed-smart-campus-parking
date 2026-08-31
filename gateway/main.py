"""API Gateway: the only HTTP-facing service. Bridges the React client to the
distributed backend (gRPC to the Coordinator/Zones, WebSocket to the browser).

Run standalone:
    uvicorn gateway.main:app --port 8000 --reload
"""

import sys
import os
import asyncio
import threading

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import grpc
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import config
from communication.grpc import parking_pb2
from communication.grpc.grpc_client import coordinator_stub, zone_stub
from communication.messaging.message_bus import publish_event, read_recent_events, consume_events
from communication.websocket.websocket_manager import manager

app = FastAPI(title="Distributed Smart Campus Parking System - API Gateway")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _coordinator():
    return coordinator_stub(config.HOST, config.COORDINATOR_GRPC_PORT)


@app.get("/health")
def health():
    return {"status": "ok", "service": "api-gateway", "port": config.GATEWAY_PORT}


@app.post("/api/parking/find")
def find_parking():
    try:
        resp = _coordinator().FindParking(parking_pb2.FindParkingRequest(), timeout=6)
    except grpc.RpcError as exc:
        return {"success": False, "message": f"Coordinator unreachable: {exc.code()}"}
    return {
        "success": resp.success,
        "zone_id": resp.zone_id,
        "node_id": resp.node_id,
        "slot_id": resp.slot_id,
        "reservation_id": resp.reservation_id,
        "message": resp.message,
    }


class ReleaseRequest(BaseModel):
    reservation_id: str


@app.post("/api/parking/release")
def release_parking(body: ReleaseRequest):
    try:
        resp = _coordinator().ReleaseParking(
            parking_pb2.ReleaseParkingRequest(reservation_id=body.reservation_id), timeout=6
        )
    except grpc.RpcError as exc:
        return {"success": False, "message": f"Coordinator unreachable: {exc.code()}"}
    return {"success": resp.success, "message": resp.message}


@app.get("/api/system/status")
def system_status():
    services = []

    # Coordinator's own reachability, checked directly (not through itself).
    coordinator_online = True
    try:
        resp = _coordinator().GetSystemStatus(parking_pb2.SystemStatusRequest(), timeout=2)
    except grpc.RpcError:
        coordinator_online = False
        resp = None

    services.append({
        "service": "Coordinator", "node_id": "COORDINATOR", "port": config.COORDINATOR_GRPC_PORT,
        "status": "ONLINE" if coordinator_online else "OFFLINE",
    })
    services.append({
        "service": "API Gateway", "node_id": "GATEWAY", "port": config.GATEWAY_PORT,
        "status": "ONLINE",
    })

    zones = []
    if resp is not None:
        for node in resp.nodes:
            zones.append({
                "service": f"Zone {node.zone_id[-1]}", "node_id": node.node_id, "zone_id": node.zone_id,
                "host": node.host, "port": node.port, "status": node.status,
                "last_heartbeat": node.last_heartbeat, "total_slots": node.total_slots,
                "available_slots": node.available_slots, "occupied_slots": node.occupied_slots,
                "reserved_slots": node.reserved_slots,
            })

    return {"services": services, "zones": zones}


@app.get("/api/events/recent")
def recent_events(count: int = 20):
    return {"events": read_recent_events(count)}


class FailureRequest(BaseModel):
    simulate_failure: bool


@app.post("/api/admin/zone/{zone_key}/failure")
def set_zone_failure(zone_key: str, body: FailureRequest):
    zone_key = zone_key.upper()
    if zone_key not in config.ZONES:
        return {"success": False, "message": "Unknown zone"}
    cfg = config.ZONES[zone_key]
    try:
        stub = zone_stub(config.HOST, cfg["port"])
        resp = stub.SetFailureMode(
            parking_pb2.SetFailureModeRequest(simulate_failure=body.simulate_failure), timeout=3
        )
    except grpc.RpcError as exc:
        return {"success": False, "message": f"Zone unreachable: {exc.code()}"}
    return {"success": resp.success, "status": resp.status}


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
    WebSocket to every connected browser. This is the message-bus -> stream
    bridge — Redis and WebSocket remain two independent communication styles."""

    def _run():
        for event in consume_events():
            asyncio.run_coroutine_threadsafe(manager.broadcast(event), loop)

    threading.Thread(target=_run, daemon=True).start()


@app.on_event("startup")
async def on_startup():
    loop = asyncio.get_event_loop()
    _start_event_bridge(loop)
    publish_event("GATEWAY_STARTED", source="gateway", data={})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.HOST, port=config.GATEWAY_PORT)
