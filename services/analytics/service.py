"""Batch analytics node: runs MapReduce jobs over booking history (Unit 4: Hadoop).

Input is either synthetic demand (to show the engine at scale) or the real
booking history read from the replicated ledger on the zones.

Run:  uvicorn services.analytics.service:app --port 9100
"""

import sys
import os
import json
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import grpc
from fastapi import FastAPI, HTTPException

import config
from communication.grpc import parking_pb2
from communication.grpc.grpc_client import zone_stub_for
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


def ledger_records() -> list[dict]:
    """Turn RESERVE/RELEASE blocks into booking records (duration from the matching RELEASE)."""
    chain = None
    for key in config.ZONES:
        try:
            resp = zone_stub_for(key).GetBlocks(parking_pb2.GetBlocksRequest(from_index=0), timeout=3)
            chain = [json.loads(b) for b in resp.blocks_json]
            break
        except grpc.RpcError:
            continue
    if chain is None:
        raise HTTPException(503, "no zone reachable to read the ledger")

    reserved: dict[str, dict] = {}
    durations: dict[str, float] = {}
    for block in chain:
        tx = block["tx"]
        if tx.get("type") == "RESERVE":
            reserved[tx["reservation_id"]] = {"zone": tx["zone_id"], "ts": block["timestamp"]}
        elif tx.get("type") == "RELEASE" and tx.get("reservation_id") in reserved:
            durations[tx["reservation_id"]] = (block["timestamp"] - reserved[tx["reservation_id"]]["ts"]) / 60.0
    return [
        {"zone": r["zone"], "hour": datetime.fromtimestamp(r["ts"], tz=timezone.utc).hour, "duration_min": durations.get(rid)}
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
    records = synthetic_records(n) if source == "synthetic" else ledger_records()
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
