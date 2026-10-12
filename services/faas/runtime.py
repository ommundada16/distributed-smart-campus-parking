"""A tiny local Function-as-a-Service platform (Unit 4: Serverless Architectures).

Mimics the parts of AWS Lambda / Cloudflare Workers that matter for the course:
  * functions are deployed as plain `handler(event, context)` modules
  * a function has no running instance until it is invoked  -> COLD start
    (module import + simulated runtime init), after which it stays WARM
  * after an idle period the instance is reclaimed          -> scale to zero
  * every invocation is metered: duration, billed ms, GB-seconds

Run:  uvicorn services.faas.runtime:app --port 9000
"""

import sys
import os
import importlib
import math
import threading
import time
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from fastapi import FastAPI, HTTPException

IDLE_TTL_SEC = float(os.environ.get("FAAS_IDLE_TTL", 30))
COLD_START_MS = int(os.environ.get("FAAS_COLD_START_MS", 350))

FUNCTIONS = {
    "pricing": {"module": "functions.pricing", "memory_mb": 128, "timeout_s": 3},
    "receipt": {"module": "functions.receipt", "memory_mb": 128, "timeout_s": 3},
}

app = FastAPI(title="Campus Parking FaaS runtime")
_lock = threading.Lock()
_state: dict[str, dict] = {
    name: {"handler": None, "last_used": 0.0, "invocations": 0, "cold_starts": 0, "total_ms": 0.0, "billed_ms": 0, "gb_seconds": 0.0}
    for name in FUNCTIONS
}


class Context:
    def __init__(self, name: str, memory_mb: int, timeout_s: int):
        self.function_name = name
        self.memory_limit_mb = memory_mb
        self.request_id = uuid.uuid4().hex[:12]
        self._deadline = time.time() + timeout_s

    def remaining_ms(self) -> int:
        return int(max(0.0, self._deadline - time.time()) * 1000)


def _is_warm(st: dict) -> bool:
    return st["handler"] is not None and (time.time() - st["last_used"]) < IDLE_TTL_SEC


@app.get("/health")
def health():
    return {"status": "ok", "service": "faas-runtime"}


@app.get("/functions")
def list_functions():
    out = []
    with _lock:
        for name, spec in FUNCTIONS.items():
            st = _state[name]
            idle = time.time() - st["last_used"] if st["last_used"] else None
            out.append({
                "name": name, "module": spec["module"], "memory_mb": spec["memory_mb"], "timeout_s": spec["timeout_s"],
                "state": "WARM" if _is_warm(st) else "COLD (scaled to zero)",
                "idle_seconds": round(idle, 1) if idle is not None else None,
                "idle_ttl_seconds": IDLE_TTL_SEC,
                "invocations": st["invocations"], "cold_starts": st["cold_starts"],
                "avg_ms": round(st["total_ms"] / st["invocations"], 2) if st["invocations"] else 0,
                "billed_ms": st["billed_ms"], "gb_seconds": round(st["gb_seconds"], 6),
            })
    return {"functions": out, "cold_start_ms": COLD_START_MS}


@app.post("/functions/{name}/evict")
def evict(name: str):
    if name not in FUNCTIONS:
        raise HTTPException(404, "no such function")
    with _lock:
        _state[name]["handler"] = None
    return {"evicted": name}


@app.post("/invoke/{name}")
def invoke(name: str, event: dict):
    spec = FUNCTIONS.get(name)
    if spec is None:
        raise HTTPException(404, f"function '{name}' is not deployed")

    t0 = time.perf_counter()
    cold = False
    with _lock:
        st = _state[name]
        if not _is_warm(st):
            cold = True
            module = importlib.import_module(spec["module"])
            time.sleep(COLD_START_MS / 1000.0)  # simulated container + runtime init
            st["handler"] = module.handler
            st["cold_starts"] += 1
        fn = st["handler"]
        st["last_used"] = time.time()

    context = Context(name, spec["memory_mb"], spec["timeout_s"])
    t1 = time.perf_counter()
    try:
        result = fn(event, context)
    except Exception as exc:  # a function error must never take the platform down
        raise HTTPException(500, f"function error: {exc}")
    run_ms = (time.perf_counter() - t1) * 1000
    total_ms = (time.perf_counter() - t0) * 1000

    billed = max(1, math.ceil(run_ms))  # Lambda bills 1 ms granularity on handler time
    with _lock:
        st["invocations"] += 1
        st["total_ms"] += total_ms
        st["billed_ms"] += billed
        st["gb_seconds"] += (spec["memory_mb"] / 1024.0) * (billed / 1000.0)

    return {
        "function": name, "request_id": context.request_id, "cold_start": cold,
        "duration_ms": round(total_ms, 2), "billed_ms": billed, "result": result,
    }
