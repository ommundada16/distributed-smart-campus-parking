# Distributed Smart Campus Parking System

A B.Tech Distributed Systems FA-1 mini project: real-time parking allocation and
monitoring across three independent parking zones, coordinated by a central
coordinator, using four distinct communication styles (RPC, message-oriented,
stream-oriented, and P2P).

See [`docs/FA1_SYLLABUS_MAPPING.md`](docs/FA1_SYLLABUS_MAPPING.md) for exactly
which syllabus concepts this implements, [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
for the full architecture, [`docs/COMMUNICATION.md`](docs/COMMUNICATION.md) for
how/why each communication style is used, and [`docs/FA1_DEMO.md`](docs/FA1_DEMO.md)
for a step-by-step demo script.

## Tech stack

- Python, gRPC + Protocol Buffers (RPC), Redis Streams (messaging), FastAPI +
  WebSockets (streaming), raw TCP sockets (P2P)
- React + Vite — one single-page dashboard, no router (frontend)
- Docker Compose — Redis only; every other service runs as a plain OS process
- No database — each zone keeps its slots in an in-memory Python dict; not a
  Unit 1/2 topic, so it was left out to keep the codebase small

## Project structure

```
distributed-parking/
├── proto/parking.proto        # gRPC service + message definitions
├── communication/             # middleware: grpc/, messaging/, p2p/, websocket/
├── services/
│   ├── coordinator/           # central coordinator (node registry, heartbeat monitor)
│   ├── zone/                  # shared zone implementation (in-memory slot state)
│   ├── zone_a/ zone_b/ zone_c/  # thin per-zone launchers
├── gateway/                   # FastAPI API gateway (only HTTP-facing service)
├── frontend/                  # React + Vite client — one page, one App.jsx
├── tests/                     # integration smoke tests
├── docs/                      # FA-1 documentation
├── config.py                  # single source of truth for ports/topology
└── docker-compose.yml         # Redis only
```

## Setup

```bash
cd distributed-parking
python -m venv venv
venv\Scripts\pip install -r requirements.txt   # Windows
# source venv/bin/activate && pip install -r requirements.txt   # macOS/Linux

cd frontend
npm install
cd ..
```

## Running it

Start Redis:
```bash
docker compose up -d
```

Then either run [`scripts/start_all.ps1`](scripts/start_all.ps1) (Windows,
PowerShell — opens one window per service), or start each of these in its own
terminal, in order:

```bash
venv\Scripts\python -m services.coordinator.server
venv\Scripts\python -m services.zone_a.main
venv\Scripts\python -m services.zone_b.main
venv\Scripts\python -m services.zone_c.main
venv\Scripts\python -m uvicorn gateway.main:app --host localhost --port 8000
```

Then the frontend:
```bash
cd frontend
npm run dev
```

Open `http://localhost:5173`.

## Running the tests

With the full system already running (see above):
```bash
venv\Scripts\python -m pytest tests/ -v
```

## Architecture at a glance

```
React Client → API Gateway (HTTP/WS) → Coordinator (gRPC) → Zone A/B/C (gRPC)
                                                                  ↕ P2P (TCP)
All services → Redis Streams (parking_events) → Gateway's event bridge → WebSocket → React
```

## FA-1 features implemented

- **Unit 1:** distributed architecture, design issues, middleware abstraction,
  model of distributed computation, role of virtualization (Redis only)
- **Unit 2:** RPC (gRPC), message-oriented communication (Redis Streams),
  stream-oriented communication (WebSocket), P2P messaging (TCP sockets),
  names/identifiers/addresses, fault tolerance (heartbeat + failover)

Full mapping: [`docs/FA1_SYLLABUS_MAPPING.md`](docs/FA1_SYLLABUS_MAPPING.md).

Deliberately **not** implemented: Unit 3/4 topics (Lamport/vector clocks, leader
election, mutual exclusion, deadlock detection, Hadoop, Kubernetes, blockchain),
distributed multimedia, and WebRTC — see the syllabus mapping doc for why.
