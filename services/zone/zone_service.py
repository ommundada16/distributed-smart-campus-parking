"""A single parking zone node (FA-2).

One shared implementation, launched three times as three independent processes
(Zone A / B / C). Besides the FA-1 slot service it now takes part in:

  * Ricart-Agrawala mutual exclusion over the shared overflow lot   (Unit 3)

Run standalone:
    python -m services.zone.zone_service --zone A
"""

import sys
import os
import argparse
import random
import threading
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import grpc

import config
from communication.discovery import LeaderLocator
from communication.grpc import parking_pb2, parking_pb2_grpc
from communication.grpc.grpc_client import make_server, replica_stub, zone_stub_for
from communication.messaging.message_bus import get_redis_client, publish_event
from communication.p2p.p2p_client import send_p2p_message, start_p2p_server
from distributed import clocks
from distributed.mutex import RicartAgrawala


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
        self.host = cfg["host"]
        self.port = cfg["port"]
        self.total_slots = cfg["total_slots"]
        self.p2p_port = cfg["p2p_port"]
        self.peers = config.P2P_PEERS.get(zone_key, [])
        self.simulate_failure = False
        self.store = SlotStore(zone_key, self.total_slots, cfg.get("occupied_ratio", 0.25))
        self.locator = LeaderLocator()

        # ---- mutual exclusion over the shared overflow lot
        self.trace_lock = threading.Lock()
        self.trace_log: list[tuple[float, str]] = []
        peer_nodes = [c["node_id"] for k, c in config.ZONES.items() if k != zone_key]
        self.peer_nodes = peer_nodes
        self.ra = RicartAgrawala(
            self.node_id, peer_nodes, self._ra_send_request,
            lamport=clocks.get_clock(), trace=self._trace,
        )
        # Ricart-Agrawala is one request per node at a time; this local lock queues
        # this zone's own concurrent requests (gRPC handlers run on a thread pool).
        self.overflow_local = threading.Lock()

    # ---- helpers --------------------------------------------------------

    def log(self, msg):
        print(f"[{self.node_id}] {msg}", flush=True)

    def _trace(self, text: str):
        with self.trace_lock:
            self.trace_log.append((time.time(), text))
            del self.trace_log[:-300]

    def trace_since(self, since: float) -> list[str]:
        with self.trace_lock:
            return [t for ts, t in self.trace_log if ts >= since]

    def _ra_send_request(self, peer_node: str, from_id: str, ts: int) -> bool:
        stub = zone_stub_for(config.ZONE_BY_NODE[peer_node])
        return stub.RequestCS(parking_pb2.RaRequest(resource="OVERFLOW", ts=ts, from_node=from_id), timeout=30).granted

    def register(self):
        try:
            self.locator.call("RegisterNode", parking_pb2.RegisterNodeRequest(
                node_id=self.node_id, zone_id=self.zone_id, host=self.host,
                grpc_port=self.port, total_slots=self.total_slots,
            ), timeout=3, attempts=2)
            self.log("Registered with the coordinator leader")
        except Exception as exc:
            self.log(f"Could not register with a leader yet: {exc}")


class ZoneServicer(parking_pb2_grpc.ZoneServiceServicer):
    def __init__(self, rt: ZoneRuntime):
        self.rt = rt

    def _check_alive(self, context):
        if self.rt.simulate_failure:
            context.abort(grpc.StatusCode.UNAVAILABLE, "zone is simulating failure")

    # ---------------------------------------------------------- FA-1 slots

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
        self.rt.log(f"Reserved {slot_id} (reservation {request.reservation_id})")
        return parking_pb2.ReserveSlotResponse(success=True, slot_id=slot_id, message="Reserved")

    def ReleaseSlot(self, request, context):
        self._check_alive(context)
        slot_id = self.rt.store.release(request.reservation_id)
        if slot_id is None:
            return parking_pb2.ReleaseSlotResponse(success=False, message="Unknown or already-released reservation")
        self.rt.log(f"Released {slot_id} (reservation {request.reservation_id})")
        return parking_pb2.ReleaseSlotResponse(success=True, message="Released", slot_id=slot_id)

    def SetFailureMode(self, request, context):
        was_failed = self.rt.simulate_failure
        self.rt.simulate_failure = request.simulate_failure
        status = "FAILING" if request.simulate_failure else "RECOVERING"
        self.rt.log(f"Admin: simulate_failure={request.simulate_failure} -> {status}")
        if was_failed and not request.simulate_failure:
            def recover():
                self.rt.register()
                self.rt.log("Re-registered with the leader after recovery")
            threading.Thread(target=recover, daemon=True).start()
        return parking_pb2.SetFailureModeResponse(success=True, status=status)

    # ------------------------------------------ Ricart-Agrawala overflow lot

    def _overflow_critical_section(self, use_mutex: bool, work):
        """Run `work` against the shared overflow counter, under Ricart-Agrawala
        unless the demo asks to run without it. Returns (work's result, the
        Lamport timestamp of our REQUEST, or 0 without the mutex)."""
        rt = self.rt
        if not use_mutex:
            rt._trace(f"{rt.node_id}: NO LOCK - entering critical section directly")
            return work(), 0
        with rt.overflow_local, rt.ra.critical_section():
            return work(), rt.ra.my_ts

    def OverflowBook(self, request, context):
        self._check_alive(context)
        rt = self.rt
        started = time.time() - 0.05
        redis_client = get_redis_client()
        hold = max(request.hold_ms, 0) / 1000.0

        def critical_work():
            entered = time.time()  # real time, only used to show critical sections never overlap
            free = int(redis_client.get(config.OVERFLOW_KEY) or 0)    # read ...
            time.sleep(hold)                                          # ... validate / take payment ...
            if free > 0:
                redis_client.set(config.OVERFLOW_KEY, free - 1)       # ... write back (lost update if unprotected)
                redis_client.hset(config.OVERFLOW_BOOKINGS_KEY, request.booking_id, rt.node_id)
                ok, msg = True, "booked an overflow slot"
            else:
                ok, msg = False, "overflow lot full"
            return ok, msg, free, entered, time.time()

        (ok, msg, free, entered, exited), request_ts = self._overflow_critical_section(request.use_mutex, critical_work)

        publish_event("OVERFLOW_BOOKED" if ok else "OVERFLOW_REJECTED", source=rt.node_id, data={
            "mutex": request.use_mutex, "saw_free": free, "booking_id": request.booking_id,
        })
        return parking_pb2.OverflowBookResponse(
            success=ok, message=msg, node_id=rt.node_id, saw_free=free, request_ts=request_ts,
            entered_at=entered, exited_at=exited, trace=rt.trace_since(started),
        )

    def OverflowRelease(self, request, context):
        """Give an overflow slot back. Also a read-modify-write on the shared
        counter, so it runs under the same mutual exclusion as booking."""
        self._check_alive(context)
        rt = self.rt
        redis_client = get_redis_client()

        def critical_work():
            if not redis_client.hdel(config.OVERFLOW_BOOKINGS_KEY, request.booking_id):
                return False, "unknown or already-released overflow booking"
            free = int(redis_client.get(config.OVERFLOW_KEY) or 0)
            redis_client.set(config.OVERFLOW_KEY, free + 1)
            return True, "released an overflow slot"

        (ok, msg), _ = self._overflow_critical_section(True, critical_work)
        if ok:
            publish_event("OVERFLOW_RELEASED", source=rt.node_id, data={"booking_id": request.booking_id})
        return parking_pb2.Ack(success=ok, message=msg)

    def RequestCS(self, request, context):
        self._check_alive(context)
        return parking_pb2.RaReply(granted=self.rt.ra.on_request(request.from_node, request.ts))


