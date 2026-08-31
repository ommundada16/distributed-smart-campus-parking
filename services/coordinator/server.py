"""Parking Coordinator: the central distributed-systems coordination point.

Responsibilities (per FA-1 scope):
  - register parking zone nodes and keep an in-memory registry
  - receive heartbeats, detect failed nodes, mark them OFFLINE
  - talk to zone nodes over gRPC to find/reserve/release slots
  - expose gateway-facing RPCs (FindParking, ReleaseParking, GetSystemStatus)
  - publish lifecycle/parking events onto the Redis message bus

Run standalone:
    python -m services.coordinator.server
"""

import sys
import os
import threading
import time
import uuid
from concurrent import futures
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import grpc

import config
from communication.grpc import parking_pb2, parking_pb2_grpc
from communication.grpc.grpc_client import zone_stub
from communication.messaging.message_bus import publish_event


class NodeRecord:
    def __init__(self, node_id, zone_id, host, port, total_slots):
        self.node_id = node_id
        self.zone_id = zone_id
        self.host = host
        self.port = port
        self.total_slots = total_slots
        self.status = "ONLINE"
        self.last_heartbeat = time.time()


class CoordinatorState:
    def __init__(self):
        self.nodes: dict[str, NodeRecord] = {}          # node_id -> NodeRecord
        self.reservation_zone: dict[str, str] = {}       # reservation_id -> node_id
        self.lock = threading.Lock()

    def online_nodes(self):
        with self.lock:
            return [n for n in self.nodes.values() if n.status == "ONLINE"]


state = CoordinatorState()


def _log(msg: str):
    print(f"[COORDINATOR] {msg}", flush=True)


