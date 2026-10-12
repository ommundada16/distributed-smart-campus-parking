"""Berkeley clock synchronisation (Unit 3: Clock Synchronization).

A time daemon (the elected coordinator) polls every node for its clock,
compensates for round-trip delay, averages the readings and tells each node
by how much to adjust - nobody needs access to a "true" time source.
"""


def estimate_remote_diff(remote_time: float, t_send: float, t_recv: float, local_time_at_recv: float) -> float:
    """Cristian-style estimate of (remote clock - local clock).

    The remote reading was taken roughly half a round trip before we received it,
    so the remote clock "now" is remote_time + rtt/2.
    """
    rtt = t_recv - t_send
    return (remote_time + rtt / 2.0) - local_time_at_recv


def berkeley_adjustments(diffs: dict[str, float], master: str, outlier_threshold: float | None = None) -> dict[str, float]:
    """Given each node's clock difference relative to the master (master = 0.0),
    return how much each node must adjust its clock by.

    Nodes whose difference exceeds `outlier_threshold` are left out of the average
    (a faulty clock must not drag everyone else) but are still told to adjust.
    """
    readings = dict(diffs)
    readings[master] = 0.0
    trusted = [
        d for d in readings.values()
        if outlier_threshold is None or abs(d) <= outlier_threshold
    ] or list(readings.values())
    average = sum(trusted) / len(trusted)
    return {node: average - diff for node, diff in readings.items()}