def _heartbeat_loop(rt: ZoneRuntime):
    registered_with = None
    while True:
        time.sleep(config.HEARTBEAT_INTERVAL_SEC)
        if rt.simulate_failure:
            registered_with = None
            continue
        try:
            leader = rt.locator.cached or rt.locator.discover()
            if not leader:
                continue
            resp = replica_stub(leader).Heartbeat(parking_pb2.HeartbeatRequest(node_id=rt.node_id), timeout=2)
            if not resp.acknowledged or registered_with != leader:
                rt.register()
                registered_with = leader
        except grpc.RpcError:
            rt.locator._leader_id = None  # leader gone or changed: rediscover next round
            registered_with = None


def _p2p_handle_message(rt: ZoneRuntime, message: str) -> str:
    if message == "CAPACITY_REQUEST":
        if rt.simulate_failure:
            return "UNAVAILABLE"
        counts = rt.store.counts()
        return f"AVAILABLE_SLOTS={counts['AVAILABLE']}"
    return "UNKNOWN_COMMAND"


def _p2p_poll_loop(rt: ZoneRuntime):
    """Periodically ask peer zones for their capacity, purely P2P (no coordinator involved)."""
    while True:
        time.sleep(15)
        if rt.simulate_failure:
            continue
        for peer_key in rt.peers:
            peer_cfg = config.ZONES[peer_key]
            reply = send_p2p_message(peer_cfg["host"], peer_cfg["p2p_port"], "CAPACITY_REQUEST")
            if reply:
                rt.log(f"P2P <- {peer_cfg['node_id']} {reply}")
                publish_event("P2P_MESSAGE", source=rt.node_id, data={
                    "peer": peer_cfg["node_id"], "request": "CAPACITY_REQUEST", "reply": reply,
                })


def _init_overflow_lot(rt: ZoneRuntime):
    """Create the shared overflow counter if no zone has yet (SET NX: first one wins)."""
    for _ in range(10):
        try:
            if get_redis_client().set(config.OVERFLOW_KEY, config.OVERFLOW_CAPACITY, nx=True):
                rt.log(f"overflow lot initialised with {config.OVERFLOW_CAPACITY} slots")
            return
        except Exception:
            time.sleep(1)  # Redis not up yet


def serve(zone_key: str):
    clocks.init_clock()
    rt = ZoneRuntime(zone_key)

    server = make_server(max_workers=32)
    parking_pb2_grpc.add_ZoneServiceServicer_to_server(ZoneServicer(rt), server)
    server.add_insecure_port(f"{config.BIND_HOST}:{rt.port}")
    server.start()
    rt.log(f"Starting on {config.BIND_HOST}:{rt.port} (zone_id={rt.zone_id}, slots={rt.total_slots})")

    start_p2p_server(config.BIND_HOST, rt.p2p_port, lambda msg: _p2p_handle_message(rt, msg))
    rt.log(f"P2P listener on {config.BIND_HOST}:{rt.p2p_port}")

    def join():
        _init_overflow_lot(rt)
        rt.register()

    threading.Thread(target=join, daemon=True).start()
    threading.Thread(target=_heartbeat_loop, args=(rt,), daemon=True).start()
    threading.Thread(target=_p2p_poll_loop, args=(rt,), daemon=True).start()

    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        server.stop(0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--zone", default=os.environ.get("ZONE_KEY"), choices=list(config.ZONES.keys()))
    args = parser.parse_args()
    if not args.zone:
        parser.error("--zone (or ZONE_KEY env) is required")
    serve(args.zone)
