"""Ricart-Agrawala distributed mutual exclusion (Unit 3: Mutual Exclusion Algorithms).

No central lock server: to enter the critical section a node multicasts a
timestamped REQUEST to every peer and enters only after every peer has replied.
A peer replies at once unless it is inside the critical section, or wants it
with an earlier (Lamport timestamp, node id) pair - then it *defers* the reply
until it leaves. 2(N-1) messages per entry.

`send_request(peer, from_id, ts)` must block until that peer grants and return
True. If a peer is unreachable (crashed) the exception is treated as an implicit
grant - the usual fault-tolerant adaptation of the algorithm.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from distributed.clocks import LamportClock

RELEASED, WANTED, HELD = "RELEASED", "WANTED", "HELD"


class RicartAgrawala:
    def __init__(
        self,
        node_id: str,
        peers: list[str],
        send_request: Callable[[str, str, int], bool],
        lamport: LamportClock | None = None,
        trace: Callable[[str], None] | None = None,
    ):
        self.node_id = node_id
        self.peers = list(peers)
        self._send_request = send_request
        self.lamport = lamport or LamportClock()
        self._trace = trace or (lambda _msg: None)

        self._cond = threading.Condition()
        self.state = RELEASED
        self.my_ts = 0
        self._epoch = 0  # incremented at every release; deferred replies wait for it to change

    # ---- requesting side -------------------------------------------------

    def acquire(self):
        with self._cond:
            self.state = WANTED
            self.my_ts = self.lamport.tick()
            ts = self.my_ts
        self._trace(f"{self.node_id}: WANTED, REQUEST(ts={ts}) -> {', '.join(self.peers)}")

        def ask(peer: str):
            try:
                self._send_request(peer, self.node_id, ts)
                self._trace(f"{self.node_id}: REPLY received from {peer}")
            except Exception as exc:  # peer down -> implicit grant
                self._trace(f"{self.node_id}: {peer} unreachable ({type(exc).__name__}), treated as granted")

        if self.peers:
            with ThreadPoolExecutor(max_workers=len(self.peers)) as pool:
                list(pool.map(ask, self.peers))

        with self._cond:
            self.state = HELD
        self._trace(f"{self.node_id}: ENTER critical section")

    def release(self):
        with self._cond:
            self.state = RELEASED
            self._epoch += 1
            self._cond.notify_all()
        self._trace(f"{self.node_id}: EXIT critical section, deferred replies sent")

    def critical_section(self):
        return _CriticalSection(self)

    # ---- replying side ---------------------------------------------------

    def on_request(self, from_id: str, ts: int) -> bool:
        """Handle a peer's REQUEST. Blocks (defers the reply) when we have priority."""
        self.lamport.update(ts)
        with self._cond:
            must_defer = self.state == HELD or (
                self.state == WANTED and (self.my_ts, self.node_id) < (ts, from_id)
            )
            if must_defer:
                self._trace(f"{self.node_id}: DEFER reply to {from_id} (state={self.state}, mine={self.my_ts}, theirs={ts})")
                epoch = self._epoch
                while self._epoch == epoch:
                    self._cond.wait(timeout=0.5)
            else:
                self._trace(f"{self.node_id}: immediate REPLY to {from_id} (state={self.state}, theirs={ts})")
        return True


class _CriticalSection:
    def __init__(self, ra: RicartAgrawala):
        self.ra = ra

    def __enter__(self):
        self.ra.acquire()
        return self

    def __exit__(self, *exc):
        self.ra.release()
        return False
