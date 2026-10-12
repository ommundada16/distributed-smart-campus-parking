# Convenience launcher for the local (non-container) mode: starts Redis via Docker Compose and
# every Python service as its own OS process (3 coordinator replicas, 3 zones, FaaS, analytics, gateway).
#
# Logs go to ./logs. Press Ctrl+C to stop everything. Then, in another terminal:
#     cd frontend; npm run dev
#
# For the full containerised deployment use:  docker compose up --build -d

$root = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $root "venv\Scripts\python.exe"

& $venvPython (Join-Path $PSScriptRoot "run_local.py")
