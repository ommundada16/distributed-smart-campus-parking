"""Lamport logical clock (Unit 3: Logical Clocks, Lamport's Algorithm).

The one clock the system needs: Ricart-Agrawala orders competing requests for
the shared overflow lot by (Lamport timestamp, node id). Every node keeps one,
and the gRPC middleware carries it on every call.

Nothing here depends on wall-clock time, so no physical clock synchronisation
is needed, and no decision depends on telling concurrent events apart, so no
vector clock is needed either.
"""

import threading


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


# ---- per-process singleton --------------------------------------------------

_clock: LamportClock | None = None


def init_clock() -> LamportClock:
    global _clock
    _clock = LamportClock()
    return _clock


def get_clock() -> LamportClock | None:
    return _clock
