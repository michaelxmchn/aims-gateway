"""Merkle tree utilities for batch settlement.

Given a list of ExecutionRecords, produces a Merkle root that can be
submitted to the Base chain as a single compressed proof.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict
from typing import List

from src.ledger.log import ExecutionRecord


def hash_record(record: ExecutionRecord) -> bytes:
    """SHA-256 hash of a canonical JSON representation."""
    raw = asdict(record)
    canonical = json.dumps(raw, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(canonical).digest()


def compute_root(records: List[ExecutionRecord]) -> bytes:
    """Compute the Merkle root of a list of records.

    Uses simple binary Merkle tree with zero-padding to power-of-2.
    """
    import json

    leaves = [hash_record(r) for r in records]
    if not leaves:
        return b""

    while len(leaves) > 1:
        if len(leaves) % 2 == 1:
            leaves.append(leaves[-1])
        parents: List[bytes] = []
        for i in range(0, len(leaves), 2):
            combined = leaves[i] + leaves[i + 1]
            parents.append(hashlib.sha256(combined).digest())
        leaves = parents

    return leaves[0]
