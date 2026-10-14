"""Parking Coordinator replica (FA-2).

Three identical replicas run (COORD_1..3). They elect one leader with the Bully
algorithm and keep it alive with a beacon; only the leader serves parking
traffic. When the leader dies, the survivors elect a new one, the new leader
rebuilds its registry by probing the zones, and the system keeps working.

The leader's jobs:
  * zone registry + heartbeat failure detection            (Unit 2 fault tolerance)
  * load-aware zone allocation (first_fit/round_robin/least_loaded)
  * when every zone is full, booking the shared overflow lot through a zone,
    which takes it under Ricart-Agrawala mutual exclusion   (Unit 3)
  * asking the serverless pricing function for a quote      (Unit 4)

Run:  python -m services.coordinator.server --id 3
"""

import sys
import os
import argparse
import itertools
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import grpc
import httpx

import config
from communication.grpc import parking_pb2, parking_pb2_grpc
from communication.grpc.grpc_client import make_server, replica_stub, zone_stub_for
from communication.messaging.message_bus import get_redis_client, publish_event
from distributed import clocks
from distributed.election import BullyElection
from services.coordinator.policies import Policies

_http = httpx.Client(timeout=1.5)  # one shared client: building a new one per call costs ~150 ms


class NodeRecord:
    def __init__(self, node_id, zone_id, host, port, total_slots):
        self.node_id = node_id
        self.zone_id = zone_id
        self.host = host
        self.port = port
        self.total_slots = total_slots
        self.status = "ONLINE"
        self.last_heartbeat = time.time()

    @property
    def zone_key(self):
        return config.ZONE_BY_NODE[self.node_id]


