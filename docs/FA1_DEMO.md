# FA-1 Demo Script

Total time: ~8-10 minutes. Have 5 terminal windows plus the browser ready.

## Setup (before the professor arrives)

```bash
docker compose up -d          # Redis
```

Then either run `scripts/start_all.ps1` (opens 5 windows automatically), or open
5 terminals manually and run, one per terminal, **in this order**:

```bash
# Terminal 1
venv\Scripts\python -m services.coordinator.server

# Terminal 2
venv\Scripts\python -m services.zone_a.main

# Terminal 3
venv\Scripts\python -m services.zone_b.main

# Terminal 4
venv\Scripts\python -m services.zone_c.main

# Terminal 5
venv\Scripts\python -m uvicorn gateway.main:app --host localhost --port 8000
```

```bash
# Terminal 6
cd frontend
npm run dev
```

Open the browser at `http://localhost:5173`.

## Script

**Step 1 — Point at the terminals.** "Six independent processes: a coordinator,
three parking zones, an API gateway, and a message broker (Redis) — no shared
memory between them, only network calls."

**Step 2 — Show node registration.** Point at Terminal 1 (coordinator). Show the
`ZONE_A/B/C registered` lines that appeared as terminals 2-4 started.

**Step 3 — Open System Monitor.** Explain the table: each row is one real process,
`status` and `last heartbeat` come live from the coordinator's in-memory registry
over gRPC, not from a hardcoded list.

**Step 4 — Open Find Parking. Click "Find Parking."**

**Step 5 — Immediately switch to Terminal 1.** Show the lines:
```
FindParking: 3 online zone(s) to check
RPC -> ZONE_A GetAvailableSlots()
RPC <- ZONE_A available_count=...
```
This is real gRPC, not a mocked function call.

**Step 6 — Back in the browser**, show the returned Zone / Slot / Reservation ID.

**Step 7 — Show the Redis message.** Either open System Monitor's Event Activity
panel (already updated), or run in a spare terminal:
```bash
docker exec -it parking_redis redis-cli XRANGE parking_events - + COUNT 5
```

**Step 8 — Point out the UI updated without a refresh.** That update arrived over
the WebSocket connection, fed by the same Redis stream — mention this is a
*different* communication style from the RPC in step 5, deliberately.

**Step 9 — Show P2P.** Point at Terminal 3 or 4 (Zone B/C); every 15s they log
`P2P -> ZONE_x CAPACITY_REQUEST` / `P2P <- ZONE_x AVAILABLE_SLOTS=...`. This goes
directly zone-to-zone over TCP, bypassing the coordinator entirely.

**Step 10 — Fail Zone B.** In System Monitor, click "Fail" on Zone B.

**Step 11 — Show heartbeat failure detection.** Within ~9 seconds Terminal 1 logs:
```
ZONE_B missed heartbeats -> OFFLINE
```
and the UI's badge for Zone B flips to OFFLINE live, plus a `NODE_FAILED` event
appears in the Event Activity panel.

**Step 12 — Request another parking slot** (Find Parking again). Show Terminal 1's
log: `FindParking: 2 online zone(s) to check` — Zone B is skipped.

**Step 13 — Recover Zone B.** Click "Recover." Terminal 3 shows it re-registering;
Terminal 1 shows it added back; the UI flips to ONLINE and a `NODE_RECOVERED`
event appears.

**Step 14 — Close by pointing at [`docs/FA1_SYLLABUS_MAPPING.md`](FA1_SYLLABUS_MAPPING.md)**
and walking through which Unit 1/2 concept each thing just shown maps to.

## If something goes wrong live

- **A zone won't register:** check the coordinator terminal started first and is
  still running on port 5000; restart the zone.
- **Redis errors:** confirm `docker ps` shows `parking_redis` running; `docker
  compose up -d` again if not.
- **Frontend shows stale data:** the dashboard also polls every 5s as a fallback
  even if the WebSocket drops — wait a few seconds, or refresh the page.
