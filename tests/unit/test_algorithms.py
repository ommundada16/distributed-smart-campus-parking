"""Unit tests for the Unit 3 / Unit 4 algorithm library, run against an in-memory
network (no gRPC, no Redis) so they need nothing else running."""

import os
import sys
import threading
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from distributed.berkeley import berkeley_adjustments, estimate_remote_diff
from distributed.clocks import LamportClock, ProcessClock, compare_vc
from distributed.election import BullyElection
from distributed.ledger import Ledger, make_block
from distributed.mutex import RicartAgrawala
from distributed.snapshot import ChandyLamport, FifoChannel


# ---- clocks -----------------------------------------------------------------

def test_lamport_receive_jumps_past_sender():
    a, b = LamportClock(), LamportClock()
    sent = a.tick()
    a.tick()
    sent = a.tick()  # a = 3
    assert b.update(sent) == 4
    assert b.tick() == 5


def test_vector_clock_detects_concurrency():
    a, b, c = ProcessClock("A"), ProcessClock("B"), ProcessClock("C")
    _, va = a.local_event()
    _, vb = b.local_event()
    assert compare_vc(va, vb) == "concurrent"

    lam, vsend = a.on_send()
    _, vc = c.on_receive(lam, vsend)
    assert compare_vc(va, vc) == "before"
    assert compare_vc(vc, va) == "after"
    assert compare_vc(vc, vb) == "concurrent"


# ---- berkeley ---------------------------------------------------------------

def test_berkeley_brings_all_clocks_to_the_average():
    offsets = {"M": 0.0, "A": 2.0, "B": -1.0}  # clock error vs master
    adj = berkeley_adjustments({"A": 2.0, "B": -1.0}, master="M")
    corrected = {n: offsets[n] + adj[n] for n in offsets}
    assert len({round(v, 9) for v in corrected.values()}) == 1
    assert abs(corrected["M"] - 1.0 / 3.0) < 1e-9


def test_berkeley_ignores_outlier_in_average():
    adj = berkeley_adjustments({"A": 0.1, "B": -0.1, "BAD": 500.0}, master="M", outlier_threshold=5.0)
    assert abs(adj["M"]) < 1e-9
    assert adj["BAD"] < -499


def test_cristian_estimate_compensates_half_rtt():
    assert abs(estimate_remote_diff(100.0, 10.0, 10.2, 10.2) - (100.1 - 10.2)) < 1e-9


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


# ---- Chandy-Lamport ---------------------------------------------------------

class _Bank:
    """Three nodes passing 'money' over delayed FIFO channels; total must stay 30."""

    def __init__(self, names, start=10):
        self.names = names
        self.balance = {n: start for n in names}
        self.cl: dict[str, ChandyLamport] = {}
        self.chan: dict[tuple[str, str], FifoChannel] = {}
        for n in names:
            peers = [p for p in names if p != n]
            self.cl[n] = ChandyLamport(n, peers, lambda n=n: self.balance[n], lambda p, sid, n=n: self.chan[(n, p)].post("marker", sid))
            for p in peers:
                self.chan[(n, p)] = FifoChannel(f"{n}->{p}", lambda kind, payload, n=n, p=p: self._deliver(n, p, kind, payload))

    def _deliver(self, src, dst, kind, payload):
        cl = self.cl[dst]
        if kind == "marker":
            cl.on_marker(payload, src)
        else:
            with cl.lock:
                self.balance[dst] += payload
                cl.on_message(src, payload)

    def transfer(self, src, dst, amount, delay):
        with self.cl[src].lock:
            self.balance[src] -= amount
            self.chan[(src, dst)].post("transfer", amount, delay)


def test_chandy_lamport_captures_in_flight_money():
    bank = _Bank(["A", "B", "C"])
    bank.transfer("B", "C", 3, delay=0.6)   # in flight when the snapshot starts
    time.sleep(0.1)
    bank.cl["A"].initiate("s1")
    deadline = time.time() + 5
    while time.time() < deadline and not all((bank.cl[n].get("s1") or {}).get("complete") for n in bank.names):
        time.sleep(0.05)

    snaps = [bank.cl[n].get("s1") for n in bank.names]
    assert all(s and s["complete"] for s in snaps)
    in_flight = sum(sum(msgs) for s in snaps for msgs in s["channels"].values())
    recorded = sum(s["state"] for s in snaps)
    assert in_flight == 3                  # the transfer was caught on channel B->C
    assert recorded == 27                  # naive sum of local states is wrong...
    assert recorded + in_flight == 30      # ...the snapshot is consistent


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
