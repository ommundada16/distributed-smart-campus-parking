"""SQLite persistence: parking slots and reservations.

Each zone process only reads/writes rows for its own zone_id, so the
shared file sees very little write contention. WAL mode keeps that
contention non-blocking for the demo's purposes.
"""

import sqlite3
import random
from contextlib import contextmanager

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS slots (
    slot_id TEXT PRIMARY KEY,
    zone_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('AVAILABLE', 'OCCUPIED', 'RESERVED'))
);

CREATE TABLE IF NOT EXISTS reservations (
    reservation_id TEXT PRIMARY KEY,
    slot_id TEXT NOT NULL,
    zone_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'RELEASED'))
);
"""


@contextmanager
def get_connection():
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_zone_slots(zone_id: str, prefix: str, total_slots: int, pre_occupied_ratio: float = 0.25):
    """Create slots A-01..A-20 for a zone if they don't already exist,
    with a few pre-seeded as OCCUPIED so the demo doesn't start empty."""
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT COUNT(*) AS c FROM slots WHERE zone_id = ?", (zone_id,)
        ).fetchone()["c"]
        if existing > 0:
            return

        rng = random.Random(42 + hash(zone_id) % 1000)
        n_occupied = max(1, int(total_slots * pre_occupied_ratio))
        occupied_indices = set(rng.sample(range(1, total_slots + 1), n_occupied))

        rows = []
        for i in range(1, total_slots + 1):
            slot_id = f"{prefix}-{i:02d}"
            status = "OCCUPIED" if i in occupied_indices else "AVAILABLE"
            rows.append((slot_id, zone_id, status))

        conn.executemany(
            "INSERT INTO slots (slot_id, zone_id, status) VALUES (?, ?, ?)", rows
        )


def init_schema():
    with get_connection() as conn:
        conn.executescript(SCHEMA)


def get_zone_counts(zone_id: str):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS c FROM slots WHERE zone_id = ? GROUP BY status",
            (zone_id,),
        ).fetchall()
    counts = {"AVAILABLE": 0, "OCCUPIED": 0, "RESERVED": 0}
    for row in rows:
        counts[row["status"]] = row["c"]
    return counts


def get_available_slot_ids(zone_id: str):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT slot_id FROM slots WHERE zone_id = ? AND status = 'AVAILABLE'",
            (zone_id,),
        ).fetchall()
    return [row["slot_id"] for row in rows]


def reserve_any_slot(zone_id: str, reservation_id: str):
    """Atomically pick one AVAILABLE slot in this zone and reserve it."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT slot_id FROM slots WHERE zone_id = ? AND status = 'AVAILABLE' LIMIT 1",
            (zone_id,),
        ).fetchone()
        if row is None:
            return None
        slot_id = row["slot_id"]
        conn.execute(
            "UPDATE slots SET status = 'RESERVED' WHERE slot_id = ?", (slot_id,)
        )
        conn.execute(
            "INSERT INTO reservations (reservation_id, slot_id, zone_id, created_at, status) "
            "VALUES (?, ?, ?, datetime('now'), 'ACTIVE')",
            (reservation_id, slot_id, zone_id),
        )
        return slot_id


def release_slot(zone_id: str, reservation_id: str):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT slot_id FROM reservations WHERE reservation_id = ? AND zone_id = ? AND status = 'ACTIVE'",
            (reservation_id, zone_id),
        ).fetchone()
        if row is None:
            return None
        slot_id = row["slot_id"]
        conn.execute(
            "UPDATE slots SET status = 'AVAILABLE' WHERE slot_id = ?", (slot_id,)
        )
        conn.execute(
            "UPDATE reservations SET status = 'RELEASED' WHERE reservation_id = ?",
            (reservation_id,),
        )
        return slot_id
