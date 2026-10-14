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
| Message-oriented communication | ✅ | Redis Streams event bus: `communication/messaging/message_bus.py` (events now carry Lamport timestamps) |
| Stream-oriented communication | ✅ | WebSocket fan-out to the browser: `communication/websocket/` |
| P2P messaging | ✅ | Zone↔zone TCP (FA-1 capacity polling) **plus** zone↔zone gRPC for mutual exclusion |
| WebRTC | 📘 | Not used (browser↔browser media); the WebSocket path covers browser push |
| *Self-study:* names, identifiers, addresses | ✅ | Replicas are found by **name** (`COORD_n`), resolved through `config.py`; `WhoIsLeader` maps "the leader" to an address. Reservation IDs encode the zone (`RES-B-3F6D0212`) so any coordinator can route a release with no lookup table |
| *Self-study:* fault tolerance | ✅ | Heartbeats, simulated zone crash, leader failover. **UI: Overview, Leader Election** |

## Unit 3 — Synchronization (new)

We implemented only what the system needs, and say why for the rest (see "Why only these" below).

| Topic | Status | Code | UI tab · demo |
|---|---|---|---|
| Election algorithms | ✅ | `distributed/election.py` (Bully) | **Leader Election** → Kill the leader, a new one is elected (≈4–5 s), Recover → it takes over again |
| Beacon protocol | ✅ | `BullyElection._monitor` / `Beacon` RPC: leader beacon every 1 s, silence of 4 s triggers election; beacons carry a *term* so a stale leader steps down | **Leader Election** timeline |
| Mutual exclusion | ✅ | `distributed/mutex.py` (Ricart-Agrawala), used by `OverflowBook` / `OverflowRelease` in `services/zone/zone_service.py`. The coordinator falls back to the shared overflow lot when every zone is full | **Mutual Exclusion** → overbooking without it, none with it; the real lot's bookings are listed on the same tab |
| Logical clocks — Lamport | ✅ | `distributed/clocks.py`; carried on every gRPC call by `communication/grpc/clock_interceptors.py` | **Mutual Exclusion** → each zone's REQUEST timestamp decides the entry order; every event shows `L=` |
| Clock synchronization (Cristian, Berkeley, NTP) | 📘 | Not implemented — no decision in the system depends on wall-clock time | — |
| Vector algorithm | 📘 | Not implemented — no decision depends on telling concurrent events apart | — |
| Global state | 📘 | Not implemented — nothing in the system needs a consistent global view | — |
| *Self-study:* Lodha–Kshemkalyani fair mutual exclusion | 📘 | See notes below | — |
| *Self-study:* Knapp's classification of distributed deadlock detection | 📘 | See notes below | — |

### Why only these

* **Election + beacon** — every booking goes through the leader; without an election the coordinator is a single point of failure.
* **Ricart-Agrawala** — the overflow lot is shared by all three zones and any of them can admit a car to it, so its free-slot counter needs mutual exclusion across nodes.
* **Lamport clock** — Ricart-Agrawala orders competing requests by (Lamport timestamp, node id). It is the one clock the system needs.
* **No physical clock sync** — timeouts are measured locally on each node and nothing compares wall-clock times across nodes.
* **No vector clocks** — nothing has to detect concurrent updates: each slot is owned by one zone and the overflow lot is protected by the mutex.
* **No snapshot** — no feature needs a consistent global state.

### Self-study notes (Unit 3)

**Fairness in mutual exclusion.** Ricart-Agrawala already serves requests in (Lamport timestamp, node id) order, which gives FIFO-like fairness. The Lodha–Kshemkalyani algorithm (*"A fair distributed mutual exclusion algorithm"*, IEEE TPDS, 2000) keeps fairness defined by the *happened-before* order and reduces the message cost compared with Ricart-Agrawala. Compare in the viva: our `RicartAgrawala` costs 2(N−1) messages per entry; the demo's message trace shows each of those messages. *(Check the exact message-complexity figures against the paper before quoting them.)*

**Deadlock detection (Knapp).** Distributed deadlock detection algorithms are classified as: *path-pushing* (wait-for paths are forwarded between sites), *edge-chasing* (probe messages follow wait-for edges; a probe returning to its initiator proves a cycle — Chandy-Misra-Haas), *diffusing computation* (query/reply waves), and *global-state-based* (take a consistent snapshot, e.g. with Chandy-Lamport, and look for cycles). Relation to this project: our Ricart-Agrawala has no deadlock because requests are totally ordered by timestamp, so the wait-for graph can never contain a cycle.

## Unit 4 — Emerging Distributed Paradigms (new)

| Topic | Status | Where / how |
|---|---|---|
| Distributed object-based systems | ✅ | `ZoneService` and `Coordinator` are remote objects: methods defined in an IDL (`parking.proto`), clients hold **stubs** (proxies) from `communication/grpc/grpc_client.py`. Same model as CORBA / Java RMI, with a language-neutral interface |
| Distributed web-based systems | ✅ | Browser → Nginx → gateway replicas (REST + WebSocket); stateless gateways, shared state in Redis, edge caching. **UI: Cloud → Web-scale delivery** |
| Distributed file system | 📘 | Not implemented, theory only: a DFS (GFS/HDFS) splits files into blocks, stores each block on several data nodes, and keeps the file-to-block map on a name node. Nothing in a parking system needs a shared file store, so we did not build one |
| Serverless architectures | 🔶 | `services/faas/runtime.py` is a small FaaS platform (cold start, warm, scale-to-zero, per-ms billing); `functions/pricing.py` and `functions/receipt.py` are Lambda-shaped handlers. **UI: Cloud → Serverless** |
| Case study: Megaport | 📘 | Software-defined network interconnection (on-demand virtual circuits via an API). Relevance: programmable infrastructure — our `k8s/` and Compose files provision the "network" of services declaratively |
| Case study: Cloudflare | 🔶 | Edge network that caches and runs code close to users (Workers). Modelled by the Nginx **edge cache** (`X-Cache-Status` HIT/MISS) and the FaaS runtime. We do not implement anycast or a global network |
| Case study: AWS | 🔶 | Lambda ↔ our FaaS runtime handler model; ELB ↔ Nginx / K8s Service load balancing; ECS/EKS ↔ Compose/K8s; ASG ↔ HorizontalPodAutoscaler (`k8s/40-gateway-web.yaml`) |
| Apache Hadoop | ✅ | `services/analytics/mapreduce.py` — map, combine, shuffle, reduce on a worker-process pool. **UI: Cloud → Batch analytics** (1 vs 4 workers, shuffle-reduction from the combiner) |
| Kubernetes | ✅ | `k8s/`: StatefulSet (stable identity → election priority), Deployments, Services, ConfigMap, probes, resource limits, HPA. *The manifests were validated structurally; apply them to kind/minikube to run them* |

## Load balancing (asked in FA-1)

| Level | Mechanism | Where |
|---|---|---|
| Application | Pluggable zone-allocation policy: `first_fit` (FA-1 baseline), `round_robin`, `least_loaded` | `services/coordinator/policies.py`; **UI: Load Balancing** compares all three on the same load |
| Request | Nginx round-robin across 2 gateway replicas; Kubernetes Service + HPA | `deploy/nginx.conf`, `k8s/40-gateway-web.yaml`; **UI: Cloud → Request load balancing** |
| Coordinator | Single elected leader serves requests; standbys take over (active–passive) | `distributed/election.py` |
