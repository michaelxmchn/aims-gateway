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

import dataclasses
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.gateway.storage import Storage
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
    payload: dict | None = None
    """Input arguments for the skill execution (dynamic skills)."""
    pipeline: list[str] | None = None
    """Sequential skill IDs for task chaining (multimodal task flows)."""
    pipeline_step: int = 0
    """Current step index in the pipeline (0-based)."""
    task_name: str = ""
    """Human-readable task name (shown in Task Market UI)."""
    description: str = ""
    """Optional task description (free text for the Task Market)."""
    is_custom: bool = False
    """If True, only workers with credit_score >= credit_score_required can claim."""
    credit_score_required: int = 0
    """Minimum worker credit score (0-100) required to claim this task."""


class TaskBroker:
    """Thread-safe stateful task store with claiming and timeout recovery."""

    def __init__(self, ledger: MockLedger, storage: Storage | None = None) -> None:
        self._ledger = ledger
        self._storage = storage
        self._lock = threading.Lock()

        # Task state store: task_id → task metadata
        self._tasks: Dict[str, BrokerTask] = {}

        # Task status tracking
        # Maps task_id → {"status": str, "worker_id": str | None, "claimed_at": float | None}
        self._status: Dict[str, Dict[str, Any]] = {}

        # Settlement results
        self._results: Dict[str, DynamicSettlementDetail] = {}

        # Auto-incrementing task ID counter
        self._task_counter: int = 0

        # Restore state from Redis on startup if available
        if storage and storage.is_persistent:
            self._load_state()

    # ── Redis persistence helpers ────────────────────────────────────────────

    NS_TASKS = "broker:tasks"
    NS_STATUS = "broker:status"
    NS_RESULTS = "broker:results"
    NS_CONTEXT = "broker:context"
    KEY_COUNTER = "broker:counter"

    def _load_state(self) -> None:
        """Restore all task state from Redis (called on startup)."""
        assert self._storage is not None
        store = self._storage

        self._task_counter = store.get(self.KEY_COUNTER, 0) or 0

        # Restore tasks
        raw_tasks = store.dict_all(self.NS_TASKS)
        for tid, data in raw_tasks.items():
            if isinstance(data, dict):
                hold_data = data.pop("escrow_hold", {})
                hold = EscrowHold(**hold_data) if hold_data else None
                task = BrokerTask(escrow_hold=hold, **data)
                self._tasks[tid] = task

        # Restore status
        raw_status = store.dict_all(self.NS_STATUS)
        for tid, state in raw_status.items():
            if isinstance(state, dict):
                self._status[tid] = state

        # Restore results
        raw_results = store.dict_all(self.NS_RESULTS)
        for tid, detail in raw_results.items():
            if isinstance(detail, dict):
                self._results[tid] = DynamicSettlementDetail(**detail)

        logger.info(
            "Broker state restored from Redis — %d tasks, %d active",
            len(self._tasks),
            sum(1 for s in self._status.values() if s.get("status") == "PENDING"),
        )

    def _persist_task(self, task_id: str, task: BrokerTask) -> None:
        """Write a single BrokerTask to Redis."""
        if self._storage and self._storage.is_persistent:
            raw = dataclasses.asdict(task)
            self._storage.dict_set(self.NS_TASKS, task_id, raw)

    def _persist_status(self, task_id: str, status: dict) -> None:
        """Write a single status entry to Redis."""
        if self._storage and self._storage.is_persistent:
            self._storage.dict_set(self.NS_STATUS, task_id, status)

    def _persist_result(self, task_id: str, detail: DynamicSettlementDetail) -> None:
        """Write a single settlement result to Redis."""
        if self._storage and self._storage.is_persistent:
            self._storage.dict_set(self.NS_RESULTS, task_id, dataclasses.asdict(detail))

    def _persist_counter(self) -> None:
        if self._storage and self._storage.is_persistent:
            self._storage.set(self.KEY_COUNTER, self._task_counter)

    # ── Context helpers (pipeline intermediate step storage) ──────────────

    def _persist_context(self, context_key: str, data: dict) -> None:
        """Write pipeline context data to Redis."""
        if self._storage and self._storage.is_persistent:
            self._storage.dict_set(self.NS_CONTEXT, context_key, data)

    def get_context(self, task_id: str, step: int) -> dict | None:
        """Read pipeline context for a specific task+step from Redis."""
        if self._storage and self._storage.is_persistent:
            return self._storage.dict_get(self.NS_CONTEXT, f"{task_id}:step_{step}")
        return None

    # ── Publish ────────────────────────────────────────────────────────────

    def publish_task(
        self,
        user_id: str,
        asin: str,
        developer_premium: float,
        max_budget: float,
        skill_id: str = "",
        compute_tier: int = 1,
        payload: dict | None = None,
        pipeline: list[str] | None = None,
        task_name: str = "",
        description: str = "",
        is_custom: bool = False,
        credit_score_required: int = 0,
    ) -> Optional[str]:
        """Create an escrow hold and register a PENDING task.

        *payload* is an optional dict that carries input arguments for
        dynamic skill execution (the ``/api/run`` path).  Static skill
        tasks typically pass ``None``.

        *pipeline* is an optional ordered list of skill IDs for sequential
        chaining.  When provided, the broker automatically advances through
        each skill on SUCCESS, storing intermediate context in Redis.
        The first element must match *skill_id*.

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
            payload=payload,
            pipeline=pipeline,
            pipeline_step=0,
            task_name=task_name,
            description=description,
            is_custom=is_custom,
            credit_score_required=credit_score_required,
        )

        with self._lock:
            self._tasks[task_id] = task
            self._status[task_id] = {
                "status": "PENDING",
                "worker_id": None,
                "claimed_at": None,
            }

        # Persist to Redis
        self._persist_task(task_id, task)
        self._persist_status(task_id, self._status[task_id])
        self._persist_counter()

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

                    self._persist_status(tid, state)

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
                        "payload": task.payload,
                        "pipeline": task.pipeline,
                        "pipeline_step": task.pipeline_step,
                    }
            return None

    # ── Get Pending Tasks (for Task Market UI) ──────────────────────────

    def get_pending_tasks(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return all PENDING tasks with metadata (newest first).

        Used by the Task Market UI in the Developer tab so workers can
        browse available tasks before claiming.
        """
        result: list[dict[str, Any]] = []
        now = time.time()
        with self._lock:
            for tid, state in self._status.items():
                if state["status"] != "PENDING":
                    continue
                task = self._tasks.get(tid)
                if task is None:
                    continue
                result.append({
                    "task_id": tid,
                    "user_id": task.user_id,
                    "skill_id": task.skill_id,
                    "task_name": task.task_name or task.skill_id,
                    "description": task.description,
                    "is_custom": task.is_custom,
                    "credit_score_required": task.credit_score_required,
                    "max_budget": task.max_budget,
                    "developer_premium": task.developer_premium,
                    "compute_tier": task.compute_tier,
                    "payload": task.payload,
                    "pipeline": task.pipeline,
                    "asin": task.asin,
                    "ts": now,
                })
        # Newest first (reverse insertion order)
        result.reverse()
        return result[:limit]

    # ── Claim Specific Task (by task_id, with credit check) ────────────

    def claim_specific_task(
        self, task_id: str, worker_id: str, credit_score: int = 0,
    ) -> Optional[Dict[str, Any]]:
        """Atomically claim a specific PENDING task by ID.

        If the task is ``is_custom``, validates that ``credit_score >=
        task.credit_score_required``.  Returns the enriched task dict on
        success, or ``None`` if the task doesn't exist, isn't PENDING, or
        the credit check fails.
        """
        with self._lock:
            state = self._status.get(task_id)
            if state is None or state["status"] != "PENDING":
                return None

            task = self._tasks.get(task_id)
            if task is None:
                return None

            # Credit score gate for custom tasks
            if task.is_custom and credit_score < task.credit_score_required:
                logger.warning(
                    "CLAIM_SPECIFIC %s — worker '%s' credit %d < required %d",
                    task_id, worker_id, credit_score, task.credit_score_required,
                )
                return None

            state["status"] = "CLAIMED"
            state["worker_id"] = worker_id
            state["claimed_at"] = time.time()

            self._persist_status(task_id, state)

            logger.info(
                "CLAIM_SPECIFIC %s → worker '%s'  (custom=%s  credit=%d)",
                task_id, worker_id, task.is_custom, credit_score,
            )
            return {
                "task_id": task_id,
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
                "payload": task.payload,
                "pipeline": task.pipeline,
                "pipeline_step": task.pipeline_step,
            }

    # ── Complete ───────────────────────────────────────────────────────────

    def complete_task(
        self,
        task_id: str,
        status: str,
        detail: Optional[DynamicSettlementDetail] = None,
    ) -> Dict[str, Any]:
        """Mark a CLAIMED task as SUCCESS or FAILED.

        For pipeline tasks on an intermediate step (SUCCESS + more steps
        remaining), the task is re-queued as PENDING with the next skill_id
        and pipeline_step advanced.  In this case no settlement detail is
        recorded — only the final step triggers escrow settlement.

        Returns a dict with:
          - ``completed``: True if the task is fully done
          - ``settle``: True if escrow settlement should happen
          - ``pipeline_step``: current step index (0-based)
          - ``total_steps``: total pipeline length (1 for non-pipeline)
        """
        with self._lock:
            state = self._status.get(task_id)
            if state is None:
                logger.warning("COMPLETE %s — unknown task", task_id)
                return {"completed": False, "settle": False,
                        "pipeline_step": 0, "total_steps": 1}
            if state["status"] != "CLAIMED":
                logger.warning(
                    "COMPLETE %s — expected CLAIMED, got %s",
                    task_id, state["status"],
                )
                return {"completed": False, "settle": False,
                        "pipeline_step": 0, "total_steps": 1}

            if status == "SUCCESS":
                task = self._tasks.get(task_id)
                if task and task.pipeline and task.pipeline_step < len(task.pipeline) - 1:
                    # ── Intermediate pipeline step ──
                    # Store context for this step
                    context_key = f"{task_id}:step_{task.pipeline_step}"
                    context_data = {
                        "skill_id": task.skill_id,
                        "step": task.pipeline_step,
                        "worker_id": state.get("worker_id"),
                    }
                    self._persist_context(context_key, context_data)

                    # Advance to next step
                    task.pipeline_step += 1
                    task.skill_id = task.pipeline[task.pipeline_step]

                    # Re-queue as PENDING
                    state["status"] = "PENDING"
                    state["worker_id"] = None
                    state["claimed_at"] = None

                    self._persist_task(task_id, task)
                    self._persist_status(task_id, state)

                    logger.info(
                        "PIPELINE %s → step %d/%d (%s)",
                        task_id, task.pipeline_step + 1, len(task.pipeline),
                        task.skill_id,
                    )
                    return {
                        "completed": False,
                        "settle": False,
                        "pipeline_step": task.pipeline_step,
                        "total_steps": len(task.pipeline),
                    }

            # ── Final step (or non-pipeline / FAILED) ──
            state["status"] = status
            if detail is not None:
                self._results[task_id] = detail
                self._persist_result(task_id, detail)

            self._persist_status(task_id, state)

            total = 1
            task = self._tasks.get(task_id)
            if task and task.pipeline:
                total = len(task.pipeline)

            logger.info(
                "COMPLETE %s → %s  (worker='%s')",
                task_id, status, state["worker_id"],
            )
            return {
                "completed": True,
                "settle": status == "SUCCESS",
                "pipeline_step": task.pipeline_step if task else 0,
                "total_steps": total,
            }

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

                    self._persist_status(tid, state)

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

    # ── PoT signature storage ──────────────────────────────────────────────

    def set_pot_signature(self, task_id: str, pot_sig: str) -> None:
        """Store a Proof-of-Task signature in the task status.

        Called from the gateway server after ``BillingEngine.request_settlement``
        completes, so that ``/api/tasks/{task_id}/status`` can include it.
        """
        with self._lock:
            state = self._status.get(task_id)
            if state is not None:
                state["pot_signature"] = pot_sig
                self._persist_status(task_id, state)

    def get_pot_signature(self, task_id: str) -> str | None:
        """Return the stored PoT signature, or ``None``."""
        with self._lock:
            state = self._status.get(task_id)
            if state is None:
                return None
            return state.get("pot_signature")

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

    @property
    def succeeded_count(self) -> int:
        with self._lock:
            return sum(
                1 for s in self._status.values() if s["status"] == "SUCCESS"
            )

    @property
    def claimed_count(self) -> int:
        with self._lock:
            return sum(
                1 for s in self._status.values() if s["status"] == "CLAIMED"
            )

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