class Coordinator:
    def __init__(self, coord_id: int):
        self.id = coord_id
        self.cfg = config.COORDINATORS[coord_id]
        self.node_id = self.cfg["node_id"]
        self.failed = False

        self.nodes: dict[str, NodeRecord] = {}
        self.lock = threading.RLock()
        self.policies = Policies()
        self.overflow_turn = itertools.count()  # rotates which zone admits the next overflow booking

        self.election = BullyElection(
            my_id=coord_id,
            all_ids=config.coordinator_ids(),
            send_election=self._send_election,
            send_announce=self._send_announce,
            send_beacon=self._send_beacon,
            fetch_term=self._fetch_term,
            on_leader_change=self._on_leader_change,
            is_alive=lambda: not self.failed,
            beacon_interval=config.BEACON_INTERVAL_SEC,
            beacon_timeout=config.BEACON_TIMEOUT_SEC,
            announce_wait=config.ELECTION_ANNOUNCE_WAIT_SEC,
            log=self.log,
        )

    # ------------------------------------------------------------------ utils

    def log(self, msg: str):
        print(f"[{self.node_id}] {msg}", flush=True)

    # ------------------------------------------------- election transport (gRPC)

    def _send_election(self, to_id: int) -> bool:
        resp = replica_stub(to_id).Election(parking_pb2.ElectionRequest(from_id=self.id), timeout=1.0)
        return resp.ok

    def _send_announce(self, to_id: int, leader_id: int, term: int):
        replica_stub(to_id).Announce(parking_pb2.AnnounceRequest(leader_id=leader_id, term=term), timeout=1.0)

    def _send_beacon(self, to_id: int, leader_id: int, term: int):
        resp = replica_stub(to_id).Beacon(parking_pb2.BeaconRequest(leader_id=leader_id, term=term), timeout=1.0)
        return resp.leader_id, resp.term

    def _fetch_term(self, to_id: int):
        return replica_stub(to_id).WhoIsLeader(parking_pb2.Empty(), timeout=1.0).term

    def _on_leader_change(self, leader_id, term, am_leader):
        if am_leader:
            self.log(f"*** I am the LEADER (term {term}) ***")
            publish_event("LEADER_ELECTED", source=self.node_id, data={"leader": self.node_id, "leader_id": self.id, "term": term})
            threading.Thread(target=self._become_leader_setup, daemon=True).start()
        elif leader_id is None:
            self.log("leader lost - election pending")
            publish_event("LEADER_LOST", source=self.node_id, data={"observer": self.node_id})
        else:
            self.log(f"following leader COORD_{leader_id} (term {term})")
            with self.lock:
                self.nodes.clear()

    # --------------------------------------------------- leader take-over work

    def _become_leader_setup(self):
        """New leader: rebuild the zone registry by probing the zones."""
        with self.lock:
            self.nodes.clear()
        for key, cfg in config.ZONES.items():
            try:
                st = zone_stub_for(key).GetZoneStatus(parking_pb2.ZoneStatusRequest(), timeout=2)
            except grpc.RpcError:
                continue
            with self.lock:
                self.nodes[cfg["node_id"]] = NodeRecord(cfg["node_id"], cfg["zone_id"], cfg["host"], cfg["port"], st.total_slots)
        self.log(f"registry rebuilt from zones: {sorted(self.nodes)}")

    # ---------------------------------------------------------------- pricing

    def quote_price(self, zone_key: str, available: int, total: int) -> tuple[float, str]:
        occupancy = 1 - available / max(total, 1)
        event = {"zone": zone_key, "occupancy": round(occupancy, 3), "hour": datetime.now().hour}
        try:
            resp = _http.post(f"{config.FAAS_URL}/invoke/pricing", json=event)
            resp.raise_for_status()
            body = resp.json()
            return float(body["result"]["price_per_hour"]), f"serverless fn 'pricing' ({'cold' if body['cold_start'] else 'warm'} start, {body['duration_ms']} ms)"
        except Exception:
            return 20.0, "fallback base price (FaaS unreachable)"

    # ----------------------------------------------------------------- policy

    def current_policy(self) -> str:
        try:
            value = get_redis_client().get(config.POLICY_KEY)
            if value in config.POLICIES:
                return value
        except Exception:
            pass
        return config.DEFAULT_POLICY

    # ----------------------------------------------------------- zone queries

    def online_nodes(self) -> list[NodeRecord]:
        with self.lock:
            return [n for n in self.nodes.values() if n.status == "ONLINE"]

    def zone_statuses(self, nodes: list[NodeRecord]) -> list[dict]:
        def probe(node: NodeRecord):
            try:
                st = zone_stub_for(node.zone_key).GetZoneStatus(parking_pb2.ZoneStatusRequest(), timeout=1.5)
                return {"node": node, "node_id": node.node_id, "available": st.available_slots, "total": st.total_slots}
            except grpc.RpcError:
                return None

        if not nodes:
            return []
        with ThreadPoolExecutor(max_workers=len(nodes)) as pool:
            return [r for r in pool.map(probe, nodes) if r]


