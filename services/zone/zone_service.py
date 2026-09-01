"""A single parking zone node.

One shared implementation, launched three times as three independent OS
processes (Zone A / B / C), each parametrized by --zone. This keeps the
code DRY without the three zones being classes inside one process — what
actually makes them "independent" is that each is its own `python`
process with its own gRPC server, its own TCP P2P server, and its own
heartbeat thread. Each zone keeps its own slot state in a plain Python
dict, in memory — no shared database, no other process ever touches it.

Run standalone:
    python -m services.zone.zone_service --zone A
    python -m services.zone.zone_service --zone B
    python -m services.zone.zone_service --zone C
"""

import sys
import os
import argparse
import random
import threading
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import grpc
from concurrent import futures

import config
from communication.grpc import parking_pb2, parking_pb2_grpc
from communication.grpc.grpc_client import coordinator_stub
from communication.messaging.message_bus import publish_event
from communication.p2p.p2p_client import start_p2p_server, send_p2p_message


class SlotStore:
    """In-memory slot state for one zone. Guarded by a lock since gRPC
    handlers run on a thread pool."""

    def __init__(self, prefix: str, total_slots: int, occupied_ratio: float = 0.25):
        self.lock = threading.Lock()
        rng = random.Random(42)
        n_occupied = max(1, int(total_slots * occupied_ratio))
        occupied_indices = set(rng.sample(range(1, total_slots + 1), n_occupied))
        self.slots = {
            f"{prefix}-{i:02d}": ("OCCUPIED" if i in occupied_indices else "AVAILABLE")
            for i in range(1, total_slots + 1)
        }
        self.reservations = {}  # reservation_id -> slot_id

    def counts(self):
        with self.lock:
            result = {"AVAILABLE": 0, "OCCUPIED": 0, "RESERVED": 0}
            for status in self.slots.values():
                result[status] += 1
            return result

    def available_ids(self):
        with self.lock:
            return [sid for sid, status in self.slots.items() if status == "AVAILABLE"]

    def reserve_any(self, reservation_id: str):
        with self.lock:
            for slot_id, status in self.slots.items():
                if status == "AVAILABLE":
                    self.slots[slot_id] = "RESERVED"
                    self.reservations[reservation_id] = slot_id
                    return slot_id
            return None

    def release(self, reservation_id: str):
        with self.lock:
            slot_id = self.reservations.pop(reservation_id, None)
            if slot_id is None:
                return None
            self.slots[slot_id] = "AVAILABLE"
            return slot_id


class ZoneRuntime:
    def __init__(self, zone_key: str):
        cfg = config.ZONES[zone_key]
        self.zone_key = zone_key
        self.node_id = cfg["node_id"]
        self.zone_id = cfg["zone_id"]
        self.host = config.HOST
        self.port = cfg["port"]
        self.total_slots = cfg["total_slots"]
        self.p2p_port = cfg["p2p_port"]
        self.peers = config.P2P_PEERS.get(zone_key, [])
        self.simulate_failure = False
        self.store = SlotStore(zone_key, self.total_slots)


def _log(node_id, msg):
    print(f"[{node_id}] {msg}", flush=True)


class ZoneServicer(parking_pb2_grpc.ZoneServiceServicer):
    def __init__(self, rt: ZoneRuntime):
        self.rt = rt

    def _check_alive(self, context):
        if self.rt.simulate_failure:
            context.abort(grpc.StatusCode.UNAVAILABLE, "zone is simulating failure")

    def GetZoneStatus(self, request, context):
        self._check_alive(context)
        counts = self.rt.store.counts()
        return parking_pb2.ZoneStatusResponse(
            zone_id=self.rt.zone_id, node_id=self.rt.node_id, total_slots=self.rt.total_slots,
            available_slots=counts["AVAILABLE"], occupied_slots=counts["OCCUPIED"],
            reserved_slots=counts["RESERVED"], status="ONLINE",
        )

    def GetAvailableSlots(self, request, context):
        self._check_alive(context)
        slot_ids = self.rt.store.available_ids()
        return parking_pb2.AvailableSlotsResponse(available_count=len(slot_ids), slot_ids=slot_ids)

    def ReserveSlot(self, request, context):
        self._check_alive(context)
        slot_id = self.rt.store.reserve_any(request.reservation_id)
        if slot_id is None:
            return parking_pb2.ReserveSlotResponse(success=False, slot_id="", message="No available slot")
        _log(self.rt.node_id, f"Reserved {slot_id} (reservation {request.reservation_id})")
        return parking_pb2.ReserveSlotResponse(success=True, slot_id=slot_id, message="Reserved")

    def ReleaseSlot(self, request, context):
        self._check_alive(context)
        slot_id = self.rt.store.release(request.reservation_id)
        if slot_id is None:
            return parking_pb2.ReleaseSlotResponse(success=False, message="Unknown or already-released reservation")
        _log(self.rt.node_id, f"Released {slot_id} (reservation {request.reservation_id})")
        return parking_pb2.ReleaseSlotResponse(success=True, message="Released", slot_id=slot_id)

    def SetFailureMode(self, request, context):
        self.rt.simulate_failure = request.simulate_failure
        status = "FAILING" if request.simulate_failure else "RECOVERING"
        _log(self.rt.node_id, f"Admin: simulate_failure={request.simulate_failure} -> {status}")
        if not request.simulate_failure:
            threading.Thread(target=lambda: (_register_with_coordinator(self.rt), _log(self.rt.node_id, "Re-registered after recovery")), daemon=True).start()
        return parking_pb2.SetFailureModeResponse(success=True, status=status)


