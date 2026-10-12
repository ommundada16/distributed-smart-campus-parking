"""A single parking zone node (FA-2).

One shared implementation, launched three times as three independent processes
(Zone A / B / C). Besides the FA-1 slot service it now takes part in the
peer-to-peer distributed algorithms:

  * Ricart-Agrawala mutual exclusion over the shared overflow lot   (Unit 3)
  * Chandy-Lamport snapshots over flexible-bay transfers             (Unit 3)
  * Berkeley clock sync (each zone has a deliberately skewed clock)  (Unit 3)
  * a replicated, hash-chained booking ledger                        (Unit 4)

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
from distributed.ledger import Block, Ledger
from distributed.mutex import RicartAgrawala
from distributed.snapshot import ChandyLamport, FifoChannel


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

        # ---- ledger replica
        self.ledger = Ledger()
        self.ledger_sync_lock = threading.Lock()

        # ---- mutual exclusion
        self.trace_lock = threading.Lock()
        self.trace_log: list[tuple[float, str]] = []
        peer_nodes = [c["node_id"] for k, c in config.ZONES.items() if k != zone_key]
        self.peer_nodes = peer_nodes
        self.ra = RicartAgrawala(
            self.node_id, peer_nodes, self._ra_send_request,
            lamport=clocks.get_process_clock().lamport, trace=self._trace,
        )

        # ---- snapshot / flexible bays
        self.flex = config.FLEX_BAYS_PER_ZONE
        self.channels: dict[str, FifoChannel] = {}
        self.cl = ChandyLamport(
            self.node_id, peer_nodes,
            capture_state=lambda: self.flex,
            send_marker=lambda peer, sid: self.channels[peer].post("marker", sid),
        )
        for peer in peer_nodes:
            self.channels[peer] = FifoChannel(
                f"{self.node_id}->{peer}", lambda kind, payload, peer=peer: self._deliver(peer, kind, payload)
            )

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

    def _deliver(self, peer_node: str, kind: str, payload):
        """FifoChannel delivery function: runs the blocking RPC to the peer."""
        stub = zone_stub_for(config.ZONE_BY_NODE[peer_node])
        if kind == "marker":
            stub.Marker(parking_pb2.MarkerRequest(snapshot_id=payload, from_node=self.node_id), timeout=10)
        else:
            transfer_id, amount = payload
            stub.TransferFlex(parking_pb2.TransferRequest(transfer_id=transfer_id, from_node=self.node_id, amount=amount), timeout=10)

    # ---- ledger sync ----------------------------------------------------

    def sync_ledger(self) -> int:
        """Catch up from peer replicas. Returns number of blocks adopted."""
        adopted = 0
        with self.ledger_sync_lock:
            for key in config.ZONES:
                if key == self.zone_key:
                    continue
                try:
                    resp = zone_stub_for(key).GetBlocks(parking_pb2.GetBlocksRequest(from_index=len(self.ledger)), timeout=3)
                except grpc.RpcError:
                    continue
                for raw in resp.blocks_json:
                    ok, _ = self.ledger.append(Block.from_json(raw))
                    if not ok:
                        break
                    adopted += 1
        if adopted:
            self.log(f"ledger sync: adopted {adopted} block(s) from peers (now {len(self.ledger)})")
        return adopted

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
            flex_bays=self.rt.flex, ledger_length=len(self.rt.ledger),
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
                self.rt.sync_ledger()
                self.rt.register()
                self.rt.log("Re-registered and caught up the ledger after recovery")
            threading.Thread(target=recover, daemon=True).start()
        return parking_pb2.SetFailureModeResponse(success=True, status=status)

    # --------------------------------------------------------------- clocks

    def _clock_info(self):
        lamport, vc = clocks.get_process_clock().peek()
        return parking_pb2.ClockInfo(
            node_id=self.rt.node_id, lamport=lamport, vclock_json=clocks.encode_vc(vc),
            physical_time=clocks.physical_clock.now(), offset=clocks.physical_clock.offset,
        )

    def GetClockInfo(self, request, context):
        self._check_alive(context)
        return self._clock_info()

    def AdjustClock(self, request, context):
        self._check_alive(context)
        if request.absolute:
            clocks.physical_clock.set_offset(request.delta)
        else:
            clocks.physical_clock.adjust(request.delta)
        self.rt.log(f"clock adjusted -> offset {clocks.physical_clock.offset:+.3f}s")
        return self._clock_info()

    # ------------------------------------------ Ricart-Agrawala overflow lot

    def OverflowBook(self, request, context):
        self._check_alive(context)
        rt = self.rt
        started = time.time() - 0.05
        redis_client = get_redis_client()
        use_mutex = request.use_mutex
        hold = max(request.hold_ms, 0) / 1000.0

        def critical_work():
            entered = time.time()  # real time, only used to show critical sections never overlap
            lamport, vc = clocks.get_process_clock().local_event()  # event "enter critical section"
            free = int(redis_client.get(config.OVERFLOW_KEY) or 0)    # read ...
            time.sleep(hold)                                          # ... validate / take payment ...
            if free > 0:
                redis_client.set(config.OVERFLOW_KEY, free - 1)       # ... write back (lost update if unprotected)
                redis_client.rpush(config.OVERFLOW_BOOKINGS_KEY, f"{request.booking_id}@{rt.node_id}")
                ok, msg = True, "booked an overflow slot"
            else:
                ok, msg = False, "overflow lot full"
            return ok, msg, free, entered, time.time(), lamport, vc

        if use_mutex:
            with rt.ra.critical_section():
                ok, msg, free, entered, exited, lamport, vc = critical_work()
        else:
            rt._trace(f"{rt.node_id}: NO LOCK - entering critical section directly")
            ok, msg, free, entered, exited, lamport, vc = critical_work()

        publish_event("OVERFLOW_BOOKED" if ok else "OVERFLOW_REJECTED", source=rt.node_id, data={
            "mutex": use_mutex, "saw_free": free, "booking_id": request.booking_id,
        })
        return parking_pb2.OverflowBookResponse(
            success=ok, message=msg, node_id=rt.node_id, saw_free=free, lamport=lamport,
            vclock_json=clocks.encode_vc(vc), entered_at=entered, exited_at=exited,
            trace=rt.trace_since(started),
        )

    def RequestCS(self, request, context):
        self._check_alive(context)
        return parking_pb2.RaReply(granted=self.rt.ra.on_request(request.from_node, request.ts))

    # ------------------------------------------ Chandy-Lamport / flex bays

    def StartTransfer(self, request, context):
        self._check_alive(context)
        rt = self.rt
        if request.to_node not in rt.channels:
            return parking_pb2.Ack(success=False, message="unknown destination")
        with rt.cl.lock:
            if rt.flex < request.amount or request.amount <= 0:
                return parking_pb2.Ack(success=False, message=f"insufficient flex bays ({rt.flex})")
            rt.flex -= request.amount
            transfer_id = f"TX-{int(time.time() * 1000) % 100000}"
            rt.channels[request.to_node].post("transfer", (transfer_id, request.amount), request.delay_ms / 1000.0)
        rt.log(f"sent {request.amount} flex bays to {request.to_node} (in flight {request.delay_ms} ms)")
        publish_event("FLEX_SENT", source=rt.node_id, data={"to": request.to_node, "amount": request.amount, "transfer_id": transfer_id})
        return parking_pb2.Ack(success=True, message=transfer_id)

    def TransferFlex(self, request, context):
        self._check_alive(context)
        rt = self.rt
        with rt.cl.lock:
            rt.flex += request.amount
            rt.cl.on_message(request.from_node, request.amount)
        rt.log(f"received {request.amount} flex bays from {request.from_node}")
        publish_event("FLEX_RECEIVED", source=rt.node_id, data={"from": request.from_node, "amount": request.amount})
        return parking_pb2.Ack(success=True, message="received")

    def Marker(self, request, context):
        self._check_alive(context)
        self.rt.log(f"MARKER({request.snapshot_id}) from {request.from_node}")
        self.rt.cl.on_marker(request.snapshot_id, request.from_node)
        return parking_pb2.Ack(success=True, message="ok")

    def StartSnapshot(self, request, context):
        self._check_alive(context)
        self.rt.log(f"initiating snapshot {request.snapshot_id}")
        publish_event("SNAPSHOT_STARTED", source=self.rt.node_id, data={"snapshot_id": request.snapshot_id})
        self.rt.cl.initiate(request.snapshot_id)
        return parking_pb2.Ack(success=True, message="initiated")

    def GetSnapshot(self, request, context):
        self._check_alive(context)
        snap = self.rt.cl.get(request.snapshot_id)
        if snap is None:
            return parking_pb2.SnapshotResponse(node_id=self.rt.node_id, known=False)
        return parking_pb2.SnapshotResponse(
            node_id=self.rt.node_id, known=True, complete=snap["complete"], recorded_flex=snap["state"],
            channels=[parking_pb2.ChannelState(from_node=p, in_flight=m) for p, m in snap["channels"].items()],
            waiting_on=snap["waiting_on"],
        )

    # ------------------------------------------------------------- ledger

    def AppendBlock(self, request, context):
        self._check_alive(context)
        rt = self.rt
        block = Block.from_json(request.block_json)
        ok, msg = rt.ledger.append(block)
        if not ok and (msg.startswith("gap") or msg.startswith("prev_hash")):
            rt.sync_ledger()  # we missed blocks while down: pull them from peers, then retry
            ok, msg = rt.ledger.append(block)
        if ok:
            rt.log(f"ledger +block #{block.index} ({block.tx.get('type')}) {block.hash[:10]}")
        return parking_pb2.AppendBlockResponse(success=ok, message=msg, length=len(rt.ledger))

    def GetBlocks(self, request, context):
        self._check_alive(context)
        return parking_pb2.GetBlocksResponse(blocks_json=[b.to_json() for b in self.rt.ledger.blocks_from(request.from_index)])

    def _ledger_status(self, message=""):
        valid, bad = self.rt.ledger.verify()
        return parking_pb2.LedgerStatus(
            node_id=self.rt.node_id, valid=valid, bad_index=bad, length=len(self.rt.ledger),
            head_hash=self.rt.ledger.head().hash, message=message,
        )

    def VerifyLedger(self, request, context):
        self._check_alive(context)
        return self._ledger_status()

    def TamperLedger(self, request, context):
        self._check_alive(context)
        ok = self.rt.ledger.tamper(request.index)
        self.rt.log(f"!!! ledger block #{request.index} tampered locally (ok={ok})")
        publish_event("LEDGER_TAMPERED", source=self.rt.node_id, data={"index": request.index})
        return parking_pb2.Ack(success=ok, message="tampered" if ok else "index out of range")

    def RepairLedger(self, request, context):
        self._check_alive(context)
        valid, bad = self.rt.ledger.verify()
        if valid:
            return self._ledger_status("already valid")
        self.rt.ledger.truncate_from(bad)
        adopted = self.rt.sync_ledger()
        publish_event("LEDGER_REPAIRED", source=self.rt.node_id, data={"dropped_from": bad, "adopted": adopted})
        return self._ledger_status(f"dropped blocks from #{bad}, re-synced {adopted} from peers")


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


def serve(zone_key: str):
    node_id = config.ZONES[zone_key]["node_id"]
    clocks.init_clocks(node_id, config.CLOCK_SKEW.get(node_id, 0.0))
    rt = ZoneRuntime(zone_key)

    server = make_server(max_workers=32)
    parking_pb2_grpc.add_ZoneServiceServicer_to_server(ZoneServicer(rt), server)
    server.add_insecure_port(f"{config.BIND_HOST}:{rt.port}")
    server.start()
    rt.log(f"Starting on {config.BIND_HOST}:{rt.port} (zone_id={rt.zone_id}, slots={rt.total_slots}, clock skew {config.CLOCK_SKEW.get(node_id, 0):+.1f}s)")

    start_p2p_server(config.BIND_HOST, rt.p2p_port, lambda msg: _p2p_handle_message(rt, msg))
    rt.log(f"P2P listener on {config.BIND_HOST}:{rt.p2p_port}")

    def join():
        rt.register()
        rt.sync_ledger()  # a restarted zone starts with an empty chain and catches up from its peers

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
