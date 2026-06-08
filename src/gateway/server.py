"""Gateway Server — production-grade FastAPI task dispatcher for AIMS (Layer 5).

Provides HTTP endpoints for DePIN workers to claim and submit tasks,
with JSON Schema validation, tier-based gas billing, and slashing.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field

from src.gateway.broker import TaskBroker
from src.ledger.mock_counter import MockLedger
from src.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)

# ── Global instances (singleton per process) ──────────────────────────────

ledger = MockLedger()
broker = TaskBroker(ledger)
registry = SkillRegistry()

app = FastAPI(
    title="AIMS Gateway",
    version="1.0.0",
    description="AIMS DePIN Network — Task Dispatch & Settlement Gateway",
)


# ── Pydantic models ────────────────────────────────────────────────────────


class ClaimRequest(BaseModel):
    worker_id: str = Field(..., min_length=1, max_length=128, description="Unique worker identifier")


class ClaimResponse(BaseModel):
    task_id: str
    skill_id: str
    compute_tier: int
    developer_premium: float
    max_budget: float
    escrow_id: str
    user_id: str
    asin: str


class SubmitRequest(BaseModel):
    task_id: str = Field(..., min_length=1, max_length=64)
    worker_id: str = Field(..., min_length=1, max_length=128)
    result_data: dict[str, Any] = Field(..., description="Task output as JSON object")


class SubmitResponse(BaseModel):
    task_id: str
    worker_id: str
    outcome: str  # "COMPLETED" | "REFUNDED" | "REJECTED"
    gas_cost: float = 0.0
    total_cost: float = 0.0
    platform_tax: float = 0.0
    developer_payout: float = 0.0
    unused_refund: float = 0.0
    error: str = ""


class HealthResponse(BaseModel):
    status: str
    tasks_pending: int
    tasks_completed: int
    workers_registered: int
    treasury_usdt: float


# ── Helper: run blocking calls off the event loop ─────────────────────────


async def _run_in_thread(fn, *args, **kwargs):
    """Run a synchronous function in a thread pool so we don't block the event loop."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))


# ── Routes ─────────────────────────────────────────────────────────────────


@app.post("/api/tasks/claim")
async def claim_task(req: ClaimRequest):
    """Claim a PENDING task from the broker.

    Returns the task metadata on success, or **204 No Content** if the
    queue is empty.
    """
    task = await _run_in_thread(broker.claim_task, req.worker_id)
    if task is None:
        return Response(status_code=204)

    return ClaimResponse(
        task_id=task["task_id"],
        skill_id=task.get("skill_id", ""),
        compute_tier=task.get("compute_tier", 1),
        developer_premium=task.get("developer_premium", 0.0),
        max_budget=task.get("max_budget", 0.0),
        escrow_id=task["escrow_hold"].escrow_id,
        user_id=task["user_id"],
        asin=task["asin"],
    )


@app.post("/api/tasks/submit")
async def submit_task(req: SubmitRequest):
    """Submit a completed task result for validation and settlement.

    **Validation** — The result is checked against the skill's
    ``output_schema`` (JSON Schema).  If the schema is missing, a basic
    ``isinstance(result_data, dict)`` guard is applied.

    **On valid result:**
      1. ``execution_time = now − claimed_at`` (wall-clock)
      2. ``release_escrow_dynamic(success=True)`` with tier-based gas billing
      3. Task marked ``SUCCESS``

    **On invalid result:**
      1. ``apply_penalty()`` — strike the worker (3 strikes → $1 slash)
      2. Task marked ``FAILED``

    Returns an itemised billing receipt on success, or an error response
    on validation failure.
    """
    # ── 1. Lookup task & verify ownership ─────────────────────────────
    status = await _run_in_thread(broker.get_task_status, req.task_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Task {req.task_id} not found")

    claimed_worker = status.get("worker_id")
    if claimed_worker != req.worker_id:
        raise HTTPException(
            status_code=403,
            detail=f"Task {req.task_id} claimed by '{claimed_worker}', not '{req.worker_id}'",
        )

    if status["status"] != "CLAIMED":
        raise HTTPException(
            status_code=409,
            detail=f"Task {req.task_id} is {status['status']}, expected CLAIMED",
        )

    claimed_at = status.get("claimed_at") or time.time()

    # ── 2. Load task metadata & skill manifest ─────────────────────────
    task_meta = await _run_in_thread(broker.get_task_meta, req.task_id)
    if task_meta is None:
        raise HTTPException(status_code=404, detail=f"Metadata for {req.task_id} not found")

    skill_id = task_meta.skill_id
    manifest = await _run_in_thread(registry.get, skill_id) if skill_id else None

    # ── 3. JSON Schema validation ─────────────────────────────────────
    schema = (manifest.output_schema or {}) if manifest else {}
    if schema:
        valid = await _run_in_thread(
            broker.validate_result_generic, req.result_data, schema, req.worker_id,
        )
    else:
        valid = isinstance(req.result_data, dict)

    if not valid:
        # Penalty already applied inside validate_result_generic
        await _run_in_thread(broker.complete_task, req.task_id, "FAILED")
        return SubmitResponse(
            task_id=req.task_id,
            worker_id=req.worker_id,
            outcome="REJECTED",
            error="Result failed JSON Schema validation",
        )

    # ── 4. Calculate execution time & settle escrow ──────────────────
    execution_time = max(time.time() - claimed_at, 0.1)

    skill_meta = {
        "compute_tier": task_meta.compute_tier,
        "developer_premium": task_meta.developer_premium,
        "skill_id": task_meta.skill_id,
    }

    detail = await _run_in_thread(
        ledger.release_escrow_dynamic,
        task_meta.escrow_hold.escrow_id,
        user_id=task_meta.user_id,
        developer_id=req.worker_id,
        execution_time=execution_time,
        skill_meta=skill_meta,
        success=True,
    )

    await _run_in_thread(broker.complete_task, req.task_id, "SUCCESS", detail)

    return SubmitResponse(
        task_id=req.task_id,
        worker_id=req.worker_id,
        outcome=detail.outcome if detail else "COMPLETED",
        gas_cost=detail.gas_cost if detail else 0.0,
        total_cost=detail.total_cost if detail else 0.0,
        platform_tax=detail.platform_tax if detail else 0.0,
        developer_payout=detail.developer_payout if detail else 0.0,
        unused_refund=detail.unused_refund if detail else 0.0,
    )


@app.get("/api/health")
async def health():
    """Health check returning broker and ledger state."""
    pending = await _run_in_thread(lambda: broker.pending_count)
    completed = await _run_in_thread(lambda: broker.completed_count)
    treasury = await _run_in_thread(lambda: ledger.founder_treasury_usdt)

    # Count registered workers by inspecting staked collateral keys
    staked_keys = await _run_in_thread(lambda: list(ledger._staked_collateral.keys()))
    workers_registered = len(staked_keys)

    return HealthResponse(
        status="healthy",
        tasks_pending=pending,
        tasks_completed=completed,
        workers_registered=workers_registered,
        treasury_usdt=treasury,
    )
