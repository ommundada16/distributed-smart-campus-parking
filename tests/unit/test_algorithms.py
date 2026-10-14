"""Unit tests for the Unit 3 / Unit 4 algorithm library, run against an in-memory
network (no gRPC, no Redis) so they need nothing else running."""

import os
import sys
import threading
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from distributed.clocks import LamportClock
from distributed.election import BullyElection
from distributed.ledger import Ledger, make_block
from distributed.mutex import WANTED, RicartAgrawala


# ---- Lamport clock ----------------------------------------------------------

def test_lamport_receive_jumps_past_sender():
    a, b = LamportClock(), LamportClock()
    sent = a.tick()
    a.tick()
    sent = a.tick()  # a = 3
    assert b.update(sent) == 4
    assert b.tick() == 5


# ---- ledger -----------------------------------------------------------------

def test_ledger_chain_validates_and_detects_tampering():
    ledger = Ledger()
    for i in range(3):
        ok, _ = ledger.append(make_block(ledger.head(), {"type": "RESERVE", "n": i}, lamport=i, timestamp=float(i)))
        assert ok
    assert ledger.verify() == (True, -1)
    assert ledger.tamper(2)
    assert ledger.verify() == (False, 2)


def test_ledger_rejects_gap_and_bad_prev_hash():
    ledger = Ledger()
    b1 = make_block(ledger.head(), {"x": 1}, 1, 1.0)
    b2 = make_block(b1, {"x": 2}, 2, 2.0)
    assert ledger.append(b2)[0] is False  # gap
    assert ledger.append(b1)[0] is True
    other = Ledger()
    fork = make_block(other.head(), {"x": "fork"}, 1, 1.0)
    assert ledger.append(fork) == (False, "conflict: different block already at this index")


# ---- Ricart-Agrawala --------------------------------------------------------

def _build_ra_cluster(names, dead=()):
    nodes: dict[str, RicartAgrawala] = {}

    def make_sender(src):
        def send(peer, from_id, ts):
            if peer in dead:
                raise ConnectionError("down")
            return nodes[peer].on_request(from_id, ts)
        return send

    for n in names:
        nodes[n] = RicartAgrawala(n, [p for p in names if p != n], make_sender(n))
    return nodes


def test_ricart_agrawala_guarantees_mutual_exclusion():
    nodes = _build_ra_cluster(["A", "B", "C"])
    inside, max_inside, counter = [0], [0], [0]
    guard = threading.Lock()

    def worker(name):
        for _ in range(4):
            with nodes[name].critical_section():
                with guard:
                    inside[0] += 1
                    max_inside[0] = max(max_inside[0], inside[0])
                v = counter[0]
                time.sleep(0.01)
                counter[0] = v + 1  # read-modify-write: loses updates unless exclusive
                with guard:
                    inside[0] -= 1

    threads = [threading.Thread(target=worker, args=(n,)) for n in nodes]
    [t.start() for t in threads]
    [t.join(timeout=30) for t in threads]
    assert max_inside[0] == 1
    assert counter[0] == 12


def test_ricart_agrawala_survives_a_dead_peer():
    nodes = _build_ra_cluster(["A", "B", "C"], dead={"C"})
    with nodes["A"].critical_section():
        pass
    with nodes["B"].critical_section():
        pass


def test_ricart_agrawala_earlier_lamport_timestamp_has_priority():
    a = RicartAgrawala("A", ["B"], send_request=lambda *_: True)
    a.state, a.my_ts = WANTED, 5             # A is waiting to enter, its REQUEST stamped at Lamport time 5

    assert a.on_request("B", 3) is True      # B asked earlier (3 < 5): A replies at once

    replied = threading.Event()
    threading.Thread(target=lambda: (a.on_request("B", 7), replied.set()), daemon=True).start()
    assert not replied.wait(0.3)             # B asked later (7 > 5): A defers its reply...
    a.release()
    assert replied.wait(2)                   # ...and sends it when it leaves


# ---- Bully election ---------------------------------------------------------

class _ElectionNet:
    def __init__(self, ids):
        self.alive = {i: True for i in ids}
        self.nodes: dict[int, BullyElection] = {}
        for i in ids:
            self.nodes[i] = BullyElection(
                i, ids,
                send_election=lambda to, i=i: self._call(i, to, lambda n: n.handle_election(i)),
                send_announce=lambda to, lid, term, i=i: self._call(i, to, lambda n: n.handle_announce(lid, term)),
                send_beacon=lambda to, lid, term, i=i: self._call(i, to, lambda n: n.handle_beacon(lid, term)),
                fetch_term=lambda to, i=i: self._call(i, to, lambda n: n.term),
                is_alive=lambda i=i: self.alive[i],
                beacon_interval=0.2, beacon_timeout=0.8, announce_wait=0.6, startup_delay=0.1,
            )

    def _call(self, src, dst, fn):
        if not self.alive[dst] or not self.alive[src]:
            raise ConnectionError("down")
        return fn(self.nodes[dst])

    def start(self):
        for n in self.nodes.values():
            n.start()

    def stop(self):
        for n in self.nodes.values():
            n.stop()

    def wait_for_leader(self, expected, among, timeout=8.0):
        end = time.time() + timeout
        while time.time() < end:
            if all(self.nodes[i].leader_id == expected for i in among):
                return True
            time.sleep(0.05)
        return False


def test_bully_elects_highest_then_fails_over_and_recovers():
    net = _ElectionNet([1, 2, 3])
    net.start()
    try:
        assert net.wait_for_leader(3, [1, 2, 3]), "node 3 should win the initial election"

        net.alive[3] = False                       # leader crashes
        assert net.wait_for_leader(2, [1, 2]), "node 2 should take over"
        term_after_failover = net.nodes[2].term
        assert term_after_failover > 1

        net.alive[3] = True                        # ex-leader recovers and bullies its way back
        net.nodes[3].reset_after_recovery()
        assert net.wait_for_leader(3, [1, 2, 3]), "recovered node 3 should regain leadership"
        assert net.nodes[3].term > term_after_failover
    finally:
        net.stop()
