# FA-1 Syllabus Mapping

This project only maps concepts that are **actually implemented and demonstrable**
in the running system. Nothing below is aspirational.

## Unit 1 — Distributed Systems Fundamentals

| Concept | Implementation | Demonstration |
|---|---|---|
| Definition & Goals of Distributed Systems | Resource sharing (parking slots shared across zones), availability (heartbeat/failover), transparency (client never talks to zones directly) | Explain via architecture diagram; System Monitor shows multiple independent nodes cooperating |
| Types of Distributed Systems | Client-server (React → Gateway) layered on top of a peer-coordinated service layer (Coordinator ↔ Zones) | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Architectures | Coordinator-based architecture: central coordinator + independent parking zone nodes | System Monitor page; `services/coordinator`, `services/zone` |
| Design Issues | Naming (node IDs, zone IDs, slot IDs), communication style choice per use case, failure handling | System Monitor (identifiers), Fault Tolerance Demonstration |
| Middleware | `communication/` package: `grpc/`, `messaging/`, `p2p/`, `websocket/` — application code never touches sockets/channels directly | Code walkthrough of `communication/` |
| Overview of Distributed Systems | The whole running system: 6 independent processes cooperating over 4 different communication styles | Full live demo |
| Model of Distributed Computations | Each zone is an independent process with its own state (SQLite rows) and its own thread of control, coordinated only via messages/RPC — no shared memory | Start each service in its own terminal; show `Get-Process` / task manager listing 5 separate python processes |
| Role of Virtualization | Redis runs in a Docker container; documented as optional deployment packaging, not required for the demo | `docker-compose.yml` (Redis only) |
| Distributed Multimedia Systems | **Not implemented** — out of scope for a parking allocation problem. See note below. | — |

## Unit 2 — Communication in Distributed Systems

| Concept | Implementation | Demonstration |
|---|---|---|
| Communication Fundamentals | Sockets (TCP for P2P), gRPC channels (RPC), pub/sub (Redis Streams), full-duplex sockets (WebSocket) — four distinct styles used for four distinct purposes | [COMMUNICATION.md](COMMUNICATION.md) |
| RPC | gRPC + Protocol Buffers (`proto/parking.proto`). Coordinator ↔ Zones (`GetAvailableSlots`, `ReserveSlot`, `ReleaseSlot`, `GetZoneStatus`), Zones → Coordinator (`RegisterNode`, `Heartbeat`), Gateway → Coordinator (`FindParking`, `ReleaseParking`, `GetSystemStatus`) | Terminal logs show `RPC -> ZONE_A GetAvailableSlots()` / `RPC <- ZONE_A available_count=...` live during Find Parking |
| Message-Oriented Communication | Redis Streams (`parking_events` stream). Producers (coordinator, zones) publish and move on; consumers (gateway's event bridge) read independently, at their own pace | System Monitor's Event Activity panel; `redis-cli XRANGE parking_events - +` |
| Stream-Oriented Communication | WebSocket (`/ws`) pushes every Redis event to the browser the instant it's published — no polling for the live parts of the UI | Reserve/release/fail a zone and watch the UI update without a page refresh |
| P2P Messaging | Raw TCP sockets directly between zone processes (Zone A ↔ Zone B ↔ Zone C), bypassing the coordinator entirely | Zone terminal logs show `P2P -> ZONE_B CAPACITY_REQUEST` / `P2P <- ZONE_B AVAILABLE_SLOTS=...` every 15s |
| WebRTC | **Not implemented** — see note below | — |
| Names, Identifiers and Addresses | `node_id` (`ZONE_A`), `zone_id` (`PARKING_A`), `slot_id` (`A-01`), `reservation_id` (`RES-XXXXXXXX`), host/port pairs | System Monitor table; `config.py` |
| Fault Tolerance | Heartbeat every 3s, coordinator marks a node `OFFLINE` after 9s of silence, excludes it from allocation, publishes `NODE_FAILED`; node re-registers and publishes `NODE_RECOVERED` on return | Fault Tolerance Demonstration buttons in System Monitor |

## Notes on deliberately excluded topics

**Distributed Multimedia Systems** — the selected problem (parking slot allocation)
has no audio/video/media component. Forcing one in would not demonstrate anything
about the actual distributed-systems concept and was left out of scope.

**WebRTC** — WebRTC is built for real-time peer-to-peer *media* (audio/video) and
data channels between browsers. Our P2P requirement (zone-to-zone capacity queries)
is server-to-server, not browser-to-browser, so plain TCP sockets are the correct
tool. If asked in viva:

> "WebRTC is part of Unit II, but it's primarily suited to real-time peer-to-peer
> media/data communication between browsers. Since our P2P requirement is between
> backend zone services — not browser clients — we used TCP-based socket
> communication for inter-zone coordination, and WebSockets for real-time
> client-facing status streaming. WebRTC was kept outside the core implementation
> because it doesn't fit this problem's actual communication pattern."

**Not implemented at all (by design, out of FA-1 scope):** Lamport/vector clocks,
Bully/Ring election, mutual exclusion algorithms, deadlock detection, Hadoop,
Kubernetes, blockchain, distributed databases. These belong to Unit 3/4 and would
not add anything defensible to an FA-1 evaluation of Unit 1/2 material.
