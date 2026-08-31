# Communication Styles Used in This Project

Four different communication styles are used, each for the job it's actually good
at — not shoehorned in to tick a syllabus box.

## 1. RPC (Remote Procedure Call) — gRPC + Protocol Buffers

**What it is:** calling a function on another machine/process as if it were local.
The caller blocks until it gets a response back.

**Where it's used:**
- Zone → Coordinator: `RegisterNode()`, `Heartbeat()`
- Coordinator → Zone: `GetZoneStatus()`, `GetAvailableSlots()`, `ReserveSlot()`, `ReleaseSlot()`, `SetFailureMode()`
- Gateway → Coordinator: `FindParking()`, `ReleaseParking()`, `GetSystemStatus()`

**Why gRPC here:** it needs a strict contract (`proto/parking.proto`) between the
coordinator and three separately-deployable zone services, and the call pattern is
genuinely request/response — "give me your available slots right now."

## 2. Message-Oriented Communication — Redis Streams

**What it is:** the sender (producer) puts a message on a durable stream and moves
on immediately. The message sits there until a consumer reads it — sender and
receiver are decoupled in *time*, unlike RPC where the caller waits.

**Where it's used:** every zone/coordinator lifecycle and parking event
(`PARKING_REQUESTED`, `PARKING_RESERVED`, `PARKING_RELEASED`, `SLOT_STATUS_CHANGED`,
`NODE_REGISTERED`, `NODE_FAILED`, `NODE_RECOVERED`) is published to the
`parking_events` stream.

**Why Redis Streams here:** the gateway's WebSocket bridge, and potentially other
future consumers (an audit logger, an analytics job), shouldn't have to be online
and listening at the exact moment an event happens. The stream keeps the last N
events so a late consumer can catch up.

## 3. Stream-Oriented Communication — WebSocket

**What it is:** a persistent, full-duplex connection the server can push data
through at any time, without the client asking again.

**Where it's used:** `/ws` on the API Gateway. The gateway's background thread
consumes the Redis stream and immediately re-broadcasts each event to every
connected browser tab.

**Why WebSocket here:** the Dashboard/System Monitor pages need to reflect slot
and node status changes live. Polling the REST endpoint would work but wastes
requests and adds latency; a stream is the right tool for continuous status push.

## 4. P2P Messaging — raw TCP sockets

**What it is:** two peers of the same kind talking directly to each other, with no
central broker or coordinator in the path.

**Where it's used:** Zone A ↔ Zone B, Zone B ↔ Zone C. Every 15 seconds each zone
opens a plain TCP socket to its neighbor(s) and sends `CAPACITY_REQUEST`; the peer
replies with `AVAILABLE_SLOTS=<n>` on the same connection.

**Why plain TCP here:** this is the simplest possible demonstration of peer-to-peer
communication — no gRPC service definition, no broker, just two processes talking
directly. It intentionally does **not** go through the coordinator, which is the
whole point of calling it P2P rather than RPC.

## Names, Identifiers and Addresses

| Kind | Example | Scope |
|---|---|---|
| Node ID | `ZONE_A` | Identifies a running process instance |
| Zone ID | `PARKING_A` | Identifies the logical parking zone that node serves |
| Slot ID | `A-07` | Identifies one physical parking slot |
| Reservation ID | `RES-7F1EFCEC` | Identifies one reservation transaction |
| Host:Port | `localhost:5001` | Network address used for RPC/P2P |

## Why not WebRTC?

WebRTC solves peer-to-peer *media/data* connections between **browsers**, usually
with NAT traversal (STUN/TURN) as the hard part it's solving. Our P2P need is
server-to-server on the same machine/network — TCP sockets solve it directly with
none of WebRTC's signaling/NAT-traversal machinery being relevant. Using WebRTC
here would add complexity without demonstrating anything WebRTC is actually for.
