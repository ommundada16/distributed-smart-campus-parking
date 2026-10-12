"""Hash-chained, replicated booking ledger (Unit 4 self-study: blockchain and
distributed ledger technologies).

Each zone holds a full copy of the chain. A block commits only when a majority of
replicas accept it; a replica that was down catches up from its peers, and a
tampered replica is detected because its hashes no longer link up.
"""

import hashlib
import json
import threading
from dataclasses import asdict, dataclass, field


def _hash_payload(index: int, prev_hash: str, timestamp: float, lamport: int, tx: dict) -> str:
    body = json.dumps(
        {"index": index, "prev_hash": prev_hash, "timestamp": timestamp, "lamport": lamport, "tx": tx},
        sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(body.encode()).hexdigest()


@dataclass
class Block:
    index: int
    prev_hash: str
    timestamp: float
    lamport: int
    tx: dict = field(default_factory=dict)
    hash: str = ""

    def compute_hash(self) -> str:
        return _hash_payload(self.index, self.prev_hash, self.timestamp, self.lamport, self.tx)

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)

    @staticmethod
    def from_json(raw: str) -> "Block":
        return Block(**json.loads(raw))


GENESIS_PREV = "0" * 64


def make_genesis() -> Block:
    block = Block(0, GENESIS_PREV, 0.0, 0, {"type": "GENESIS", "note": "Smart Campus Parking ledger"})
    block.hash = block.compute_hash()
    return block


def make_block(prev: Block, tx: dict, lamport: int, timestamp: float) -> Block:
    block = Block(prev.index + 1, prev.hash, timestamp, lamport, tx)
    block.hash = block.compute_hash()
    return block


class Ledger:
    def __init__(self):
        self._lock = threading.RLock()
        self.chain: list[Block] = [make_genesis()]

    def head(self) -> Block:
        with self._lock:
            return self.chain[-1]

    def __len__(self):
        with self._lock:
            return len(self.chain)

    def append(self, block: Block) -> tuple[bool, str]:
        with self._lock:
            head = self.chain[-1]
            if block.index <= head.index:
                if self.chain[block.index].hash == block.hash:
                    return True, "duplicate"
                return False, "conflict: different block already at this index"
            if block.index != head.index + 1:
                return False, f"gap: have {head.index}, got {block.index}"
            if block.prev_hash != head.hash:
                return False, "prev_hash does not match head"
            if block.compute_hash() != block.hash:
                return False, "invalid block hash"
            self.chain.append(block)
            return True, "appended"

    def blocks_from(self, index: int) -> list[Block]:
        with self._lock:
            return list(self.chain[max(index, 0):])

    def verify(self) -> tuple[bool, int]:
        """Return (valid, first_bad_index). first_bad_index is -1 when valid."""
        with self._lock:
            for i, block in enumerate(self.chain):
                if block.compute_hash() != block.hash:
                    return False, i
                if i > 0 and block.prev_hash != self.chain[i - 1].hash:
                    return False, i
            return True, -1

    def truncate_from(self, index: int):
        with self._lock:
            self.chain = self.chain[:max(index, 1)]

    def tamper(self, index: int) -> bool:
        """Demo helper: silently rewrite a block's contents without fixing its hash."""
        with self._lock:
            if index <= 0 or index >= len(self.chain):
                return False
            block = self.chain[index]
            block.tx = dict(block.tx, tampered=True, slot_id="FORGED-99")
            return True
