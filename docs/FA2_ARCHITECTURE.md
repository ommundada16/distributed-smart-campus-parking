# FA-2 Architecture

## 1. What problem is this, as a *distributed* system?

A campus parking system whose parts run on different nodes that can fail independently and share **no clock and no memory**. The interesting engineering is not "send a message between two programs" (that is networking) but what must be solved *because* there are several nodes:

| Distributed-systems problem | Where it shows up here | Solved by |
|---|---|---|
| Single point of failure | One coordinator served everything in FA-1 | 3 replicas + Bully election + beacon |
| No global clock / ordering | Events from different nodes must be ordered | Lamport + vector clocks; Berkeley sync |
| Concurrent access to a shared resource | Three zones sell the same overflow slots | Ricart-Agrawala mutual exclusion |
| No consistent global view | Capacity in transit between zones | Chandy-Lamport snapshot |
| Tamper-evident shared record | Booking history | Hash-chained, majority-committed replicated ledger |
| Load concentration | First-fit hammered Zone A | Load-aware allocation + request load balancing |
| Node crash / recovery | Zone or coordinator dies | Heartbeats, re-registration, ledger catch-up, leader rediscovery |

## 2. Component view

```
                         Browser (React)
                              │  HTTP + WebSocket
                    ┌─────────▼─────────┐
                    │   web  (Nginx)    │  round-robin LB · edge cache · static UI
                    └───────┬─────┬─────┘
                  ┌─────────▼┐   ┌▼─────────┐
                  │gateway-1 │   │gateway-2 │  stateless FastAPI, find the leader by name
                  └────┬─────┘   └─────┬────┘
                       └──────┬────────┘            gRPC (clock-stamped)
         ┌────────────────────▼────────────────────┐
         │  coord-1 ◄──── Bully election ────► coord-3 (LEADER) ◄──► coord-2  │  beacon every 1 s
         └───────┬───────────────┬───────────────┬──┘
                 │ gRPC          │ gRPC          │ gRPC               ┌────────────┐
            ┌────▼───┐      ┌────▼───┐      ┌────▼───┐   HTTP        │ faas       │ pricing / receipt
            │ zone-a │◄────►│ zone-b │◄────►│ zone-c │◄─────────────►│ (serverless)│
            └────────┘ P2P  └────────┘ P2P  └────────┘               └────────────┘
              ▲  ledger replica · Ricart-Agrawala · Chandy-Lamport · Berkeley slave

   redis  ── Streams event bus (every node publishes, gateways relay to WebSocket) + shared config
   analytics ── MapReduce worker pool, reads booking history from the zones' ledger
```

## 3. Server inventory and configuration

*"How many servers do you have, and what are their configurations?"* — Under Docker Compose there are **12 containers**, each with its own hostname (= its own network identity) and enforced CPU/memory limits. `docker compose ps` and `docker stats` show them live; the dashboard's **Cloud → Deployment** table shows the same data.

| Container | Count | Role | CPU limit | Memory limit | Address inside the network |
|---|---|---|---|---|---|
| web | 1 | Nginx load balancer, edge cache, UI | 0.50 | 128 MB | web:80 → host 8080 |
| gateway-1, gateway-2 | 2 | Stateless API gateway | 0.50 each | 256 MB each | gateway-N:8000 |
| coord-1, coord-2, coord-3 | 3 | Coordinator replicas (1 leader, 2 standbys) | 0.50 each | 256 MB each | coord-N:510N |
| zone-a, zone-b, zone-c | 3 | Slot service, mutex, snapshot, ledger replica | 0.25 each | 128 MB each | zone-x:500x (P2P 600x) |
| redis | 1 | Event streams + shared config | 0.50 | 128 MB | redis:6379 |
| faas | 1 | Serverless runtime | 0.25 | 128 MB | faas:9000 |
| analytics | 1 | MapReduce workers | 1.00 | 512 MB | analytics:9100 |

Total = 5.5 vCPU limit / 2.5 GB limit (limits, not reservations). Ports differ only because the same code also runs as plain local processes on one machine; in containers each node additionally has a distinct hostname/IP. On Kubernetes the same layout becomes pods (`k8s/`).

> Be precise in the viva: this is one *physical* host running 12 isolated containers (virtualization). The nodes are genuinely separate processes with separate network stacks and separate failure domains, but they share the host's hardware. A multi-host run needs Docker Swarm/Kubernetes across machines — the manifests support that, we simply have not run it on more than one machine.

