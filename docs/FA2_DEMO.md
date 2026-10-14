# FA-2 Demo Script (~12 minutes) and Viva Cheat-Sheet

## Start

```bash
docker compose up --build -d     # 12 containers, UI at http://localhost:8080
docker compose ps                # show the server inventory
```
(Or without Docker: `python scripts/run_local.py` + `cd frontend && npm run dev`, UI at http://localhost:5173.)

## Script

| # | Tab | What to do | What to say |
|---|---|---|---|
| 1 | Cloud & Deployment | Show the deployment table and `docker stats` | "12 containers, each with its own hostname and CPU/memory limit. Ports are different only so the same code also runs locally." |
| 2 | Overview | Press **Find Parking** | "Request goes Nginx → one of two gateways → the *elected* coordinator → allocation policy → a zone. Note the price from a **serverless function**, and the Lamport timestamp." |
| 3 | Leader Election | **Kill** the LEADER, press *Request a slot* repeatedly | "Requests fail for ~4 s, a new leader is elected, requests succeed served by a different coordinator. Recover the old one: Bully lets the higher id take back leadership with a higher term." |
| 4 | Mutual Exclusion | Run **WITHOUT**, then **WITH** | "When all zones are full, cars go to one overflow lot that any zone can admit to. No lock: three zones all read '2 free', all book → overbooked, counter wrong. With Ricart-Agrawala: exactly 2 booked, no overlap, and the zones enter in order of their Lamport REQUEST timestamps. That is why we keep one clock: the mutex needs it. The trace shows who deferred whom." |
| 5 | Overview | **Fail** zone C, make bookings, **Recover** | "The leader notices C missed its heartbeats and stops using it; the other zones keep serving. When C returns it re-registers and is used again." |
| 6 | Load Balancing | **Run comparison** | "Same 24 requests: first-fit (FA-1) saturates Zone A; round-robin spreads requests; least-loaded equalises *occupancy*. Lowest imbalance wins." |
| 7 | Cloud | Send 12 requests; fetch edge summary twice; invoke `pricing()`, **Evict**, invoke again; run MapReduce on 1 vs 4 workers | "Load balanced across gateways; edge cache MISS then HIT; serverless cold vs warm start; MapReduce combiner cuts shuffle traffic by >99 %." |

Optional — a *real* crash instead of the simulated one: `docker compose stop coord-3` (then `docker compose start coord-3`), or `docker compose stop zone-c` / `start zone-c`. The same failover happens. (A restarted zone loses its in-memory slot state but re-registers.)

## Likely viva questions

**"Is this just computer networks?"**
Networking is how bytes get between nodes. Here the hard parts are the problems that exist only because nodes are independent: agreeing on a leader (Bully), mutual exclusion without shared memory (Ricart-Agrawala), ordering requests without a shared clock (Lamport). Each has a demo that first shows the failure, then the fix.

**"How are you handling load balancing?"**
Two levels. Application: the coordinator picks a zone with a pluggable policy — first-fit (our FA-1 baseline), round-robin, least-loaded — and the UI compares them on identical load. Request level: Nginx round-robins across two gateway replicas; on Kubernetes the Service does it and a HorizontalPodAutoscaler adds replicas under CPU load.

**"How many servers, what configuration?"**
12 containers (table in `FA2_ARCHITECTURE.md` §3 and the Cloud tab). Different hostnames/IPs, CPU and memory limits per container. One physical host — stated honestly; the Kubernetes manifests describe the multi-node form.

**"What is your single point of failure now?"**
Redis (event bus + policy store) and Nginx. Coordinator, gateways and zones are covered. Mitigation (not implemented): Redis Sentinel/replication, a second edge node. Zone state is also in memory.

**"What happens if the leader crashes mid-request?"**
The gateway's call fails with UNAVAILABLE, it rediscovers the leader and retries. A reservation already made on a zone stays held by that zone, and releases route by the zone encoded in the reservation id, so nothing is lost. (Exactly-once semantics for the in-flight request are not provided.)

**"Does Ricart-Agrawala survive a crash?"**
Plain RA blocks forever if a peer dies. We treat an unreachable peer as an implicit grant, which keeps the system live but could violate safety if a *live* node is merely partitioned away. Real systems add a failure detector with membership agreement.

**"Why only one clock? Why not vector clocks or Berkeley?"**
We implemented only what the system uses. Ricart-Agrawala needs a total order of requests, which the Lamport clock gives. Nothing compares wall-clock times across nodes, so physical clock sync would correct nothing; nothing has to detect concurrent updates, so vector clocks would decide nothing; and no feature needs a consistent global view, so there is no snapshot.

**"Serverless — is that real Lambda?"**
No — it is a local model of the programming and billing model (stateless handler, cold/warm start, scale-to-zero, per-ms metering). The handlers are written in Lambda's `handler(event, context)` shape.
