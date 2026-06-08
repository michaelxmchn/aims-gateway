"""Task Broker — Stateful Task Claiming & Fault-Tolerance (Layer 3.5).

Manages a thread-safe in-memory task store with explicit state tracking.
Workers claim individual tasks; the broker detects abandoned (timed-out)
CLAIMED tasks and recycles them back to PENDING so other workers can
pick them up.

Lifecycle:
  1. publish_task()  — create escrow hold from user, enqueue as PENDING
  2. claim_task()    — atomically grab the first PENDING task → CLAIMED
  3. complete_task() — mark CLAIMED as SUCCESS or FAILED
  4. check_timeouts()— recycle CLAIMED tasks older than 5 s back to PENDING
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.ledger.mock_counter import DynamicSettlementDetail, EscrowHold, MockLedger

logger = logging.getLogger(__name__)

CLAIM_TIMEOUT = 5.0
"""Seconds after which a CLAIMED task is considered abandoned."""


@dataclass
class BrokerTask:
    """Escrow metadata for a published task (referenced by task_id)."""

    task_id: str
    user_id: str
    asin: str
    developer_premium: float
    max_budget: float
    escrow_hold: EscrowHold
    skill_id: str = ""
    compute_tier: int = 1


class TaskBroker:
    """Thread-safe stateful task store with claiming and timeout recovery."""

    def __init__(self, ledger: MockLedger) -> None:
        self._ledger = ledger
        self._task_counter = 0
        self._lock = threading.Lock()

        # Task state store: task_id → task metadata
        self._tasks: Dict[str, BrokerTask] = {}

        # Task status tracking
        # Maps task_id → {"status": str, "worker_id": str | None, "claimed_at": float | None}
        self._status: Dict[str, Dict[str, Any]] = {}

        # Settlement results
        self._results: Dict[str, DynamicSettlementDetail] = {}

    # ── Publish ────────────────────────────────────────────────────────────

    def publish_task(
        self,
        user_id: str,
        asin: str,
        developer_premium: float,
        max_budget: float,
        skill_id: str = "",
        compute_tier: int = 1,
    ) -> Optional[str]:
        """Create an escrow hold and register a PENDING task.

        Returns the ``task_id`` string, or ``None`` if the user has
        insufficient balance for the escrow hold.
        """
        hold = self._ledger.create_escrow_hold(user_id, max_budget)
        if hold is None:
            return None

        with self._lock:
            self._task_counter += 1
            task_id = f"task-{self._task_counter:04d}"

        task = BrokerTask(
            task_id=task_id,
            user_id=user_id,
            asin=asin,
            developer_premium=developer_premium,
            max_budget=max_budget,
            escrow_hold=hold,
            skill_id=skill_id,
            compute_tier=compute_tier,
        )

        with self._lock:
            self._tasks[task_id] = task
            self._status[task_id] = {
                "status": "PENDING",
                "worker_id": None,
                "claimed_at": None,
            }

        logger.info(
            "PUBLISH %s → PENDING (asin=%s  premium=$%.2f  budget=$%.2f)",
            task_id, asin, developer_premium, max_budget,
        )
        return task_id

    # ── Claim ──────────────────────────────────────────────────────────────

    def claim_task(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """Atomically claim the first PENDING task.

        Returns an enriched dict with task metadata, or ``None`` if no
        PENDING tasks are available.
        """
        with self._lock:
            for tid, state in self._status.items():
                if state["status"] == "PENDING":
                    task = self._tasks.get(tid)
                    if task is None:
                        continue

                    state["status"] = "CLAIMED"
                    state["worker_id"] = worker_id
                    state["claimed_at"] = time.time()

                    logger.info(
                        "CLAIM %s → worker '%s'  (asin=%s)",
                        tid, worker_id, task.asin,
                    )
                    return {
                        "task_id": tid,
                        "asin": task.asin,
                        "status": "CLAIMED",
                        "worker_id": worker_id,
                        "claimed_at": state["claimed_at"],
                        "user_id": task.user_id,
                        "developer_premium": task.developer_premium,
                        "max_budget": task.max_budget,
                        "escrow_hold": task.escrow_hold,
                        "skill_id": task.skill_id,
                        "compute_tier": task.compute_tier,
                    }
            return None

    # ── Complete ───────────────────────────────────────────────────────────

    def complete_task(
        self,
        task_id: str,
        status: str,
        detail: Optional[DynamicSettlementDetail] = None,
    ) -> None:
        """Mark a CLAIMED task as SUCCESS or FAILED."""
        with self._lock:
            state = self._status.get(task_id)
            if state is None:
                logger.warning("COMPLETE %s — unknown task", task_id)
                return
            if state["status"] != "CLAIMED":
                logger.warning(
                    "COMPLETE %s — expected CLAIMED, got %s",
                    task_id, state["status"],
                )
                return

            state["status"] = status
            if detail is not None:
                self._results[task_id] = detail

            logger.info(
                "COMPLETE %s → %s  (worker='%s')",
                task_id, status, state["worker_id"],
            )

    # ── Timeout recovery ───────────────────────────────────────────────────

    def validate_task_result(self, task_id: str, result_data: Any) -> bool:
        """Proof-of-Result validation with automatic penalty on failure.

        Validation rules for *result_data*:
          - Must be a ``dict``.
          - Must contain ``"asin"`` (non-empty string).
          - Must contain ``"price"`` (float/int > 0).

        If validation fails, the worker that claimed this task receives a
        strike via ``ledger.apply_penalty()``.

        Returns ``True`` if the result is valid, ``False`` otherwise.
        """
        with self._lock:
            state = self._status.get(task_id)
            if state is None:
                return False
            worker_id = state.get("worker_id")

        if not isinstance(result_data, dict):
            logger.warning("VALIDATE %s FAIL — not a dict", task_id)
            if worker_id:
                self._ledger.apply_penalty(worker_id, f"invalid result: not a dict")
            return False

        asin = result_data.get("asin", "")
        price = result_data.get("price", 0)

        if not isinstance(asin, str) or not asin.strip():
            logger.warning(
                "VALIDATE %s FAIL — bad asin=%r (worker='%s')",
                task_id, asin, worker_id,
            )
            if worker_id:
                self._ledger.apply_penalty(worker_id, f"invalid result: bad asin={asin!r}")
            return False

        if not isinstance(price, (int, float)) or price <= 0:
            logger.warning(
                "VALIDATE %s FAIL — bad price=%r (worker='%s')",
                task_id, price, worker_id,
            )
            if worker_id:
                self._ledger.apply_penalty(worker_id, f"invalid result: bad price={price}")
            return False

        logger.info("VALIDATE %s PASS (asin=%s, price=$%.2f)", task_id, asin, float(price))
        return True

    def check_timeouts(self) -> List[str]:
        """Revert CLAIMED tasks older than *CLAIM_TIMEOUT* back to PENDING.

        Each timed-out worker receives a strike via ``ledger.apply_penalty()``.

        Returns the list of recycled task IDs.
        """
        recycled: List[str] = []
        # Capture (task_id, worker_id) before mutating state
        timeout_workers: List[tuple[str, str]] = []
        now = time.time()

        with self._lock:
            for tid, state in self._status.items():
                if state["status"] != "CLAIMED":
                    continue
                if state["claimed_at"] is None:
                    continue
                age = now - state["claimed_at"]
                if age >= CLAIM_TIMEOUT:
                    worker = state["worker_id"]
                    logger.warning(
                        "[Timeout] Worker '%s' went ghost on %s! "
                        "(age=%.1fs) Reverting to PENDING.",
                        worker, tid, age,
                    )
                    state["status"] = "PENDING"
                    state["worker_id"] = None
                    state["claimed_at"] = None
                    recycled.append(tid)
                    if worker:
                        timeout_workers.append((tid, worker))

        # Apply penalties outside the lock to avoid nested lock contention
        for tid, worker in timeout_workers:
            self._ledger.apply_penalty(worker, "timeout")

        return recycled

    # ── Generic JSON Schema validation ──────────────────────────────────

    def validate_result_generic(self, result_data: Any, schema: Dict[str, Any],
                                 worker_id: str) -> bool:
        """Generic JSON Schema result validation with slashing integration.

        Supports a subset of JSON Schema sufficient for skill output checks:

        - **type**: ``"object"`` | ``"array"`` | ``"string"`` | ``"number"``
        - **properties** (object): each key describes a field with:
          ``{"type": ..., "required": true/false}``
        - **items** (array): schema for each element
        - **minimum** / **maximum** (number): numeric bounds

        On validation failure, calls ``ledger.apply_penalty(worker_id)``.
        Returns ``True`` if valid, ``False`` otherwise.
        """
        def _check_type(value: Any, expected: str) -> bool:
            if expected == "object":
                return isinstance(value, dict)
            elif expected == "array":
                return isinstance(value, list)
            elif expected == "string":
                return isinstance(value, str)
            elif expected == "number":
                return isinstance(value, (int, float))
            return True  # unknown type passes

        def _validate(value: Any, schema_part: Dict[str, Any]) -> bool:
            schema_type = schema_part.get("type")
            if schema_type:
                if not _check_type(value, schema_type):
                    return False

            if schema_type == "object" and isinstance(value, dict):
                req = schema_part.get("required", [])
                for field in req:
                    if field not in value:
                        return False
                props = schema_part.get("properties", {})
                for prop_name, prop_schema in props.items():
                    if prop_name in value:
                        if not _validate(value[prop_name], prop_schema):
                            return False

            if schema_type == "array" and isinstance(value, list):
                items_schema = schema_part.get("items", {})
                for item in value:
                    if not _validate(item, items_schema):
                        return False

            if isinstance(value, (int, float)):
                min_val = schema_part.get("minimum")
                max_val = schema_part.get("maximum")
                if min_val is not None and value < min_val:
                    return False
                if max_val is not None and value > max_val:
                    return False

            return True

        if not _validate(result_data, schema):
            logger.warning(
                "VALIDATE GENERIC FAIL — worker='%s'  schema=%s",
                worker_id, schema,
            )
            self._ledger.apply_penalty(worker_id, "output validation failed")
            return False

        logger.info("VALIDATE GENERIC PASS — worker='%s'", worker_id)
        return True

    # ── Task metadata lookup (for Gateway Server) ─────────────────────────

    def get_task_meta(self, task_id: str) -> Optional["BrokerTask"]:
        """Return task metadata for the given *task_id*, or ``None``."""
        with self._lock:
            return self._tasks.get(task_id)

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Return a copy of the task status dict, or ``None``."""
        with self._lock:
            s = self._status.get(task_id)
            return dict(s) if s else None

    # ── Status helpers ─────────────────────────────────────────────────────

    @property
    def pending_count(self) -> int:
        with self._lock:
            return sum(
                1 for s in self._status.values() if s["status"] == "PENDING"
            )

    @property
    def completed_count(self) -> int:
        with self._lock:
            return len(self._results)

    def worker_summary(self) -> Dict[str, int]:
        """Return {worker_id: completed_task_count}."""
        with self._lock:
            summary: Dict[str, int] = {}
            for tid, state in self._status.items():
                if state["status"] == "SUCCESS" and state["worker_id"]:
                    wid = state["worker_id"]
                    summary[wid] = summary.get(wid, 0) + 1
            return summary

    def status_counts(self) -> Dict[str, int]:
        """Return {status_label: count} for diagnostics."""
        with self._lock:
            counts: Dict[str, int] = {}
            for s in self._status.values():
                label = s["status"]
                counts[label] = counts.get(label, 0) + 1
            return counts