## 4. Key design decisions

1. **One elected leader, standbys on hot standby (active–passive).** Only the leader serves parking requests, so allocation decisions are serialised without distributed locking. The price: throughput is bounded by one coordinator; the benefit is simplicity and a short failover (≈ beacon timeout 4 s + election ≈ 0.5 s).
2. **The leader keeps no irreplaceable state.** Zones own slot state; the ledger is replicated on zones; reservation IDs encode their zone. A new leader rebuilds its registry by probing the zones (`_become_leader_setup`) and reloads the ledger head from the longest valid zone replica.
3. **Terms.** Every leadership has a monotonically increasing term (as in Raft). Beacons carry it; a leader that receives a higher term steps down. A restarted node first *asks peers for their term* before declaring itself leader (otherwise a freshly restarted high-id node would announce a stale term and be ignored).
4. **Clocks live in the middleware, not the application.** `ClientClockInterceptor`/`ServerClockInterceptor` attach and merge the Lamport and vector clocks on every gRPC call (request metadata out, trailing metadata back). Application code just calls `stub.Method()`, and every event it publishes is stamped.
5. **Algorithms are separated from transport.** `distributed/*.py` take injected send functions, so they are unit-tested against an in-memory network (`tests/unit/test_algorithms.py`) and wired to gRPC in the services. This is what makes the algorithms demonstrably correct rather than only demonstrably running.
6. **FIFO channels for the snapshot.** Chandy-Lamport requires ordered channels; each peer link is a queue drained by one sender thread that makes blocking RPCs one at a time, so markers cannot overtake application messages.
7. **Mutual exclusion over a deliberately weak shared resource.** The overflow lot is a Redis counter updated with plain `GET` then `SET` (not `DECR`), so correctness comes from the algorithm and not from a lucky atomic primitive. A crashed peer is treated as an implicit grant (fault-tolerant variant).

## 5. Consistency and availability trade-offs (CAP / PACELC)

| Data | Choice | Behaviour during a failure / partition | Latency cost normally |
|---|---|---|---|
| Slot reservations | **Availability, per-zone consistency** — each slot is owned by exactly one zone, so no conflicting writes exist | If a zone is down its slots are unavailable, the others keep serving | one RPC |
| Booking ledger | **Majority commit (2 of 3)**, then eventual catch-up | One zone down → still commits; a partitioned minority cannot commit (consistency over availability for *ledger writes*); a lagging replica resyncs from peers on its next append or on recovery | one parallel round of 3 RPCs |
| Overflow lot (mutex) | **Consistency over availability** — safety of the critical section is never traded away | A node that is down is assumed to have granted, so the system stays live; a network *partition* that hides a live node could break safety — the known limitation of this fault-tolerant variant | 2(N−1) messages |
| Leader election | **Availability with a brief gap** — no leader for ~4–5 s after a crash | Requests fail fast during the gap, then resume | beacon traffic |

Why not proof-of-work / full BFT? The nodes are in one trust domain (a campus). A permissioned, leader-based ledger gives tamper *evidence* and replication cheaply; it does **not** defend against a malicious leader. State that limitation explicitly.

## 6. Mapping to Hadoop / HDFS terms (for the viva)

| HDFS / Hadoop | This project |
|---|---|
| NameNode (metadata, single active + standby) | Coordinator leader (+ 2 standbys) |
| DataNodes holding replicated blocks | Zones holding ledger replicas |
| Block checksums | Hash chain; `VerifyLedger` |
| Re-replication of a lost/corrupt block | `RepairLedger` / `sync_ledger` |
| MapReduce `Mapper → Combiner → Shuffle → Reducer` | `run_mapreduce` (same stages, process pool instead of a cluster) |

## 7. What is *not* implemented (be upfront)

* No multi-host cluster run; Kubernetes manifests are validated structurally but were not applied to a live cluster in development.
* Zones keep slot state in memory (no durable storage); a restarted zone loses it (it does re-join and re-sync its ledger).
* The ledger tolerates crash faults, not Byzantine faults.
* Lodha–Kshemkalyani and distributed deadlock detection are self-study notes, not code.
* The "FaaS platform" and "MapReduce engine" are small local models of Lambda/Hadoop, not those products.
