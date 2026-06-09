"""Transaction history ledger for the AIMS Credit & Revenue system (Layer 3.5).

Records every deposit, task-deduction, worker-payout, and owner-revenue event
as an append-only log backed by the shared ``Storage`` instance.

Usage::

    store = Storage()
    ledger = TransactionLedger(store)
    tx_id = ledger.record("deposit", "alice", 10.0, "Initial deposit")
    txs = ledger.get_user_history("alice")
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any

from src.gateway.storage import Storage

logger = __import__("logging").getLogger(__name__)

NS_TXNS = "ledger:transactions"
KEY_COUNTER = "ledger:counter"
KEY_USER_TXNS = "ledger:user_txns"


class TransactionLedger:
    """Append-only history of credit & billing transactions.

    Each transaction is stored as a JSON dict under ``ledger:transactions:{tx_id}``.
    A secondary index maps ``ledger:user_txns:{user_id}`` to a list of tx_ids
    for efficient per-user lookups.
    """

    def __init__(self, storage: Storage) -> None:
        self._storage = storage
        self._lock = threading.Lock()

    def record(
        self,
        txn_type: str,
        user_id: str,
        amount: float,
        description: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Record a transaction and return its unique ``tx_id``.

        Args:
            txn_type: ``"deposit"``, ``"task_deduction"``, ``"worker_payout"``,
                      ``"owner_revenue"``, or ``"refund"``.
            user_id:  The primary actor (who the balance change is for).
            amount:   The credit amount involved (positive for credits, may be
                      negative if the caller prefers).
            description: Human-readable summary.
            metadata: Optional extra fields (e.g. ``{"task_id": "…"}``).
        """
        counter = self._storage.incr(KEY_COUNTER)
        tx_id = f"txn-{counter:04d}"

        record: dict[str, Any] = {
            "tx_id": tx_id,
            "type": txn_type,
            "user_id": user_id,
            "amount": round(amount, 4),
            "description": description,
            "metadata": metadata or {},
            "timestamp": time.time(),
        }
        self._storage.dict_set(NS_TXNS, tx_id, record)

        # Append to the per-user index (best-effort, stored as JSON list)
        self._append_user_txn(user_id, tx_id)

        return tx_id

    def _append_user_txn(self, user_id: str, tx_id: str) -> None:
        """Append *tx_id* to the user's transaction list."""
        key = f"{KEY_USER_TXNS}:{user_id}"
        existing = self._storage.get(key, [])
        if not isinstance(existing, list):
            existing = []
        existing.append(tx_id)
        # Keep only the last 200 entries per user
        self._storage.set(key, existing[-200:])

    def get_transaction(self, tx_id: str) -> dict[str, Any] | None:
        """Retrieve a single transaction record by *tx_id*, or ``None``."""
        return self._storage.dict_get(NS_TXNS, tx_id)

    def get_user_history(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """Return the most recent *limit* transactions for *user_id*."""
        key = f"{KEY_USER_TXNS}:{user_id}"
        tx_ids = self._storage.get(key, [])
        if not isinstance(tx_ids, list):
            return []
        results: list[dict[str, Any]] = []
        for tid in reversed(tx_ids[-limit:]):
            txn = self._storage.dict_get(NS_TXNS, tid)
            if txn is not None:
                results.append(txn)
        return results

    def get_all(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return the most recent *limit* transactions across all users."""
        all_txns = self._storage.dict_all(NS_TXNS)
        sorted_txns = sorted(
            all_txns.values(),
            key=lambda t: t.get("timestamp", 0),
            reverse=True,
        )
        return sorted_txns[:limit]
