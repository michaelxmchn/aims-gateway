"""Gateway Server — production-grade FastAPI task dispatcher for AIMS (Layer 5).

Provides HTTP endpoints for DePIN workers to claim and submit tasks,
with JSON Schema validation, tier-based gas billing, slashing, and
HMAC-SHA256 signature authentication.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
from threading import Lock
from typing import Any

from fastapi import FastAPI, File, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field

from src.gateway.broker import TaskBroker
from src.gateway.skill_store import SkillStore, SkillStoreError
from src.gateway.storage import Storage
from src.ledger.mock_counter import MockLedger
from src.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)

# ── Auth config ─────────────────────────────────────────────────────────────

AIMS_SIGNING_SECRET: bytes = os.getenv("AIMS_SIGNING_SECRET", "AIMS_MOCK_SECRET_2026").encode()
"""Shared secret for HMAC-SHA256 request signing.

Reads from the ``AIMS_SIGNING_SECRET`` environment variable in production
(Fly.io secrets).  Falls back to ``AIMS_MOCK_SECRET_2026`` for local dev/testing.
"""

SIGNATURE_TIMEOUT: float = 300.0
"""Maximum age (seconds) for a signed request — replay protection."""


def compute_signature(body: bytes, timestamp: str, user_id: str) -> str:
    """HMAC-SHA256 of ``body + b'|' + timestamp + b'|' + user_id``."""
    msg = body + b"|" + timestamp.encode() + b"|" + user_id.encode()
    return hmac.new(AIMS_SIGNING_SECRET, msg, hashlib.sha256).hexdigest()


def verify_signature(body: bytes, timestamp: str, user_id: str, sig: str) -> bool:
    """Constant-time comparison of the provided signature against the computed one."""
    expected = compute_signature(body, timestamp, user_id)
    return hmac.compare_digest(expected, sig)


# ── Global instances (singleton per process) ──────────────────────────────

storage = Storage()
ledger = MockLedger(storage=storage)
broker = TaskBroker(ledger, storage=storage)
registry = SkillRegistry()
skill_store = SkillStore(storage=storage)

# Load any previously uploaded skills into the registry
skill_store.load_into_registry(registry)

# Worker heartbeat tracking: worker_id → last_seen_unix_ts
worker_heartbeats: dict[str, float] = {}
_heartbeat_lock = Lock()

app = FastAPI(
    title="AIMS Gateway",
    version="1.0.0",
    description="AIMS DePIN Network — Task Dispatch & Settlement Gateway",
)


# ── Signature verification middleware (applied to /api/tasks/*) ────────────


@app.middleware("http")
async def verify_signature_middleware(request: Request, call_next):
    """Verify HMAC-SHA256 signature on all ``/api/*`` requests (except health & admin).

    Required headers:
      - ``X-Signature``  — hex-encoded HMAC-SHA256
      - ``X-Timestamp``  — UNIX epoch seconds as string
      - ``X-User-ID``    — worker/user identifier

    The signature is computed over::

        HMAC-SHA256(secret, body_bytes + "|" + timestamp + "|" + user_id)

    Requests with a timestamp older than ``SIGNATURE_TIMEOUT`` (300 s)
    are rejected as replay attempts.
    """
    path = request.url.path

    # Skip health and admin endpoints
    if path == "/api/health" or path.startswith("/api/admin/"):
        return await call_next(request)

    # Skip HMAC auth for multipart uploads (body can't be pre-signed trivially)
    if path == "/api/skills/upload":
        return await call_next(request)

    # Require auth on all other /api/ endpoints
    if path.startswith("/api/"):
        sig = request.headers.get("x-signature", "")
        ts = request.headers.get("x-timestamp", "")
        uid = request.headers.get("x-user-id", "")

        if not sig or not ts or not uid:
            return Response(
                status_code=403,
                content=json.dumps({"detail": "Missing signature headers"}),
                media_type="application/json",
            )

        # Replay protection — reject requests older than SIGNATURE_TIMEOUT
        try:
            ts_float = float(ts)
        except ValueError:
            return Response(
                status_code=403,
                content=json.dumps({"detail": "Invalid X-Timestamp"}),
                media_type="application/json",
            )

        if abs(time.time() - ts_float) > SIGNATURE_TIMEOUT:
            return Response(
                status_code=403,
                content=json.dumps({"detail": "Timestamp outside allowed window — possible replay"}),
                media_type="application/json",
            )

        body = await request.body()
        if not verify_signature(body, ts, uid, sig):
            return Response(
                status_code=403,
                content=json.dumps({"detail": "Invalid signature"}),
                media_type="application/json",
            )

    response = await call_next(request)
    return response


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
    payload: dict[str, Any] | None = None
    skill_logic_url: str | None = None
    """URL where the worker can fetch ``logic.py`` for dynamic skills."""


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
    tasks_succeeded: int
    workers_registered: int
    workers_active: int = 0
    treasury_usdt: float


class HeartbeatRequest(BaseModel):
    worker_id: str = Field(..., min_length=1, max_length=128)


class HeartbeatResponse(BaseModel):
    status: str
    worker_id: str


class UploadResponse(BaseModel):
    skill_id: str
    name: str
    version: str


class RunRequest(BaseModel):
    skill_id: str = Field(..., min_length=1, max_length=64)
    params: dict[str, Any] = Field(default_factory=dict)
    user_id: str = Field(..., min_length=1, max_length=128)
    developer_premium: float = Field(default=0.0, ge=0.0)
    max_budget: float = Field(default=2.0, ge=0.0)
    compute_tier: int = Field(default=1, ge=1, le=3)


class RunResponse(BaseModel):
    task_id: str
    status: str = "PENDING"


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    worker_id: str | None = None
    result: dict[str, Any] | None = None
    outcome: str | None = None


# ── Helper: run blocking calls off the event loop ─────────────────────────


async def _run_in_thread(fn, *args, **kwargs):
    """Run a synchronous function in a thread pool so we don't block the event loop."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))


# ── Admin / test-only endpoints (no signature required) ────────────────────


class SetupResponse(BaseModel):
    seeded: bool
    user_balance: float
    tasks_published: int


@app.post("/api/admin/setup", response_model=SetupResponse)
async def admin_setup():
    """Seed test data into the ledger and publish sample tasks.

    Intended for load-test / unattended-testing scenarios only.
    """
    user_id = "loadtest_user"
    dev_id = "loadtest_dev"

    ledger.seed_usdt(user_id, 10000.0)
    ledger.seed_dev_usdt(dev_id, 10000.0)

    # Register a worker identity for the dev
    from src.chain.settlement import ChainSettlement
    chain = ChainSettlement("http://localhost")
    chain.simulate_stripe_webhook(user_id, 10000.0, ledger)

    count = 0
    for i in range(100):
        tid = await _run_in_thread(
            broker.publish_task,
            user_id=user_id,
            asin=f"LOAD-{i:04d}",
            developer_premium=0.01,
            max_budget=2.0,
            skill_id="amazon_scraper",
            compute_tier=1,
        )
        if tid:
            count += 1

    return SetupResponse(
        seeded=True,
        user_balance=ledger.get_user_usdt(user_id),
        tasks_published=count,
    )


# ── Routes ─────────────────────────────────────────────────────────────────


@app.post("/api/tasks/claim")
async def claim_task(req: ClaimRequest, request: Request):
    """Claim a PENDING task from the broker.

    Returns the task metadata on success, or **204 No Content** if the
    queue is empty.
    """
    task = await _run_in_thread(broker.claim_task, req.worker_id)
    if task is None:
        return Response(status_code=204)

    skill_id = task.get("skill_id", "")
    base_url = str(request.base_url).rstrip("/")
    logic_url = f"{base_url}/api/skills/{skill_id}/logic" if skill_id else None

    return ClaimResponse(
        task_id=task["task_id"],
        skill_id=skill_id,
        compute_tier=task.get("compute_tier", 1),
        developer_premium=task.get("developer_premium", 0.0),
        max_budget=task.get("max_budget", 0.0),
        escrow_id=task["escrow_hold"].escrow_id,
        user_id=task["user_id"],
        asin=task["asin"],
        payload=task.get("payload"),
        skill_logic_url=logic_url,
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


@app.post("/api/workers/heartbeat")
async def worker_heartbeat(req: HeartbeatRequest):
    """Receive a keep-alive heartbeat from a worker.

    Records ``worker_id → time.time()`` so the health endpoint can report
    the number of currently active workers.
    """
    with _heartbeat_lock:
        worker_heartbeats[req.worker_id] = time.time()

    # Prune workers that haven't reported in 60 s
    cutoff = time.time() - 60.0
    stale = [wid for wid, ts in worker_heartbeats.items() if ts < cutoff]
    for wid in stale:
        worker_heartbeats.pop(wid, None)

    return HeartbeatResponse(status="ack", worker_id=req.worker_id)


@app.get("/api/health")
async def health():
    """Health check returning broker, ledger, and worker-liveness state."""
    pending = await _run_in_thread(lambda: broker.pending_count)
    completed = await _run_in_thread(lambda: broker.completed_count)
    succeeded = await _run_in_thread(lambda: broker.succeeded_count)
    treasury = await _run_in_thread(lambda: ledger.founder_treasury_usdt)

    # Count registered workers by inspecting staked collateral keys
    staked_keys = await _run_in_thread(lambda: list(ledger._staked_collateral.keys()))
    workers_registered = len(staked_keys)

    # Count active workers (heartbeat within last 60 s)
    cutoff = time.time() - 60.0
    with _heartbeat_lock:
        workers_active = sum(1 for ts in worker_heartbeats.values() if ts >= cutoff)

    return HealthResponse(
        status="healthy",
        tasks_pending=pending,
        tasks_completed=completed,
        tasks_succeeded=succeeded,
        workers_registered=workers_registered,
        workers_active=workers_active,
        treasury_usdt=treasury,
    )


# ── Dynamic Skill Upload & Execution ─────────────────────────────────────


@app.post("/api/skills/upload", response_model=UploadResponse)
async def upload_skill(zip_file: UploadFile = File(...)):
    """Upload a zip containing ``manifest.json`` + ``logic.py``.

    The archive is validated, extracted, and installed into the local
    filesystem.  Metadata is persisted in Redis.

    Returns the ``skill_id``, ``name``, and ``version`` on success.
    """
    zip_bytes = await zip_file.read()
    try:
        result = skill_store.install_zip(zip_bytes, author=zip_file.filename or "api")
    except SkillStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Register in the runtime registry so workers can find it
    raw_manifest = skill_store.get_manifest(result["skill_id"])
    logic_path = skill_store.get_logic_path(result["skill_id"])
    if raw_manifest:
        registry.install_skill(result["skill_id"], raw_manifest, str(logic_path) if logic_path else None)

    return UploadResponse(
        skill_id=result["skill_id"],
        name=result["name"],
        version=result["version"],
    )


@app.get("/api/skills/{skill_id}/logic")
async def serve_logic(skill_id: str):
    """Serve the ``logic.py`` source for a dynamically uploaded skill.

    Workers fetch this at startup to load the skill code dynamically.
    """
    source = skill_store.get_logic_source(skill_id)
    if source is None:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found or has no logic.py")
    return Response(content=source, media_type="text/plain")


@app.post("/api/run", response_model=RunResponse)
async def run_skill(req: RunRequest):
    """Universal execution endpoint — validate input, enqueue a task, return task_id.

    1. Looks up the skill manifest for ``input_schema`` validation.
    2. Validates ``params`` against the required fields from the schema.
    3. Creates an escrow hold and publishes a PENDING broker task.
    4. The task is picked up by an idle worker via the normal claim cycle.

    The caller polls ``GET /api/tasks/{task_id}/status`` to learn the outcome.
    """
    # ── 1. Look up manifest ─────────────────────────────────────────────
    manifest = registry.get(req.skill_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"Skill '{req.skill_id}' not found in registry")

    # ── 2. Validate params against input_schema ─────────────────────────
    schema = manifest.input_schema or {}
    required = schema.get("required", [])
    for field in required:
        if field not in req.params:
            raise HTTPException(
                status_code=400,
                detail=f"Missing required parameter: {field}",
            )

    props = schema.get("properties", {})
    for prop_name, prop_schema in props.items():
        if prop_name not in req.params:
            continue
        expected_type = prop_schema.get("type")
        val = req.params[prop_name]
        if expected_type == "string" and not isinstance(val, str):
            raise HTTPException(status_code=400, detail=f"{prop_name}: expected string, got {type(val).__name__}")
        elif expected_type == "number" and not isinstance(val, (int, float)):
            raise HTTPException(status_code=400, detail=f"{prop_name}: expected number, got {type(val).__name__}")
        elif expected_type == "boolean" and not isinstance(val, bool):
            raise HTTPException(status_code=400, detail=f"{prop_name}: expected boolean, got {type(val).__name__}")

    # ── 3. Create escrow & publish task ─────────────────────────────────
    task_id = await _run_in_thread(
        broker.publish_task,
        user_id=req.user_id,
        asin=f"dynamic-{req.skill_id}",
        developer_premium=req.developer_premium,
        max_budget=req.max_budget,
        skill_id=req.skill_id,
        compute_tier=req.compute_tier,
        payload=req.params,
    )
    if task_id is None:
        raise HTTPException(status_code=402, detail="Insufficient balance for escrow hold")

    return RunResponse(task_id=task_id, status="PENDING")


@app.get("/api/tasks/{task_id}/status", response_model=TaskStatusResponse)
async def task_status(task_id: str):
    """Return the current status of a task (for polling after ``/api/run``)."""
    status = await _run_in_thread(broker.get_task_status, task_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    result = None
    outcome = None
    if status["status"] == "SUCCESS":
        detail = await _run_in_thread(lambda: broker._results.get(task_id))
        if detail:
            result = getattr(detail, "detail", None) or {}
            outcome = getattr(detail, "outcome", None)
    elif status["status"] == "FAILED":
        outcome = "FAILED"

    return TaskStatusResponse(
        task_id=task_id,
        status=status["status"],
        worker_id=status.get("worker_id"),
        result=result,
        outcome=outcome,
    )
