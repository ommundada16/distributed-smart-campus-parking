"""Central configuration: node identities, ports and shared constants.

Single source of truth for addresses so services don't hardcode magic
numbers. Each service still runs as its own OS process; this module is
just imported by all of them.
"""

import os

HOST = "localhost"

GATEWAY_PORT = 8000
COORDINATOR_GRPC_PORT = 5000

ZONES = {
    "A": {"node_id": "ZONE_A", "zone_id": "PARKING_A", "port": 5001, "total_slots": 20, "p2p_port": 6001},
    "B": {"node_id": "ZONE_B", "zone_id": "PARKING_B", "port": 5002, "total_slots": 20, "p2p_port": 6002},
    "C": {"node_id": "ZONE_C", "zone_id": "PARKING_C", "port": 5003, "total_slots": 20, "p2p_port": 6003},
}

# P2P topology: which zones talk directly to which over TCP sockets.
P2P_PEERS = {
    "A": ["B"],
    "B": ["A", "C"],
    "C": ["B"],
}

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
REDIS_STREAM = "parking_events"

HEARTBEAT_INTERVAL_SEC = 3
HEARTBEAT_TIMEOUT_SEC = 9  # coordinator marks a node OFFLINE if no heartbeat within this window
