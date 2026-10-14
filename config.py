"""Central configuration: node identities, addresses and shared constants.

Single source of truth for the topology so services never hardcode addresses.
Every host can be overridden with an environment variable, which is how the
same code runs three ways:

  * as plain local processes   -> every host defaults to "localhost"
  * under Docker Compose       -> ZONE_A_HOST=zone-a, COORD_1_HOST=coord-1, ... (one container each)
  * on Kubernetes              -> the same variables point at Service DNS names
"""

import os

# Interface the gRPC/HTTP servers bind to. "0.0.0.0" inside containers.
BIND_HOST = os.environ.get("BIND_HOST", "localhost")
HOST = "localhost"  # legacy alias kept for the FA-1 code paths


def _host(prefix: str) -> str:
    return os.environ.get(f"{prefix}_HOST", "localhost")


GATEWAY_PORT = int(os.environ.get("GATEWAY_PORT", 8000))
GATEWAY_NAME = os.environ.get("GATEWAY_NAME", os.environ.get("HOSTNAME", "gateway"))

# ---- Coordinator replicas (Unit 3: leader election) ----------------------------
# The id is the Bully-election priority: the live replica with the highest id leads.
COORDINATORS = {
    1: {"id": 1, "node_id": "COORD_1", "host": _host("COORD_1"), "port": 5101},
    2: {"id": 2, "node_id": "COORD_2", "host": _host("COORD_2"), "port": 5102},
    3: {"id": 3, "node_id": "COORD_3", "host": _host("COORD_3"), "port": 5103},
}

# ---- Parking zones --------------------------------------------------------------
ZONES = {
    "A": {"node_id": "ZONE_A", "zone_id": "PARKING_A", "host": _host("ZONE_A"), "port": 5001, "total_slots": 20, "p2p_port": 6001, "occupied_ratio": 0.45},
    "B": {"node_id": "ZONE_B", "zone_id": "PARKING_B", "host": _host("ZONE_B"), "port": 5002, "total_slots": 20, "p2p_port": 6002, "occupied_ratio": 0.25},
    "C": {"node_id": "ZONE_C", "zone_id": "PARKING_C", "host": _host("ZONE_C"), "port": 5003, "total_slots": 20, "p2p_port": 6003, "occupied_ratio": 0.10},
}
ZONE_BY_NODE = {cfg["node_id"]: key for key, cfg in ZONES.items()}

# P2P topology: which zones talk directly to which over TCP sockets (FA-1).
P2P_PEERS = {"A": ["B"], "B": ["A", "C"], "C": ["B"]}

# ---- Backing services -----------------------------------------------------------
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
REDIS_STREAM = "parking_events"

FAAS_URL = os.environ.get("FAAS_URL", "http://127.0.0.1:9000")
ANALYTICS_URL = os.environ.get("ANALYTICS_URL", "http://127.0.0.1:9100")

# ---- Timing ---------------------------------------------------------------------
HEARTBEAT_INTERVAL_SEC = 3
HEARTBEAT_TIMEOUT_SEC = 9  # leader marks a zone OFFLINE if no heartbeat within this window

BEACON_INTERVAL_SEC = 1.0   # leader -> replicas
BEACON_TIMEOUT_SEC = 4.0    # followers start an election after this much silence
ELECTION_ANNOUNCE_WAIT_SEC = 2.5

# ---- Shared overflow lot (Ricart-Agrawala mutual exclusion) ----------------------
# One lot shared by all three zones, used when every zone is full. Any zone can
# admit a car to it, so its free-slot counter is a shared resource.
OVERFLOW_CAPACITY = 5
OVERFLOW_KEY = "overflow:free_slots"
OVERFLOW_BOOKINGS_KEY = "overflow:bookings"   # hash: booking id -> zone that admitted it

# ---- Load balancing ----------------------------------------------------------------
POLICY_KEY = "config:allocation_policy"
DEFAULT_POLICY = "least_loaded"
POLICIES = ("first_fit", "round_robin", "least_loaded")


def coordinator_ids() -> list[int]:
    return sorted(COORDINATORS)


def node_id_for_coordinator(coord_id: int) -> str:
    return COORDINATORS[coord_id]["node_id"]
