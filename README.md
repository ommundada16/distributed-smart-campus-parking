# Distributed Smart Campus Parking System

B.Tech Distributed Systems project, built in two phases:

* **FA-1 (Units 1–2):** three parking zones coordinated by one coordinator, using RPC (gRPC), message-oriented (Redis Streams), stream-oriented (WebSocket) and P2P (TCP) communication, with heartbeat fault tolerance. Docs: [`docs/FA1_*.md`](docs/FA1_SYLLABUS_MAPPING.md).
* **FA-2 (Units 3–4, all units combined):** the same system, now with the problems that only exist *because* it is distributed — leader election with a beacon, mutual exclusion ordered by Lamport clocks, a replicated hash-chained ledger, load balancing, containers/Kubernetes, a serverless runtime and MapReduce analytics.

| Read this | For |
|---|---|
| [`docs/FA2_SYLLABUS_MAPPING.md`](docs/FA2_SYLLABUS_MAPPING.md) | Every syllabus topic → code → demo (and what is *not* implemented) |
| [`docs/FA2_ARCHITECTURE.md`](docs/FA2_ARCHITECTURE.md) | Architecture, server inventory & configuration, trade-offs (CAP), limitations |
| [`docs/FA2_DEMO.md`](docs/FA2_DEMO.md) | 12-minute demo script + likely viva questions |

## What FA-2 adds

| Topic | Implementation | Dashboard tab |
|---|---|---|
| Leader election + beacon (Unit 3) | 3 coordinator replicas, Bully election with terms — `distributed/election.py` | Leader Election |
| Lamport clock (Unit 3) | Orders Ricart-Agrawala requests; carried on every gRPC call by interceptors — `distributed/clocks.py` | Mutual Exclusion |
| Mutual exclusion (Unit 3) | Ricart-Agrawala across zones over the shared overflow lot, used when every zone is full — `distributed/mutex.py` | Mutual Exclusion |
| Blockchain / ledger (Unit 4) | Majority-committed, hash-chained replicated ledger — `distributed/ledger.py` | Ledger |
| Load balancing (Units 1, 4) | first-fit / round-robin / least-loaded policies; Nginx + K8s request balancing | Load Balancing, Cloud |
| Serverless (Unit 4) | Local FaaS runtime + Lambda-style functions — `services/faas`, `functions/` | Cloud |
| Hadoop (Unit 4) | Mini MapReduce with combiner — `services/analytics` | Cloud |
| Kubernetes / virtualization (Unit 4, Unit 1) | Docker Compose (12 containers with limits) + `k8s/` manifests | Cloud |

## Architecture

```
Browser → Nginx (round-robin LB, edge cache, UI) → gateway-1/2 → elected coordinator (1 of 3)
        → zone A / B / C  ⇄  zone-to-zone gRPC/TCP     Redis Streams (events) · FaaS · MapReduce
```

## Run it

### Option 1 — Docker Compose (recommended, the full 12-node deployment)

```bash
docker compose up --build -d
docker compose ps          # server inventory
```
Open **http://localhost:8080**. Stop with `docker compose down`.

### Option 2 — local processes (no containers except Redis)

```bash
python -m venv venv
venv\Scripts\pip install -r requirements.txt      # Windows   (source venv/bin/activate on macOS/Linux)
python scripts/run_local.py                        # starts Redis (Docker) + 9 Python processes
cd frontend && npm install && npm run dev          # in a second terminal
```
Open **http://localhost:5173**. Logs are written to `logs/`.

### Kubernetes (optional)

See the header of [`k8s/00-namespace-config.yaml`](k8s/00-namespace-config.yaml) (build the two images, load them into kind/minikube, `kubectl apply -f k8s/`).

## Tests

```bash
pytest tests/unit -v                                   # algorithms against an in-memory network, no services needed
pytest tests/test_integration.py -v                    # end-to-end against the running system (local mode)
GATEWAY_URL=http://localhost:8080 pytest tests/test_integration.py -v   # …or against Docker Compose
```

The integration suite exercises election/failover, mutual exclusion on/off, the overflow fallback when all zones are full, ledger tamper/repair, zone failure and ledger catch-up, allocation policies, serverless cold/warm start and MapReduce.

## Project structure

```
proto/parking.proto            gRPC interface (IDL) for coordinators and zones
distributed/                   Unit 3/4 algorithms, transport-independent and unit-tested
  clocks.py election.py mutex.py ledger.py
communication/                 middleware: grpc/ (+ clock interceptors), messaging/, p2p/, websocket/, discovery.py
services/
  coordinator/                 replica: election, registry, allocation policies, overflow fallback, ledger commit
  zone/                        slot service + overflow-lot mutex + ledger replica
  faas/  analytics/            serverless runtime, MapReduce engine and jobs
functions/                     Lambda-style handlers (pricing, receipt)
gateway/                       stateless FastAPI gateway (REST + WebSocket)
frontend/                      React dashboard — one tab per topic
deploy/                        Dockerfiles, nginx.conf, topology.json
k8s/                           Kubernetes manifests
tests/                         unit/ and integration tests
docs/                          FA-1 and FA-2 documentation
scripts/                       run_local.py, start_all.ps1
config.py                      topology, timing, env-overridable hosts
```