class CoordinatorServicer(parking_pb2_grpc.CoordinatorServicer):

    def RegisterNode(self, request, context):
        with state.lock:
            was_known = request.node_id in state.nodes
            state.nodes[request.node_id] = NodeRecord(
                request.node_id, request.zone_id, request.host,
                request.grpc_port, request.total_slots,
            )
        _log(f"{request.node_id} registered ({request.zone_id} @ {request.host}:{request.grpc_port})")
        publish_event("NODE_REGISTERED" if not was_known else "NODE_RECOVERED",
                       source="coordinator",
                       data={"node_id": request.node_id, "zone_id": request.zone_id})
        return parking_pb2.RegisterNodeResponse(success=True, message="registered")

    def Heartbeat(self, request, context):
        with state.lock:
            node = state.nodes.get(request.node_id)
            if node is None:
                return parking_pb2.HeartbeatResponse(acknowledged=False, server_time=_now())
            was_offline = node.status == "OFFLINE"
            node.last_heartbeat = time.time()
            node.status = "ONLINE"
        if was_offline:
            _log(f"{request.node_id} heartbeat resumed -> ONLINE")
        return parking_pb2.HeartbeatResponse(acknowledged=True, server_time=_now())

    def FindParking(self, request, context):
        publish_event("PARKING_REQUESTED", source="coordinator", data={})
        candidates = state.online_nodes()
        _log(f"FindParking: {len(candidates)} online zone(s) to check")

        for node in candidates:
            try:
                stub = zone_stub(node.host, node.port)
                _log(f"RPC -> {node.node_id} GetAvailableSlots()")
                resp = stub.GetAvailableSlots(parking_pb2.AvailableSlotsRequest(), timeout=2)
                _log(f"RPC <- {node.node_id} available_count={resp.available_count}")
                if resp.available_count <= 0:
                    continue

                reservation_id = f"RES-{uuid.uuid4().hex[:8].upper()}"
                reserve_resp = stub.ReserveSlot(
                    parking_pb2.ReserveSlotRequest(reservation_id=reservation_id), timeout=2
                )
                if not reserve_resp.success:
                    continue

                with state.lock:
                    state.reservation_zone[reservation_id] = node.node_id

                publish_event("PARKING_RESERVED", source=node.node_id, data={
                    "zone_id": node.zone_id, "slot_id": reserve_resp.slot_id,
                    "reservation_id": reservation_id,
                })
                publish_event("SLOT_STATUS_CHANGED", source=node.node_id, data={
                    "slot_id": reserve_resp.slot_id, "status": "RESERVED",
                })

                return parking_pb2.FindParkingResponse(
                    success=True, zone_id=node.zone_id, node_id=node.node_id,
                    slot_id=reserve_resp.slot_id, reservation_id=reservation_id,
                    message="Slot reserved",
                )
            except grpc.RpcError as exc:
                _log(f"RPC error contacting {node.node_id}: {exc.code()}")
                continue

        return parking_pb2.FindParkingResponse(success=False, message="No available parking slots")

    def ReleaseParking(self, request, context):
        with state.lock:
            node_id = state.reservation_zone.get(request.reservation_id)
            node = state.nodes.get(node_id) if node_id else None

        if node is None:
            return parking_pb2.ReleaseParkingResponse(success=False, message="Unknown reservation")

        try:
            stub = zone_stub(node.host, node.port)
            resp = stub.ReleaseSlot(
                parking_pb2.ReleaseSlotRequest(reservation_id=request.reservation_id), timeout=2
            )
        except grpc.RpcError as exc:
            return parking_pb2.ReleaseParkingResponse(success=False, message=f"Zone unreachable: {exc.code()}")

        if resp.success:
            with state.lock:
                state.reservation_zone.pop(request.reservation_id, None)
            publish_event("PARKING_RELEASED", source=node.node_id, data={
                "zone_id": node.zone_id, "slot_id": resp.slot_id,
                "reservation_id": request.reservation_id,
            })
            publish_event("SLOT_STATUS_CHANGED", source=node.node_id, data={
                "slot_id": resp.slot_id, "status": "AVAILABLE",
            })

        return parking_pb2.ReleaseParkingResponse(success=resp.success, message=resp.message)

    def GetSystemStatus(self, request, context):
        with state.lock:
            nodes_snapshot = list(state.nodes.values())

        infos = []
        for node in nodes_snapshot:
            counts = {"AVAILABLE": 0, "OCCUPIED": 0, "RESERVED": 0}
            if node.status == "ONLINE":
                try:
                    stub = zone_stub(node.host, node.port)
                    resp = stub.GetZoneStatus(parking_pb2.ZoneStatusRequest(), timeout=1.5)
                    counts["AVAILABLE"] = resp.available_slots
                    counts["OCCUPIED"] = resp.occupied_slots
                    counts["RESERVED"] = resp.reserved_slots
                except grpc.RpcError:
                    pass

            infos.append(parking_pb2.NodeInfo(
                node_id=node.node_id, zone_id=node.zone_id, host=node.host, port=node.port,
                status=node.status, last_heartbeat=datetime.fromtimestamp(node.last_heartbeat, tz=timezone.utc).isoformat(),
                total_slots=node.total_slots, available_slots=counts["AVAILABLE"],
                occupied_slots=counts["OCCUPIED"], reserved_slots=counts["RESERVED"],
            ))

        return parking_pb2.SystemStatusResponse(nodes=infos)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _heartbeat_monitor():
    while True:
        time.sleep(1)
        now = time.time()
        with state.lock:
            for node in state.nodes.values():
                if node.status == "ONLINE" and (now - node.last_heartbeat) > config.HEARTBEAT_TIMEOUT_SEC:
                    node.status = "OFFLINE"
                    _log(f"{node.node_id} missed heartbeats -> OFFLINE")
                    publish_event("NODE_FAILED", source="coordinator", data={"node_id": node.node_id, "zone_id": node.zone_id})


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    parking_pb2_grpc.add_CoordinatorServicer_to_server(CoordinatorServicer(), server)
    server.add_insecure_port(f"{config.HOST}:{config.COORDINATOR_GRPC_PORT}")
    server.start()
    _log(f"Starting on {config.HOST}:{config.COORDINATOR_GRPC_PORT} ...")

    threading.Thread(target=_heartbeat_monitor, daemon=True).start()

    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        server.stop(0)


if __name__ == "__main__":
    serve()
