# Architecture

## Diagram

```
                  ┌─────────────────┐
                  │   React Client   │  (Dashboard / Find Parking / My Reservation / System Monitor)
                  └────────┬─────────┘
                           │ HTTP + WebSocket
                  ┌────────▼─────────┐
                  │   API Gateway     │  FastAPI, port 8000
                  └────────┬─────────┘
                           │ gRPC (RPC)
                  ┌────────▼─────────┐
                  │    Coordinator    │  port 5000
                  │  (node registry,  │
                  │  heartbeat monitor)│
                  └───┬─────────┬────┘
                      │ gRPC    │ gRPC
               ┌──────▼──┐   ┌──▼───────┐   ┌──────────┐
               │ Zone A  │   │  Zone B  │   │  Zone C  │
               │ :5001   │◄─►│  :5002   │◄─►│  :5003   │   (P2P over raw TCP)
               └────┬────┘   └────┬─────┘   └────┬─────┘
                    │              │              │
                    └──── each zone owns its own SQLite rows ────┘
                                   │
                    all 3 processes publish to
                                   ▼
                            Redis Streams
                          (parking_events)
                                   │
                     consumed independently by
                                   ▼
                          API Gateway's event
                              bridge thread
                                   │
                                   ▼
                         WebSocket (/ws) → React UI
```

## Processes (6 independent OS processes + Redis)

| # | Process | Command | Port(s) |
|---|---|---|---|
| 1 | Coordinator | `python -m services.coordinator.server` | gRPC 5000 |
| 2 | Zone A | `python -m services.zone_a.main` | gRPC 5001, P2P TCP 6001 |
| 3 | Zone B | `python -m services.zone_b.main` | gRPC 5002, P2P TCP 6002 |
| 4 | Zone C | `python -m services.zone_c.main` | gRPC 5003, P2P TCP 6003 |
| 5 | API Gateway | `uvicorn gateway.main:app --port 8000` | HTTP/WS 8000 |
| 6 | React frontend | `npm run dev` (in `frontend/`) | 5173 |
| — | Redis (message broker) | `docker compose up -d` | 6379 |

Each zone is the **same code** (`services/zone/zone_service.py`), launched with a
different `--zone` argument, but each runs as its own process with its own gRPC
server, its own TCP P2P listener, and its own heartbeat thread — they do not share
memory or a Python process. That is what actually makes them "independent" in the
distributed-systems sense; the shared source file is just avoiding copy-paste.

## Component responsibilities

- **Coordinator** — the only component with a global view. Keeps an in-memory node
  registry, runs a heartbeat-timeout monitor, and does the RPC fan-out to zones
  when the gateway asks it to find/release parking.
- **Zone (A/B/C)** — owns 20 physical slots. Answers RPCs about its own state,
  answers P2P capacity queries from its neighbor zone(s), and is the only thing
  in the system that touches its own rows in SQLite.
- **API Gateway** — the single HTTP-facing service. Translates REST/WebSocket
  from the browser into gRPC calls to the coordinator, and bridges Redis Stream
  events onto the browser's WebSocket connection.
- **Redis** — decouples "something happened" (a zone publishing an event) from
  "someone needs to know" (the gateway's consumer thread), which is the point of
  message-oriented communication.

## Data

SQLite (`database/parking.db`), two tables: `slots` and `reservations`. Each zone
only ever reads/writes rows where `zone_id` matches itself, so despite the shared
file, there's effectively no cross-zone write contention.

## Optional: Docker

`docker-compose.yml` runs **only Redis** in a container — this is intentional.
Installing Redis natively on Windows is a bigger ask than running one container,
but the rest of the system deliberately stays as plain OS processes so the
distributed nature is visible as separate terminal windows during a viva, not
hidden inside a docker-compose stack. Wrapping the app services in Docker too is a
reasonable Unit III/IV extension, not a Unit I/II requirement.
