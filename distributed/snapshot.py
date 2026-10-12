"""Chandy-Lamport global state snapshot (Unit 3: Global State).

Records a consistent global state without stopping the system: each node's local
state plus the messages that were in flight on every channel when the snapshot
was taken. Requires FIFO channels, which `FifoChannel` provides.

Usage contract for callers: perform every local state change, every
`on_message` and every enqueue of an outgoing message while holding
`snapshot.lock`, so that "record my state" is atomic with respect to them.
"""

import queue
import threading
import time
from typing import Any, Callable


class FifoChannel:
    """One-directional, order-preserving channel to a peer. Messages (application
    messages and snapshot markers alike) are delivered strictly in the order posted,
    each after an optional simulated network delay."""

    def __init__(self, name: str, deliver: Callable[[str, Any], None]):
        self.name = name
        self._deliver = deliver
        self._queue: queue.Queue = queue.Queue()
        threading.Thread(target=self._run, daemon=True, name=f"channel-{name}").start()

    def post(self, kind: str, payload: Any, delay: float = 0.0):
        self._queue.put((kind, payload, delay))

    def _run(self):
        while True:
            kind, payload, delay = self._queue.get()
            if delay:
                time.sleep(delay)
            try:
                self._deliver(kind, payload)
            except Exception:
                pass  # peer unreachable: the message is lost, like a dropped packet


class ChandyLamport:
    def __init__(
        self,
        node_id: str,
        peers: list[str],
        capture_state: Callable[[], Any],
        send_marker: Callable[[str, str], None],
    ):
        self.node_id = node_id
        self.peers = list(peers)
        self._capture_state = capture_state
        self._send_marker = send_marker  # (peer, snapshot_id) -> enqueue only, must not block
        self.lock = threading.RLock()
        self.snapshots: dict[str, dict] = {}

    def initiate(self, snapshot_id: str):
        with self.lock:
            if snapshot_id not in self.snapshots:
                self._record(snapshot_id, via=None)

    def on_marker(self, snapshot_id: str, from_peer: str):
        with self.lock:
            if snapshot_id not in self.snapshots:
                # First marker: record state now; the channel it arrived on is empty.
                self._record(snapshot_id, via=from_peer)
            else:
                self.snapshots[snapshot_id]["recording"].discard(from_peer)
                self._maybe_complete(snapshot_id)

    def on_message(self, from_peer: str, message: Any):
        """Call for every application message received (after applying it)."""
        with self.lock:
            for snap in self.snapshots.values():
                if from_peer in snap["recording"]:
                    snap["channels"][from_peer].append(message)

    def get(self, snapshot_id: str) -> dict | None:
        with self.lock:
            snap = self.snapshots.get(snapshot_id)
            if snap is None:
                return None
            return {
                "node_id": self.node_id,
                "complete": snap["complete"],
                "state": snap["state"],
                "channels": {p: list(m) for p, m in snap["channels"].items()},
                "waiting_on": sorted(snap["recording"]),
            }

    # ---- internals -------------------------------------------------------

    def _record(self, snapshot_id: str, via: str | None):
        self.snapshots[snapshot_id] = {
            "state": self._capture_state(),
            "channels": {p: [] for p in self.peers},
            "recording": set(self.peers) - ({via} if via else set()),
            "complete": False,
        }
        for peer in self.peers:
            self._send_marker(peer, snapshot_id)
        self._maybe_complete(snapshot_id)

    def _maybe_complete(self, snapshot_id: str):
        snap = self.snapshots[snapshot_id]
        if not snap["recording"]:
            snap["complete"] = True
