# FA-1 Demo Script

You explain this system **through the browser page**, top to bottom — you should
not need to open a code editor during the viva. Terminal windows are there as
supporting proof ("see, it's really happening"), not as something you narrate
line by line.

Total time: ~8 minutes. Have 5 terminal windows plus the browser ready.

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

Open the browser at `http://localhost:5173`. The whole demo happens on this one
page — you scroll down through it section by section.

## The script (narrate while scrolling down the page)

**Section 1 — Live Snapshot.** "This is pulled live from the coordinator over
gRPC, not hardcoded — 60 slots across 3 independent zone processes, refreshed
either by a WebSocket push or a 5-second poll as a fallback."

**Section 2 — Parking Zones.** "Each card is one independent OS process — Zone
A, B, C — each owning its own 20 slots in memory. They don't share a database
or any memory with each other or with the coordinator."

**Section 3 — Find & Reserve Parking. Click "Find Parking."** Watch the result
appear (Zone / Slot / Reservation ID), then immediately scroll to Section 5.

**Section 5 — Live Communication Activity.** Point at the new rows that just
appeared:
- an **RPC** row: `coordinator → ZONE_A → GetAvailableSlots()` — "this is a
  real gRPC call, request/response, the caller waits for the answer."
- a **MESSAGE** row: `PARKING_RESERVED` — "the zone published this to a Redis
  stream and moved on; it didn't wait for anyone to read it."
- notice the page updated **without a refresh** — "that message was pushed to
  this browser over a WebSocket connection the instant it was published; that's
  the stream-oriented style, a third, different communication pattern."
- every ~15 seconds, a **P2P** row appears on its own:
  `ZONE_A → ZONE_B → CAPACITY_REQUEST (AVAILABLE_SLOTS=...)` — "this is zone-to
  -zone directly over a TCP socket; the coordinator is not involved at all,
  which is what makes it peer-to-peer rather than RPC."

**Back to Section 3 — release the reservation** (button appears once you have
one). Point out a new `MESSAGE: PARKING_RELEASED` row appears.

**Section 4 — System Monitor table.** "Every row here — status, last heartbeat
— comes from the coordinator's live in-memory registry. Nothing is typed in by
hand."

**Section 2 again — click "Fail" on Zone B.** Within ~9 seconds:
- Zone B's badge flips to OFFLINE, live, no refresh.
- A `MESSAGE: NODE_FAILED` row appears in the activity feed.
- (Optional, for extra proof) switch to Terminal 1 and show
  `ZONE_B missed heartbeats -> OFFLINE`.

**Click "Find Parking" again.** The result comes back from Zone A or C —
mention: "the coordinator's registry marked Zone B offline, so it skipped it
when choosing a zone for this request — that's the fault-tolerance goal:
failure of one node doesn't break the whole service, and it doesn't get routed
new requests while it's down."

**Click "Recover" on Zone B.** Badge flips back to ONLINE, `NODE_RECOVERED`
event appears. "The zone process never died — we told it to stop responding,
the coordinator's heartbeat timeout is what actually detected and excluded it,
same as it would for a real crash."

## If asked "why is the client-server part not more complicated?"

Because the interesting distributed-systems behavior lives on the *backend* —
between the gateway, coordinator, and zones. The browser is just one more
client talking to the gateway over HTTP/WebSocket; adding more complexity there
wouldn't demonstrate anything new about distributed systems.

## If something goes wrong live

- **A zone won't register:** check the coordinator terminal started first and
  is still running on port 5000; restart the zone.
- **Redis errors / activity feed stops updating:** confirm `docker ps` shows
  `parking_redis` running; `docker compose up -d` again if not. The gateway's
  Redis calls time out in ~1 second, so a Redis outage won't hang the rest of
  the demo — parking requests still work, you just won't see new activity rows.
- **Frontend shows stale data:** the page also polls every 5s as a fallback
  even if the WebSocket drops — wait a few seconds, or refresh the page.