def _register_with_coordinator(rt: ZoneRuntime):
    stub = coordinator_stub(config.HOST, config.COORDINATOR_GRPC_PORT)
    try:
        stub.RegisterNode(parking_pb2.RegisterNodeRequest(
            node_id=rt.node_id, zone_id=rt.zone_id, host=rt.host,
            grpc_port=rt.port, total_slots=rt.total_slots,
        ), timeout=5)
        _log(rt.node_id, f"Registering with coordinator... done")
    except grpc.RpcError as exc:
        _log(rt.node_id, f"Could not reach coordinator to register: {exc.code()}")


def _heartbeat_loop(rt: ZoneRuntime):
    stub = coordinator_stub(config.HOST, config.COORDINATOR_GRPC_PORT)
    while True:
        time.sleep(config.HEARTBEAT_INTERVAL_SEC)
        if rt.simulate_failure:
            continue
        try:
            stub.Heartbeat(parking_pb2.HeartbeatRequest(node_id=rt.node_id), timeout=2)
        except grpc.RpcError:
            pass


def _p2p_handle_message(rt: ZoneRuntime, message: str) -> str:
    if message == "CAPACITY_REQUEST":
        if rt.simulate_failure:
            return "UNAVAILABLE"
        counts = rt.store.counts()
        return f"AVAILABLE_SLOTS={counts['AVAILABLE']}"
    return "UNKNOWN_COMMAND"


def _p2p_poll_loop(rt: ZoneRuntime):
    """Periodically ask peer zones for their capacity, purely P2P (no coordinator involved).

    Also publishes a P2P_MESSAGE event so the browser's live activity feed can
    show this exchange next to the RPC and message-bus activity — otherwise
    P2P traffic would only ever be visible in the terminal logs.
    """
    while True:
        time.sleep(15)
        if rt.simulate_failure:
            continue
        for peer_key in rt.peers:
            peer_cfg = config.ZONES[peer_key]
            _log(rt.node_id, f"P2P -> {peer_cfg['node_id']} CAPACITY_REQUEST")
            reply = send_p2p_message(config.HOST, peer_cfg["p2p_port"], "CAPACITY_REQUEST")
            if reply:
                _log(rt.node_id, f"P2P <- {peer_cfg['node_id']} {reply}")
                publish_event("P2P_MESSAGE", source=rt.node_id, data={
                    "peer": peer_cfg["node_id"], "request": "CAPACITY_REQUEST", "reply": reply,
                })


def serve(zone_key: str):
    rt = ZoneRuntime(zone_key)

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    parking_pb2_grpc.add_ZoneServiceServicer_to_server(ZoneServicer(rt), server)
    server.add_insecure_port(f"{rt.host}:{rt.port}")
    server.start()
    _log(rt.node_id, f"Starting on {rt.host}:{rt.port} (zone_id={rt.zone_id}, slots={rt.total_slots})")

    start_p2p_server(rt.host, rt.p2p_port, lambda msg: _p2p_handle_message(rt, msg))
    _log(rt.node_id, f"P2P listener on {rt.host}:{rt.p2p_port}")

    _log(rt.node_id, "Registering with coordinator...")
    _register_with_coordinator(rt)

    threading.Thread(target=_heartbeat_loop, args=(rt,), daemon=True).start()
    threading.Thread(target=_p2p_poll_loop, args=(rt,), daemon=True).start()

    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        server.stop(0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--zone", required=True, choices=list(config.ZONES.keys()))
    args = parser.parse_args()
    serve(args.zone)
