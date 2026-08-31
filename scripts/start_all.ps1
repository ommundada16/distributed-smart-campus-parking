# Convenience launcher: starts every backend service, each as its own process,
# in its own PowerShell window. This is purely a demo convenience — the six
# services below are genuinely independent OS processes either way; running
# them from six manual terminals (as the FA-1 demo does) works identically.

$root = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $root "venv\Scripts\python.exe"

function Start-Service($title, $workdir, $command) {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$workdir'; $command" -WindowStyle Normal
}

docker compose -f (Join-Path $root "docker-compose.yml") up -d

Start-Sleep -Seconds 2

Start-Service "Coordinator" $root "& '$venvPython' -m services.coordinator.server"
Start-Sleep -Seconds 1
Start-Service "Zone A" $root "& '$venvPython' -m services.zone_a.main"
Start-Service "Zone B" $root "& '$venvPython' -m services.zone_b.main"
Start-Service "Zone C" $root "& '$venvPython' -m services.zone_c.main"
Start-Sleep -Seconds 1
Start-Service "Gateway" $root "& '$venvPython' -m uvicorn gateway.main:app --host localhost --port 8000"

Write-Host "All backend services launching in separate windows. Redis running via Docker Compose."
Write-Host "Next: cd frontend; npm run dev"
