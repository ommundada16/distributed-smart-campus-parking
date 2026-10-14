"""Batch analytics node: runs MapReduce jobs over booking history (Unit 4: Hadoop).

Input is either synthetic demand (to show the engine at scale) or the real
booking history read from the Redis event stream (PARKING_RESERVED / PARKING_RELEASED).

Run:  uvicorn services.analytics.service:app --port 9100
"""

import sys
import os
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from fastapi import FastAPI, HTTPException

from communication.messaging.message_bus import read_recent_events
from services.analytics.jobs import JOBS, synthetic_records
from services.analytics.mapreduce import run_mapreduce

app = FastAPI(title="Campus Parking analytics (MapReduce)")
_executor: ProcessPoolExecutor | None = None
_WORKERS = int(os.environ.get("ANALYTICS_WORKERS", 4))


def _get_executor() -> ProcessPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ProcessPoolExecutor(max_workers=_WORKERS)
    return _executor


def event_records() -> list[dict]:
    """Turn PARKING_RESERVED / PARKING_RELEASED events into booking records
    (duration comes from the matching release event)."""
    events = read_recent_events(2000)
    reserved: dict[str, dict] = {}
    durations: dict[str, float] = {}
    for e in events:
        data = e.get("data", {})
        rid = data.get("reservation_id")
        when = datetime.fromisoformat(e["timestamp"])
        if e["event"] == "PARKING_RESERVED" and rid:
            reserved[rid] = {"zone": data.get("zone_id", "?"), "ts": when}
        elif e["event"] == "PARKING_RELEASED" and rid in reserved:
            durations[rid] = (when - reserved[rid]["ts"]).total_seconds() / 60.0
    return [
        {"zone": r["zone"], "hour": r["ts"].hour, "duration_min": durations.get(rid)}
        for rid, r in reserved.items()
    ]


@app.get("/health")
def health():
    return {"status": "ok", "service": "analytics", "workers": _WORKERS}


@app.get("/jobs")
def jobs():
    return {"jobs": [{"name": n, "title": j["title"]} for n, j in JOBS.items()]}


@app.post("/run")
def run(job: str = "peak_hours", source: str = "synthetic", n: int = 200000, workers: int = 4, reducers: int = 2):
    if job not in JOBS:
        raise HTTPException(404, f"unknown job '{job}'")
    n = max(1, min(n, 2_000_000))
    records = synthetic_records(n) if source == "synthetic" else event_records()
    spec = JOBS[job]
    executor = _get_executor() if workers > 1 else None
    output, stats = run_mapreduce(
        records, spec["mapper"], spec["reducer"], spec["combiner"],
        num_mappers=workers, num_reducers=reducers, executor=executor,
    )

    if job == "peak_hours":
        per_zone: dict[str, dict[int, int]] = defaultdict(dict)
        for key, count in output.items():
            zone, hour = key.split("|")
            per_zone[zone][int(hour)] = count
        result = {z: {"histogram": [hours.get(h, 0) for h in range(24)],
                      "peak_hour": max(hours, key=hours.get) if hours else None} for z, hours in sorted(per_zone.items())}
    else:
        result = dict(sorted(output.items()))
    return {"job": job, "title": spec["title"], "source": source, "workers": workers, "result": result, "stats": stats}
