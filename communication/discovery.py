"""Leader discovery (Unit 2: names, identifiers and addresses; Unit 3: election).

Clients never hardcode "the coordinator". They hold the *names* of the replicas
(config.COORDINATORS), ask any live one WhoIsLeader, and resolve the answer to
an address. When the leader changes, the next failed call triggers re-discovery.
"""

import threading
import time

import grpc

import config
from communication.grpc import parking_pb2
from communication.grpc.grpc_client import replica_stub


class NoLeaderError(Exception):
    pass


class LeaderLocator:
    def __init__(self):
        self._lock = threading.Lock()
        self._leader_id: int | None = None

    @property
    def cached(self) -> int | None:
        return self._leader_id

    def discover(self) -> int | None:
        """Ask every replica (highest id first) who the leader is; trust the highest term."""
        best = (-1, None)  # (term, leader_id)
        for coord_id in sorted(config.COORDINATORS, reverse=True):
            try:
                info = replica_stub(coord_id).WhoIsLeader(parking_pb2.Empty(), timeout=1.0)
            except grpc.RpcError:
                continue
            if info.leader_id > 0 and info.term > best[0]:
                best = (info.term, info.leader_id)
        with self._lock:
            self._leader_id = best[1]
        return best[1]

    def call(self, method: str, request, timeout: float = 5.0, attempts: int = 3, pause: float = 0.7):
        """Invoke `method` on the current leader, re-discovering it on failure."""
        last_error = None
        for attempt in range(attempts):
            leader = self._leader_id or self.discover()
            if leader is None:
                last_error = NoLeaderError("no leader elected yet")
                time.sleep(pause)
                continue
            try:
                return getattr(replica_stub(leader), method)(request, timeout=timeout)
            except grpc.RpcError as exc:
                last_error = exc
                if exc.code() not in (grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.FAILED_PRECONDITION,
                                      grpc.StatusCode.DEADLINE_EXCEEDED):
                    raise
                with self._lock:
                    self._leader_id = None
                time.sleep(pause)
        raise last_error if last_error else NoLeaderError("no leader")