class CoordinatorServicer(parking_pb2_grpc.CoordinatorServicer):
    def __init__(self, coord: Coordinator):
        self.c = coord

    # ---- guards -----------------------------------------------------------

    def _alive(self, context):
        if self.c.failed:
            context.abort(grpc.StatusCode.UNAVAILABLE, f"{self.c.node_id} is simulating failure")

    def _leader_only(self, context):
        self._alive(context)
        if not self.c.election.is_leader:
            context.abort(grpc.StatusCode.FAILED_PRECONDITION, f"{self.c.node_id} is not the leader (leader={self.c.election.leader_id})")

    # ---- election ---------------------------------------------------------

    def Election(self, request, context):
        self._alive(context)
        ok = self.c.election.handle_election(request.from_id)
        return parking_pb2.ElectionResponse(ok=ok, term=self.c.election.term)

    def Announce(self, request, context):
        self._alive(context)
        return parking_pb2.AnnounceResponse(accepted=self.c.election.handle_announce(request.leader_id, request.term))

    def Beacon(self, request, context):
        self._alive(context)
        leader_id, term = self.c.election.handle_beacon(request.leader_id, request.term)
        return parking_pb2.BeaconResponse(leader_id=leader_id or 0, term=term)

    def WhoIsLeader(self, request, context):
        st = self.c.election.status()
        failing = self.c.failed
        return parking_pb2.LeaderInfo(
            self_id=self.c.id, self_node=self.c.node_id,
            leader_id=0 if failing else (st["leader_id"] or 0), term=st["term"],
            state="FAILING" if failing else "UP", host=self.c.cfg["host"], port=self.c.cfg["port"],
        )

    def SetFailureMode(self, request, context):
        was_failed = self.c.failed
        self.c.failed = request.simulate_failure
        status = "FAILING" if request.simulate_failure else "RECOVERING"
        self.c.log(f"Admin: simulate_failure={request.simulate_failure}")
        if request.simulate_failure and not was_failed:
            publish_event("NODE_FAILED", source=self.c.node_id, data={"node_id": self.c.node_id, "role": "coordinator"})
        if was_failed and not request.simulate_failure:
            publish_event("NODE_RECOVERED", source=self.c.node_id, data={"node_id": self.c.node_id, "role": "coordinator"})
            self.c.election.reset_after_recovery()
        return parking_pb2.SetFailureModeResponse(success=True, status=status)

    # ---- registry / heartbeat --------------------------------------------

    def RegisterNode(self, request, context):
        self._leader_only(context)
        with self.c.lock:
            was_known = request.node_id in self.c.nodes
            self.c.nodes[request.node_id] = NodeRecord(request.node_id, request.zone_id, request.host, request.grpc_port, request.total_slots)
        self.c.log(f"{request.node_id} registered ({request.zone_id} @ {request.host}:{request.grpc_port})")
        publish_event("NODE_REGISTERED" if not was_known else "NODE_RECOVERED", source=self.c.node_id,
                      data={"node_id": request.node_id, "zone_id": request.zone_id})
        return parking_pb2.RegisterNodeResponse(success=True, message="registered")

    def Heartbeat(self, request, context):
        self._leader_only(context)
        with self.c.lock:
            node = self.c.nodes.get(request.node_id)
            if node is None:
                return parking_pb2.HeartbeatResponse(acknowledged=False, server_time=_now(), leader_id=self.c.id)
            was_offline = node.status == "OFFLINE"
            node.last_heartbeat = time.time()
            node.status = "ONLINE"
        if was_offline:
            self.c.log(f"{request.node_id} heartbeat resumed -> ONLINE")
        return parking_pb2.HeartbeatResponse(acknowledged=True, server_time=_now(), leader_id=self.c.id)

    # ---- parking ------------------------------------------------------------

    def FindParking(self, request, context):
        self._leader_only(context)
        c = self.c
        policy = request.policy if request.policy in config.POLICIES else c.current_policy()
        publish_event("PARKING_REQUESTED", source=c.node_id, data={"policy": policy})

        statuses = c.zone_statuses(c.online_nodes())
        ordered = c.policies.order(policy, statuses)
        c.log(f"FindParking[{policy}]: {[(s['node_id'], s['available']) for s in statuses]} -> try {[s['node_id'] for s in ordered]}")

        for s in ordered:
            node: NodeRecord = s["node"]
            reservation_id = f"RES-{node.zone_key}-{uuid.uuid4().hex[:8].upper()}"
            try:
                resp = zone_stub_for(node.zone_key).ReserveSlot(parking_pb2.ReserveSlotRequest(reservation_id=reservation_id), timeout=2)
            except grpc.RpcError as exc:
                c.log(f"RPC error contacting {node.node_id}: {exc.code()}")
                continue
            publish_event("RPC_CALL", source=c.node_id, data={
                "target": node.node_id, "method": "ReserveSlot()", "result": resp.slot_id if resp.success else "failed",
            })
            if not resp.success:
                continue

            price, price_source = c.quote_price(node.zone_key, s["available"] - 1, s["total"])
            publish_event("PARKING_RESERVED", source=node.node_id, data={
                "zone_id": node.zone_id, "slot_id": resp.slot_id, "reservation_id": reservation_id, "policy": policy,
            })
            publish_event("SLOT_STATUS_CHANGED", source=node.node_id, data={"slot_id": resp.slot_id, "status": "RESERVED"})
            return parking_pb2.FindParkingResponse(
                success=True, zone_id=node.zone_id, node_id=node.node_id, slot_id=resp.slot_id,
                reservation_id=reservation_id, message="Slot reserved", price_per_hour=price, price_source=price_source,
                policy=policy, served_by=c.node_id, lamport=clocks.get_clock().value(),
            )

        return self._book_overflow(policy)

    def _book_overflow(self, policy: str):
        """Every zone is full: fall back to the overflow lot shared by all zones.
        The leader hands the booking to a zone (rotating, like a car arriving at
        that zone's gate); the zone takes the lot under Ricart-Agrawala, because
        the other zones may be admitting cars to it at the same moment."""
        c = self.c
        nodes = sorted(c.online_nodes(), key=lambda n: n.node_id)
        if nodes:
            start = next(c.overflow_turn) % len(nodes)
            nodes = nodes[start:] + nodes[:start]
        for node in nodes:
            reservation_id = f"RES-OVF-{uuid.uuid4().hex[:8].upper()}"
            try:
                resp = zone_stub_for(node.zone_key).OverflowBook(
                    parking_pb2.OverflowBookRequest(use_mutex=True, booking_id=reservation_id), timeout=10)
            except grpc.RpcError as exc:
                c.log(f"RPC error contacting {node.node_id}: {exc.code()}")
                continue
            publish_event("RPC_CALL", source=c.node_id, data={
                "target": node.node_id, "method": "OverflowBook()", "result": "booked" if resp.success else resp.message,
            })
            if not resp.success:
                break  # the lot is shared: if it is full for one zone it is full for all

            price, price_source = c.quote_price("OVERFLOW", 0, 1)
            publish_event("PARKING_RESERVED", source=node.node_id, data={
                "zone_id": "OVERFLOW", "slot_id": "OVERFLOW", "reservation_id": reservation_id, "policy": "overflow",
            })
            return parking_pb2.FindParkingResponse(
                success=True, zone_id="OVERFLOW", node_id=node.node_id, slot_id="OVERFLOW",
                reservation_id=reservation_id, message="All zones full - overflow lot booked",
                price_per_hour=price, price_source=price_source, policy=policy,
                served_by=c.node_id, lamport=clocks.get_clock().value(),
            )

        return parking_pb2.FindParkingResponse(success=False, message="No available parking slots", policy=policy, served_by=c.node_id)

    def _release_overflow(self, reservation_id: str):
        c = self.c
        for node in sorted(c.online_nodes(), key=lambda n: n.node_id):  # any zone can release it
            try:
                ack = zone_stub_for(node.zone_key).OverflowRelease(
                    parking_pb2.OverflowReleaseRequest(booking_id=reservation_id), timeout=10)
            except grpc.RpcError:
                continue
            if ack.success:
                publish_event("PARKING_RELEASED", source=node.node_id, data={
                    "zone_id": "OVERFLOW", "slot_id": "OVERFLOW", "reservation_id": reservation_id,
                })
            return parking_pb2.ReleaseParkingResponse(success=ack.success, message=ack.message)
        return parking_pb2.ReleaseParkingResponse(success=False, message="No zone reachable to release the overflow slot")

    def ReleaseParking(self, request, context):
        self._leader_only(context)
        c = self.c
        if request.reservation_id.startswith("RES-OVF-"):
            return self._release_overflow(request.reservation_id)
        parts = request.reservation_id.split("-")
        zone_key = parts[1] if len(parts) == 3 and parts[1] in config.ZONES else None
        if zone_key is None:
            return parking_pb2.ReleaseParkingResponse(success=False, message="Unknown reservation id")
        cfg = config.ZONES[zone_key]
        try:
            resp = zone_stub_for(zone_key).ReleaseSlot(parking_pb2.ReleaseSlotRequest(reservation_id=request.reservation_id), timeout=2)
        except grpc.RpcError as exc:
            return parking_pb2.ReleaseParkingResponse(success=False, message=f"Zone unreachable: {exc.code()}")

        if resp.success:
            publish_event("PARKING_RELEASED", source=cfg["node_id"], data={
                "zone_id": cfg["zone_id"], "slot_id": resp.slot_id, "reservation_id": request.reservation_id,
            })
            publish_event("SLOT_STATUS_CHANGED", source=cfg["node_id"], data={"slot_id": resp.slot_id, "status": "AVAILABLE"})
        return parking_pb2.ReleaseParkingResponse(success=resp.success, message=resp.message)

    def GetSystemStatus(self, request, context):
        self._leader_only(context)
        with self.c.lock:
            snapshot = list(self.c.nodes.values())
        detail: dict[str, parking_pb2.ZoneStatusResponse] = {}

        def probe(node: NodeRecord):
            try:
                return node.node_id, zone_stub_for(node.zone_key).GetZoneStatus(parking_pb2.ZoneStatusRequest(), timeout=1.5)
            except grpc.RpcError:
                return node.node_id, None

        online = [n for n in snapshot if n.status == "ONLINE"]
        if online:
            with ThreadPoolExecutor(max_workers=len(online)) as pool:
                detail = {nid: st for nid, st in pool.map(probe, online) if st is not None}

        infos = []
        for node in snapshot:
            st = detail.get(node.node_id)
            infos.append(parking_pb2.NodeInfo(
                node_id=node.node_id, zone_id=node.zone_id, host=node.host, port=node.port, status=node.status,
                last_heartbeat=datetime.fromtimestamp(node.last_heartbeat, tz=timezone.utc).isoformat(),
                total_slots=node.total_slots,
                available_slots=st.available_slots if st else 0, occupied_slots=st.occupied_slots if st else 0,
                reserved_slots=st.reserved_slots if st else 0,
            ))
        status = self.c.election.status()
        return parking_pb2.SystemStatusResponse(nodes=infos, leader_id=status["leader_id"] or 0, term=status["term"])


