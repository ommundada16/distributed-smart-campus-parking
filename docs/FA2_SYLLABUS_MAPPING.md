# FA-2 — Syllabus Mapping (Units 1–4)

Every syllabus topic, where it lives in the code, and how to show it. **UI tab** names refer to the tabs of the web dashboard.

Legend: ✅ implemented and demonstrable · 🔶 modelled locally (same concepts, not the vendor product) · 📘 theory / self-study note only

## Unit 1 — Introduction (FA-1, extended)

| Topic | Status | Where / how |
|---|---|---|
| Definition, goals, types of distributed systems | ✅ | `docs/FA2_ARCHITECTURE.md` §1 — a distributed *information system* with coordination, storage and web tiers |
| Architectures | ✅ | Layered + client-server + peer-to-peer hybrid: gateway tier → replicated coordinator tier → zone peers (`docs/FA2_ARCHITECTURE.md` §2) |
| Design issues (transparency, scalability, fault tolerance, openness) | ✅ | Failure transparency: leader failover. Scalability: stateless gateways, load-aware allocation. Openness: gRPC IDL in `proto/parking.proto`. **UI: Load Balancing, Leader Election** |
| Middleware | ✅ | `communication/` (gRPC channels + **clock-propagating interceptors**, Redis message bus, WebSocket, P2P) and `communication/discovery.py` (leader discovery) |
| Distributed multimedia systems | 📘 | Not applicable to this domain; WebSocket event stream is the closest "continuous media" analogue |
| *Self-study:* model of distributed computation | ✅ | Asynchronous message passing, no shared memory/clock: each node is a process; the algorithms in `distributed/` are written against injected send/receive functions |
| *Self-study:* virtualization | ✅ | Every node is a container with CPU/memory limits (`docker-compose.yml`), and Kubernetes pods (`k8s/`) |

## Unit 2 — Communication (FA-1, extended)

| Topic | Status | Where |
|---|---|---|
| RPC | ✅ | gRPC: `proto/parking.proto`; zone, coordinator and election calls |
| Message-oriented communication | ✅ | Redis Streams event bus: `communication/messaging/message_bus.py` (events now carry logical clocks) |
| Stream-oriented communication | ✅ | WebSocket fan-out to the browser: `communication/websocket/` |
| P2P messaging | ✅ | Zone↔zone TCP (FA-1 capacity polling) **plus** zone↔zone gRPC for mutual exclusion, snapshot markers and ledger sync |
| WebRTC | 📘 | Not used (browser↔browser media); the WebSocket path covers browser push |
| *Self-study:* names, identifiers, addresses | ✅ | Replicas are found by **name** (`COORD_n`), resolved through `config.py`; `WhoIsLeader` maps "the leader" to an address. Reservation IDs encode the zone (`RES-B-3F6D0212`) so any coordinator can route a release with no lookup table |
| *Self-study:* fault tolerance | ✅ | Heartbeats, simulated zone crash, leader failover, ledger catch-up. **UI: Overview, Leader Election, Ledger** |

## Unit 3 — Synchronization (new)

| Topic | Status | Code | UI tab · demo |
|---|---|---|---|
| Clock synchronization | ✅ | `distributed/berkeley.py`, `SyncClocks` in `services/coordinator/server.py` | **Clocks** → "Synchronise clocks (Berkeley)": six clocks seeded ±2 s collapse to within a few ms |
| Logical clocks — Lamport | ✅ | `distributed/clocks.py`; `communication/grpc/clock_interceptors.py` | **Clocks** → every event shows `L=`; sort by Lamport vs wall clock |
| Vector algorithm | ✅ | same | **Clocks** → click two events: "happened-before" vs "concurrent". **Mutual Exclusion** shows pairs concurrent without the lock, ordered with it |
| Global state | ✅ | `distributed/snapshot.py` (Chandy-Lamport) + `services/zone/zone_service.py` | **Global Snapshot** → total is 30 only if in-flight bays are counted |
| Election algorithms | ✅ | `distributed/election.py` (Bully) | **Leader Election** → Kill the leader, a new one is elected (≈4–5 s), Recover → it takes over again |
| Mutual exclusion | ✅ | `distributed/mutex.py` (Ricart-Agrawala) | **Mutual Exclusion** → overbooking without it, none with it |
| Beacon protocol | ✅ | `BullyElection._monitor` / `Beacon` RPC: leader beacon every 1 s, silence of 4 s triggers election; beacons carry a *term* so a stale leader steps down | **Leader Election** timeline |
| *Self-study:* Lodha–Kshemkalyani fair mutual exclusion | 📘 | See notes below | — |
| *Self-study:* Knapp's classification of distributed deadlock detection | 📘 | See notes below | — |

