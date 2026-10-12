"""Start the whole backend as separate local OS processes (no Docker needed except for Redis).

    python scripts/run_local.py            # start everything, Ctrl-C stops it all
    python scripts/run_local.py --no-redis # Redis already running

Each service logs to logs/<name>.log. The React dev server is separate:
    cd frontend && npm run dev
"""

import argparse
import os
import signal
import subprocess
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LOGS = os.path.join(ROOT, "logs")

SERVICES = [
    ("coord-1", ["-m", "services.coordinator.server", "--id", "1"]),
    ("coord-2", ["-m", "services.coordinator.server", "--id", "2"]),
    ("coord-3", ["-m", "services.coordinator.server", "--id", "3"]),
    ("zone-a", ["-m", "services.zone.zone_service", "--zone", "A"]),
    ("zone-b", ["-m", "services.zone.zone_service", "--zone", "B"]),
    ("zone-c", ["-m", "services.zone.zone_service", "--zone", "C"]),
    ("faas", ["-m", "uvicorn", "services.faas.runtime:app", "--port", "9000"]),
    ("analytics", ["-m", "uvicorn", "services.analytics.service:app", "--port", "9100"]),
    ("gateway", ["-m", "gateway.main"]),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-redis", action="store_true")
    args = parser.parse_args()

    if not args.no_redis:
        subprocess.run(["docker", "compose", "up", "-d", "redis"], cwd=ROOT, check=True)
        time.sleep(2)

    os.makedirs(LOGS, exist_ok=True)
    procs = []
    for name, argv in SERVICES:
        log = open(os.path.join(LOGS, f"{name}.log"), "w", encoding="utf-8")
        env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONPATH=ROOT)
        proc = subprocess.Popen([sys.executable, *argv], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, env=env)
        procs.append((name, proc))
        print(f"started {name:10s} pid={proc.pid}")
        time.sleep(0.3)

    print("\nAll services started. Logs in ./logs  -  Ctrl-C to stop everything.")

    def stop(*_):
        for name, proc in procs:
            proc.terminate()
        for _, proc in procs:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        sys.exit(0)

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    while True:
        time.sleep(1)
        for name, proc in procs:
            if proc.poll() is not None:
                print(f"!! {name} exited with code {proc.returncode} (see logs/{name}.log)")
                procs.remove((name, proc))
                break


if __name__ == "__main__":
    main()