def _now():
    return datetime.now(timezone.utc).isoformat()


def _heartbeat_monitor(c: Coordinator):
    while True:
        time.sleep(1)
        if c.failed or not c.election.is_leader:
            continue
        now = time.time()
        with c.lock:
            for node in c.nodes.values():
                if node.status == "ONLINE" and (now - node.last_heartbeat) > config.HEARTBEAT_TIMEOUT_SEC:
                    node.status = "OFFLINE"
                    c.log(f"{node.node_id} missed heartbeats -> OFFLINE")
                    publish_event("NODE_FAILED", source=c.node_id, data={"node_id": node.node_id, "zone_id": node.zone_id})


def serve(coord_id: int):
    clocks.init_clock()
    c = Coordinator(coord_id)

    server = make_server(max_workers=24)
    parking_pb2_grpc.add_CoordinatorServicer_to_server(CoordinatorServicer(c), server)
    server.add_insecure_port(f"{config.BIND_HOST}:{c.cfg['port']}")
    server.start()
    c.log(f"Starting on {config.BIND_HOST}:{c.cfg['port']} (election priority {c.id})")

    threading.Thread(target=_heartbeat_monitor, args=(c,), daemon=True).start()
    c.election.start()

    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        server.stop(0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int, default=int(os.environ.get("COORD_ID", 0)) or None, choices=config.coordinator_ids())
    args = parser.parse_args()
    if args.id is None:
        parser.error("--id (or COORD_ID env) is required")
    serve(args.id)