### Self-study notes (Unit 3)

**Fairness in mutual exclusion.** Ricart-Agrawala already serves requests in (Lamport timestamp, node id) order, which gives FIFO-like fairness. The Lodha–Kshemkalyani algorithm (*"A fair distributed mutual exclusion algorithm"*, IEEE TPDS, 2000) keeps fairness defined by the *happened-before* order and reduces the message cost compared with Ricart-Agrawala. Compare in the viva: our `RicartAgrawala` costs 2(N−1) messages per entry; the demo's message trace shows each of those messages. *(Check the exact message-complexity figures against the paper before quoting them.)*

**Deadlock detection (Knapp).** Distributed deadlock detection algorithms are classified as: *path-pushing* (wait-for paths are forwarded between sites), *edge-chasing* (probe messages follow wait-for edges; a probe returning to its initiator proves a cycle — Chandy-Misra-Haas), *diffusing computation* (query/reply waves), and *global-state-based* (take a consistent snapshot and look for cycles). Relation to this project: our snapshot module is exactly the building block for the global-state class. Our Ricart-Agrawala has no deadlock because requests are totally ordered by timestamp, so the wait-for graph can never contain a cycle.

## Unit 4 — Emerging Distributed Paradigms (new)

| Topic | Status | Where / how |
|---|---|---|
| Distributed object-based systems | ✅ | `ZoneService` and `Coordinator` are remote objects: methods defined in an IDL (`parking.proto`), clients hold **stubs** (proxies) from `communication/grpc/grpc_client.py`. Same model as CORBA / Java RMI, with a language-neutral interface |
| Distributed web-based systems | ✅ | Browser → Nginx → gateway replicas (REST + WebSocket); stateless gateways, shared state in Redis, edge caching. **UI: Cloud → Web-scale delivery** |
| Distributed file system | 🔶 | The booking ledger is a replicated, append-only log with checksums (hash chain), majority commit and replica catch-up — the same ideas as GFS/HDFS block replication, but it is a ledger, not a general file system. See `docs/FA2_ARCHITECTURE.md` §6 for the HDFS comparison |
| Serverless architectures | 🔶 | `services/faas/runtime.py` is a small FaaS platform (cold start, warm, scale-to-zero, per-ms billing); `functions/pricing.py` and `functions/receipt.py` are Lambda-shaped handlers. **UI: Cloud → Serverless** |
| Case study: Megaport | 📘 | Software-defined network interconnection (on-demand virtual circuits via an API). Relevance: programmable infrastructure — our `k8s/` and Compose files provision the "network" of services declaratively |
| Case study: Cloudflare | 🔶 | Edge network that caches and runs code close to users (Workers). Modelled by the Nginx **edge cache** (`X-Cache-Status` HIT/MISS) and the FaaS runtime. We do not implement anycast or a global network |
| Case study: AWS | 🔶 | Lambda ↔ our FaaS runtime handler model; ELB ↔ Nginx / K8s Service load balancing; ECS/EKS ↔ Compose/K8s; ASG ↔ HorizontalPodAutoscaler (`k8s/40-gateway-web.yaml`) |
| Apache Hadoop | ✅ | `services/analytics/mapreduce.py` — map, combine, shuffle, reduce on a worker-process pool. **UI: Cloud → Batch analytics** (1 vs 4 workers, shuffle-reduction from the combiner) |
| Kubernetes | ✅ | `k8s/`: StatefulSet (stable identity → election priority), Deployments, Services, ConfigMap, probes, resource limits, HPA. *The manifests were validated structurally; apply them to kind/minikube to run them* |
| *Self-study:* blockchain / distributed ledgers; trade-offs in modern distributed databases | ✅ | Hash-chained ledger: `distributed/ledger.py`. **UI: Ledger** (tamper → detect → repair). Trade-offs: `docs/FA2_ARCHITECTURE.md` §5 (CAP / PACELC) |

## Load balancing (asked in FA-1)

| Level | Mechanism | Where |
|---|---|---|
| Application | Pluggable zone-allocation policy: `first_fit` (FA-1 baseline), `round_robin`, `least_loaded` | `services/coordinator/policies.py`; **UI: Load Balancing** compares all three on the same load |
| Request | Nginx round-robin across 2 gateway replicas; Kubernetes Service + HPA | `deploy/nginx.conf`, `k8s/40-gateway-web.yaml`; **UI: Cloud → Request load balancing** |
| Coordinator | Single elected leader serves requests; standbys take over (active–passive) | `distributed/election.py` |
