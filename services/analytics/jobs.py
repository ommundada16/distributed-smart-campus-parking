"""MapReduce jobs over parking records (Unit 4: Apache Hadoop).

A record is {"zone": "PARKING_A", "hour": 0-23, "duration_min": float | None}.
All functions are top-level so they can be pickled to worker processes.
"""

import math
import random


# ---- job 1: bookings per (zone, hour) -> peak hours -------------------------------
def map_zone_hour(record):
    yield (f"{record['zone']}|{record['hour']:02d}", 1)


def combine_sum(_key, values):
    return sum(values)


def reduce_sum(_key, values):
    return sum(values)


# ---- job 2: total bookings per zone -------------------------------------------------
def map_zone(record):
    yield (record["zone"], 1)


# ---- job 3: average stay duration per zone (needs (sum, count) pairs) -----------------
def map_duration(record):
    if record.get("duration_min") is not None:
        yield (record["zone"], (record["duration_min"], 1))


def combine_avg(_key, values):
    return (sum(v[0] for v in values), sum(v[1] for v in values))


def reduce_avg(_key, values):
    total, count = sum(v[0] for v in values), sum(v[1] for v in values)
    return round(total / count, 2) if count else 0.0


JOBS = {
    "peak_hours": {"mapper": map_zone_hour, "combiner": combine_sum, "reducer": reduce_sum,
                   "title": "Bookings per zone per hour (peak-hour detection)"},
    "zone_load": {"mapper": map_zone, "combiner": combine_sum, "reducer": reduce_sum,
                  "title": "Total bookings per zone"},
    "avg_duration": {"mapper": map_duration, "combiner": combine_avg, "reducer": reduce_avg,
                     "title": "Average stay duration (minutes) per zone"},
}


def synthetic_records(n: int, seed: int = 7) -> list[dict]:
    """Realistic-looking campus demand: two daily peaks, Zone A most popular."""
    rng = random.Random(seed)
    hour_weights = [1, 1, 1, 1, 1, 2, 4, 8, 14, 12, 8, 7, 9, 10, 7, 6, 10, 13, 9, 5, 3, 2, 1, 1]
    zones = ["PARKING_A", "PARKING_B", "PARKING_C"]
    zone_weights = [5, 3, 2]
    hours = rng.choices(range(24), weights=hour_weights, k=n)
    zs = rng.choices(zones, weights=zone_weights, k=n)
    return [
        {"zone": z, "hour": h, "duration_min": round(max(10.0, rng.lognormvariate(math.log(95), 0.5)), 1)}
        for z, h in zip(zs, hours)
    ]
