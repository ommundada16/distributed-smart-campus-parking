"""Logical and physical clocks (Unit 3: Clock Synchronization, Logical Clocks,
Lamport's Algorithm, Vector Algorithm).

* LamportClock   - scalar logical clock, gives a total order consistent with causality.
* VectorClock    - one counter per process, can tell "happened-before" apart from "concurrent".
* ProcessClock   - the pair kept by every node; stamped onto every outgoing message.
* PhysicalClock  - a node's wall clock with a deliberate skew, so the demo can show
                   why wall clocks are unreliable and what Berkeley sync fixes.
"""

import json
import threading
import time


class LamportClock:
    def __init__(self):
        self._lock = threading.Lock()
        self.time = 0

    def tick(self) -> int:
        """Local event or send: L = L + 1."""
        with self._lock:
            self.time += 1
            return self.time

    def update(self, received: int) -> int:
        """Receive: L = max(L, received) + 1."""
        with self._lock:
            self.time = max(self.time, int(received)) + 1
            return self.time

    def value(self) -> int:
        with self._lock:
            return self.time


class VectorClock:
    def __init__(self, node_id: str):
        self.node_id = node_id
        self._lock = threading.Lock()
        self.vc: dict[str, int] = {node_id: 0}

    def tick(self) -> dict[str, int]:
        with self._lock:
            self.vc[self.node_id] = self.vc.get(self.node_id, 0) + 1
            return dict(self.vc)

    def merge(self, other: dict[str, int]) -> dict[str, int]:
        """Receive: element-wise max, then tick own component."""
        with self._lock:
            for node, count in other.items():
                self.vc[node] = max(self.vc.get(node, 0), int(count))
            self.vc[self.node_id] = self.vc.get(self.node_id, 0) + 1
            return dict(self.vc)

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self.vc)


def compare_vc(a: dict[str, int], b: dict[str, int]) -> str:
    """Return 'before' (a -> b), 'after' (b -> a), 'equal' or 'concurrent'."""
    keys = set(a) | set(b)
    a_le_b = all(a.get(k, 0) <= b.get(k, 0) for k in keys)
    b_le_a = all(b.get(k, 0) <= a.get(k, 0) for k in keys)
    if a_le_b and b_le_a:
        return "equal"
    if a_le_b:
        return "before"
    if b_le_a:
        return "after"
    return "concurrent"


class ProcessClock:
    """Lamport + vector clock for one process."""

    def __init__(self, node_id: str):
        self.node_id = node_id
        self.lamport = LamportClock()
        self.vector = VectorClock(node_id)

    def local_event(self) -> tuple[int, dict[str, int]]:
        return self.lamport.tick(), self.vector.tick()

    def on_send(self) -> tuple[int, dict[str, int]]:
        return self.local_event()

    def on_receive(self, lamport: int, vc: dict[str, int]) -> tuple[int, dict[str, int]]:
        return self.lamport.update(lamport), self.vector.merge(vc)

    def peek(self) -> tuple[int, dict[str, int]]:
        return self.lamport.value(), self.vector.snapshot()


class PhysicalClock:
    """A wall clock with an adjustable offset (seconds) from true time."""

    def __init__(self, offset: float = 0.0):
        self._lock = threading.Lock()
        self.offset = offset

    def now(self) -> float:
        with self._lock:
            return time.time() + self.offset

    def adjust(self, delta: float) -> float:
        with self._lock:
            self.offset += delta
            return self.offset

    def set_offset(self, offset: float) -> float:
        with self._lock:
            self.offset = offset
            return self.offset


# ---- per-process singletons -------------------------------------------------

_process_clock: ProcessClock | None = None
physical_clock = PhysicalClock()


def init_clocks(node_id: str, skew_seconds: float = 0.0) -> ProcessClock:
    global _process_clock
    _process_clock = ProcessClock(node_id)
    physical_clock.set_offset(skew_seconds)
    return _process_clock


def get_process_clock() -> ProcessClock | None:
    return _process_clock


def encode_vc(vc: dict[str, int]) -> str:
    return json.dumps(vc, separators=(",", ":"), sort_keys=True)


def decode_vc(raw: str | None) -> dict[str, int]:
    if not raw:
        return {}
    try:
        return {k: int(v) for k, v in json.loads(raw).items()}
    except (ValueError, TypeError, AttributeError):
        return {}
