"""Bully leader election with a leader beacon (Unit 3: Election Algorithms, beacon protocol).

The live process with the highest id is the leader.
  * A node that suspects the leader is gone sends ELECTION to every higher id.
  * Any live higher node answers OK and runs its own election (it "bullies" the sender).
  * If nobody higher answers, the node declares itself leader and sends ANNOUNCE(term).
  * The leader sends a periodic BEACON; followers that miss beacons for `beacon_timeout`
    start an election. A beacon answered with a higher term makes a stale leader step down.

`term` is a monotonically increasing epoch, so a recovered ex-leader cannot
resurrect itself over a newer leader (split-brain protection).
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable


class BullyElection:
    def __init__(
        self,
        my_id: int,
        all_ids: list[int],
        send_election: Callable[[int], bool],
        send_announce: Callable[[int, int, int], None],
        send_beacon: Callable[[int, int, int], tuple[int, int] | None],
        on_leader_change: Callable[[int | None, int, bool], None] | None = None,
        is_alive: Callable[[], bool] = lambda: True,
        beacon_interval: float = 1.0,
        beacon_timeout: float = 4.0,
        announce_wait: float = 2.0,
        startup_delay: float = 1.0,
        fetch_term: Callable[[int], int | None] | None = None,
        log: Callable[[str], None] | None = None,
    ):
        self.my_id = my_id
        self.peers = [i for i in all_ids if i != my_id]
        self._send_election = send_election
        self._send_announce = send_announce
        self._send_beacon = send_beacon
        self._on_leader_change = on_leader_change or (lambda *_: None)
        self._is_alive = is_alive
        self.beacon_interval = beacon_interval
        self.beacon_timeout = beacon_timeout
        self.announce_wait = announce_wait
        self.startup_delay = startup_delay
        self._fetch_term = fetch_term
        self._log = log or (lambda _msg: None)

        self._lock = threading.RLock()
        self.leader_id: int | None = None
        self.term = 0
        self.last_beacon = time.time()
        self._announce_seq = 0
        self._electing = False
        self._running = False
        self._last_beacon_sent = 0.0

    # ---- lifecycle -------------------------------------------------------

    def start(self):
        self._running = True
        threading.Thread(target=self._monitor, daemon=True, name=f"election-{self.my_id}").start()
        threading.Thread(target=self._delayed_first_election, daemon=True).start()

    def stop(self):
        self._running = False

    def _delayed_first_election(self):
        time.sleep(self.startup_delay)
        if self.leader_id is None:
            self.start_election("startup")

    def reset_after_recovery(self):
        """Called when a failed node comes back: forget stale leadership and re-elect."""
        with self._lock:
            self.leader_id = None
            self.last_beacon = time.time()
        threading.Thread(target=self.start_election, args=("recovered",), daemon=True).start()

    @property
    def is_leader(self) -> bool:
        return self.leader_id == self.my_id

    def status(self) -> dict:
        with self._lock:
            return {"leader_id": self.leader_id, "term": self.term, "is_leader": self.is_leader}

    # ---- election --------------------------------------------------------

    def start_election(self, reason: str = ""):
        with self._lock:
            if self._electing or not self._is_alive():
                return
            self._electing = True
        try:
            self._log(f"election started ({reason})")
            while self._running and self._is_alive():
                higher = [i for i in self.peers if i > self.my_id]
                answered = self._probe(higher)
                if not answered:
                    self._become_leader()
                    return
                self._log(f"higher node(s) {answered} answered OK; waiting for their ANNOUNCE")
                seq = self._announce_seq
                deadline = time.time() + self.announce_wait
                while time.time() < deadline:
                    if self._announce_seq != seq:
                        return
                    time.sleep(0.05)
                self._log("no ANNOUNCE arrived; retrying election")
        finally:
            with self._lock:
                self._electing = False

    def _probe(self, ids: list[int]) -> list[int]:
        if not ids:
            return []

        def ask(i: int):
            try:
                return i if self._send_election(i) else None
            except Exception:
                return None

        with ThreadPoolExecutor(max_workers=len(ids)) as pool:
            return [i for i in pool.map(ask, ids) if i is not None]

    def _learn_terms(self):
        """Ask every peer for its current term so a freshly restarted node (term 0)
        still declares a term higher than the one in force."""
        if not self._fetch_term or not self.peers:
            return

        def ask(i: int):
            try:
                return self._fetch_term(i)
            except Exception:
                return None

        with ThreadPoolExecutor(max_workers=len(self.peers)) as pool:
            terms = [t for t in pool.map(ask, self.peers) if t is not None]
        with self._lock:
            self.term = max([self.term] + terms)

    def _become_leader(self):
        self._learn_terms()
        with self._lock:
            self.term += 1
            self.leader_id = self.my_id
            self.last_beacon = time.time()
            term = self.term
        self._log(f"no higher node alive -> I am leader (term {term})")

        def tell(i: int):
            try:
                self._send_announce(i, self.my_id, term)
            except Exception:
                pass

        if self.peers:
            with ThreadPoolExecutor(max_workers=len(self.peers)) as pool:
                list(pool.map(tell, self.peers))
        self._last_beacon_sent = 0.0
        self._on_leader_change(self.my_id, term, True)

    # ---- incoming messages -----------------------------------------------

    def handle_election(self, from_id: int) -> bool:
        if not self._is_alive():
            return False
        if from_id < self.my_id:
            threading.Thread(target=self.start_election, args=(f"bullied by {from_id}",), daemon=True).start()
        return True

    def handle_announce(self, leader_id: int, term: int) -> bool:
        with self._lock:
            if term < self.term or (term == self.term and self.leader_id is not None and leader_id < self.leader_id):
                return False
            changed = self.leader_id != leader_id or self.term != term
            self.leader_id, self.term = leader_id, term
            self.last_beacon = time.time()
            self._announce_seq += 1
        if changed:
            self._log(f"accepted leader {leader_id} (term {term})")
            self._on_leader_change(leader_id, term, leader_id == self.my_id)
        return True

    def handle_beacon(self, leader_id: int, term: int) -> tuple[int | None, int]:
        with self._lock:
            if term < self.term:
                return self.leader_id, self.term  # sender is a stale leader
            was = (self.leader_id, self.term)
            if leader_id < self.my_id and self._is_alive():
                self.term = max(self.term, term)
                # A live node with a higher id exists (me): take over.
                threading.Thread(target=self.start_election, args=("beacon from lower id",), daemon=True).start()
                return self.leader_id, self.term
            self.leader_id, self.term = leader_id, term
            self.last_beacon = time.time()
            changed = was != (leader_id, term)
        if changed:
            self._on_leader_change(leader_id, term, leader_id == self.my_id)
        return leader_id, term

    # ---- background loop -------------------------------------------------

    def _monitor(self):
        while self._running:
            time.sleep(0.2)
            if not self._is_alive():
                continue
            now = time.time()
            if self.is_leader:
                if now - self._last_beacon_sent >= self.beacon_interval:
                    self._last_beacon_sent = now
                    threading.Thread(target=self._send_beacons, daemon=True).start()
            elif self.leader_id is not None and now - self.last_beacon > self.beacon_timeout:
                self._log(f"leader {self.leader_id} missed beacons for {self.beacon_timeout}s")
                with self._lock:
                    self.leader_id = None
                self._on_leader_change(None, self.term, False)
                self.start_election("leader timeout")
            elif self.leader_id is None and now - self.last_beacon > self.beacon_timeout + self.announce_wait:
                self.start_election("no leader known")

    def _send_beacons(self):
        def beacon(i: int):
            try:
                return self._send_beacon(i, self.my_id, self.term)
            except Exception:
                return None

        if not self.peers:
            return
        with ThreadPoolExecutor(max_workers=len(self.peers)) as pool:
            replies = list(pool.map(beacon, self.peers))
        for reply in replies:
            if reply and reply[1] > self.term:
                with self._lock:
                    self.leader_id, self.term = reply[0], reply[1]
                    self.last_beacon = time.time()
                self._log(f"stepping down: saw term {reply[1]} led by {reply[0]}")
                self._on_leader_change(reply[0], reply[1], reply[0] == self.my_id)
                return
