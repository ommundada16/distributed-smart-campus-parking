"""Zone-allocation (load-balancing) policies used by the coordinator leader.

first_fit     FA-1 baseline: walk the zones in registry order and take the first
              one with space. Simple, but piles every request onto Zone A until
              it is full while B and C sit idle.
round_robin   Rotate the starting zone on every request - even spread of *requests*
              regardless of how full each zone is.
least_loaded  Pick the zone with the lowest occupancy ratio - spreads *load*, and
              steers traffic away from nearly-full zones.
"""

import itertools


class Policies:
    def __init__(self):
        self._rr = itertools.count()

    def order(self, policy: str, statuses: list[dict]) -> list[dict]:
        """`statuses`: dicts with node_id, available, total (zones with available > 0 only).
        Returns them best-first; the coordinator tries them in this order."""
        candidates = sorted((s for s in statuses if s["available"] > 0), key=lambda s: s["node_id"])
        if not candidates:
            return []
        if policy == "first_fit":
            return candidates
        if policy == "round_robin":
            start = next(self._rr) % len(candidates)
            return candidates[start:] + candidates[:start]
        # least_loaded (default): lowest occupancy first, ties broken by name
        return sorted(candidates, key=lambda s: ((s["total"] - s["available"]) / max(s["total"], 1), s["node_id"]))
