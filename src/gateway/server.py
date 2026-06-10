"""Gateway Server — production-grade FastAPI task dispatcher for AIMS (Layer 5).

Provides HTTP endpoints for DePIN workers to claim and submit tasks,
with JSON Schema validation, tier-based gas billing, slashing, and
EIP-712 typed-data signature authentication.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from threading import Lock
from typing import Any

from eth_account import Account
from fastapi import FastAPI, File, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field

from eth_account.messages import encode_defunct

from src.chain.nonce_manager import NonceManager
from src.chain.pot import POTManager
from src.gateway.broker import TaskBroker
from src.gateway.skill_store import SkillStore, SkillStoreError
from src.gateway.storage import Storage
from src.ledger.mock_counter import MockLedger
from src.skills.registry import SkillRegistry
from src.gateway.billing import BillingEngine

logger = logging.getLogger(__name__)

# ── Auth config ─────────────────────────────────────────────────────────────

SIGNATURE_TIMEOUT: float = 300.0
"""Maximum age (seconds) for a signed request — replay protection."""

AIMS_GATEWAY_PRIVATE_KEY: str = os.getenv("AIMS_GATEWAY_PRIVATE_KEY", "")
"""Gateway ECDSA private key for signing Proof-of-Task receipts."""

AIMS_CONTRACT_ADDRESS: str = os.getenv(
    "AIMS_CONTRACT_ADDRESS",
    "0x0000000000000000000000000000000000000001",
)

# ── Rate limiter config ──────────────────────────────────────────────────────

RATE_LIMIT_WINDOW: int = 60
"""Sliding window size in seconds for the per-wallet rate limiter."""

RATE_LIMIT_MAX: int = 100
"""Maximum requests per ``RATE_LIMIT_WINDOW`` per wallet address."""

RATE_LIMIT_NS = "rate:limiter"
"""Storage namespace for rate limiter counters."""

# ── Global instances (singleton per process) ──────────────────────────────

storage = Storage()
ledger = MockLedger(storage=storage)
broker = TaskBroker(ledger, storage=storage)
registry = SkillRegistry()
skill_store = SkillStore(storage=storage)

# Load any previously uploaded skills into the registry
skill_store.load_into_registry(registry)

# Web3 billing singletons
nonce_manager = NonceManager(storage)
pot_manager = POTManager(storage, AIMS_GATEWAY_PRIVATE_KEY) if AIMS_GATEWAY_PRIVATE_KEY else None

# Lazy-init contract via ChainSettlement (InMemory or Web3 based on env)
from src.chain.settlement import ChainSettlement
_chain_settlement = ChainSettlement(os.getenv("AIMS_RPC_URL", ""))
_contract = _chain_settlement.contract  # InMemorySettlementContract or Web3SettlementContract

billing = BillingEngine(
    storage=storage,
    contract_client=_contract,
    pot_manager=pot_manager,
    gateway_signing_key=AIMS_GATEWAY_PRIVATE_KEY,
)

# Worker heartbeat tracking: worker_id → last_seen_unix_ts
worker_heartbeats: dict[str, float] = {}
_heartbeat_lock = Lock()

app = FastAPI(
    title="AIMS Gateway",
    version="1.0.0",
    description="AIMS DePIN Network — Task Dispatch & Settlement Gateway",
)

# ── EIP-191 personal_sign wallet verification middleware ────────────────────

EXEMPT_PATHS = {
    "/api/health",
    "/api/discovery",
    "/api/skills/upload",
}


@app.middleware("http")
async def verify_wallet_middleware(request: Request, call_next):
    """Verify EIP-191 wallet signature on all ``/api/*`` requests.

    Required headers:
      - ``X-Wallet-Address`` — EVM wallet address (0x-prefixed, 42 chars)
      - ``X-Signature``      — EIP-191 ``personal_sign`` hex signature
      - ``X-Timestamp``      — UNIX epoch seconds as string (300 s window)

    The middleware:
    1. Validates ``X-Wallet-Address`` is a valid EVM address.
    2. Checks the timestamp is within the 300 s window.
    3. Recovers the signer by EIP-191 ``personal_sign`` over the raw body.
    4. Verifies the signer matches ``X-Wallet-Address``.

    Exempt paths: ``/api/health``, ``/api/discovery``, ``/api/skills/upload``.
    """
    path = request.url.path

    if path in EXEMPT_PATHS or path.startswith("/api/admin/"):
        return await call_next(request)

    # GET requests to /api/tasks/ are public (status polling + PoT retrieval)
    if request.method == "GET" and path.startswith("/api/tasks/"):
        return await call_next(request)

    if not path.startswith("/api/"):
        return await call_next(request)

    # ── Debug: log all incoming headers ──────────────────────────────
    headers_dict = dict(request.headers)
    logger.debug("Incoming headers: %s", headers_dict)
    print(f"[AIMS] Incoming headers for {request.method} {path}: {headers_dict}")

    # ── Read headers (case-insensitive fallback chain) ───────────────
    # Fly.io/Nginx reverse proxies may forward headers with different
    # casing.  Try the canonical form first, then lower-case fallback.
    def _get_header(name: str) -> str:
        """Fetch a header by name with case-insensitive fallback."""
        raw = request.headers.get(name) or request.headers.get(name.lower()) or request.headers.get(name.upper())
        if raw is None:
            # Last resort: scan all header keys case-insensitively
            lower = name.lower()
            for key, value in request.headers.items():
                if key.lower() == lower:
                    return value
        return raw or ""

    wallet_address = _get_header("X-Wallet-Address")
    if not wallet_address:
        wallet_address = _get_header("X-User-ID")
    signature = _get_header("X-Signature")
    ts = _get_header("X-Timestamp")

    # ── Report exactly which headers are missing ─────────────────────
    missing = []
    if not wallet_address:
        missing.append("X-Wallet-Address (or X-User-ID)")
    if not signature:
        missing.append("X-Signature")
    if not ts:
        missing.append("X-Timestamp")

    if missing:
        return Response(
            status_code=403,
            content=json.dumps({
                "detail": f"Missing EIP-191 headers: {', '.join(missing)}",
                "received_headers": list(headers_dict.keys()),
            }),
            media_type="application/json",
        )

    # ── 1. Validate EVM address ──────────────────────────────────────
    if not wallet_address.startswith("0x") or len(wallet_address) != 42:
        return Response(
            status_code=403,
            content=json.dumps({"detail": "X-Wallet-Address must be a valid EVM address (0x-prefixed, 42 chars)"}),
            media_type="application/json",
        )

    # ── 2. Timestamp window ──────────────────────────────────────────
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

    # ── 3. Sliding-window rate limiter (per wallet address) ──────────
    window_start = int(time.time() // RATE_LIMIT_WINDOW)
    rate_key = f"{RATE_LIMIT_NS}:{wallet_address}:{window_start}"
    current_count = storage.incr(rate_key)
    if current_count == 1 and storage.is_persistent:
        storage._redis.expire(rate_key, RATE_LIMIT_WINDOW * 2)
    if current_count > RATE_LIMIT_MAX:
        return Response(
            status_code=429,
            content=json.dumps({
                "detail": f"Rate limit exceeded: {RATE_LIMIT_MAX} requests per {RATE_LIMIT_WINDOW}s per wallet",
            }),
            media_type="application/json",
        )

    # ── 4. Verify EIP-191 personal_sign signature ────────────────────
    body = await request.body()
    try:
        signable_message = encode_defunct(primitive=body)
        recovered = Account.recover_message(signable_message, signature=signature)
    except Exception as exc:
        return Response(
            status_code=403,
            content=json.dumps({"detail": f"Signature verification failed: {exc}"}),
            media_type="application/json",
        )

    if recovered.lower() != wallet_address.lower():
        return Response(
            status_code=403,
            content=json.dumps({
                "detail": "Invalid EIP-191 signature — recovered signer does not match X-Wallet-Address",
            }),
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
    outcome: str  # "COMPLETED" | "REFUNDED" | "REJECTED" | "PIPELINE_CONTINUED"
    gas_cost: float = 0.0
    total_cost: float = 0.0
    platform_tax: float = 0.0
    developer_payout: float = 0.0
    unused_refund: float = 0.0
    pot: str | None = None
    """Proof-of-Task signature — worker presents this to claimReward() on-chain."""
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
    pipeline: list[str] | None = Field(default=None, description="Sequential skill IDs for task chaining. First element must match skill_id.")


class RunResponse(BaseModel):
    task_id: str
    status: str = "PENDING"


# ── Wallet & Balance models ────────────────────────────────────────────────

class DepositRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128, description="User or agent identifier")
    amount: float = Field(..., gt=0.0, description="Credit amount to deposit")


class DepositResponse(BaseModel):
    user_id: str
    amount: float
    new_balance: float


class BalanceResponse(BaseModel):
    user_id: str
    credits: float
    status: str = "PENDING"


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    worker_id: str | None = None
    result: dict[str, Any] | None = None
    outcome: str | None = None
    pot: str | None = None
    """Proof-of-Task signature — present this to claimReward() on-chain."""


class PotResponse(BaseModel):
    task_id: str
    worker_address: str
    signature: str


# ── Static capability definitions (for discovery endpoint) ───────────────

SKILL_CAPABILITIES: dict[str, list[str]] = {
    "amazon_scraper": ["web-scraping", "e-commerce", "price-tracking"],
    "code_security_audit": ["code-analysis", "security", "static-analysis"],
    "git_changelog": ["git", "automation", "documentation"],
    "data_analyzer": ["data-analysis", "visualization"],
    "buggy_skill": ["testing", "debugging"],
    "dashboard_skill": ["visualization", "monitoring", "dashboard"],
}


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


@app.get("/api/discovery")
async def discovery():
    """Auto-discovery endpoint — returns the full API surface as self-documenting JSON."""
    base_url = "https://api.aimsgateway.com"
    skills_list = []
    all_manifests = await _run_in_thread(registry.get_all_manifests)
    for m in all_manifests:
        skills_list.append({
            "id": m.name,
            "description": m.description,
            "execution": {"endpoint": "/api/run", "method": "POST"},
            "resources": {
                "logic_script_url": f"{base_url}/api/skills/{m.name}/logic",
                "manifest_url": f"{base_url}/api/discovery",
            },
            "capabilities": SKILL_CAPABILITIES.get(m.name, []),
            "manifest": {
                "name": m.name,
                "description": m.description,
                "version": m.version,
                "author": m.author,
                "tags": m.tags,
                "input_schema": m.input_schema,
                "output_schema": m.output_schema,
                "price_points": m.price_points,
                "staked_points": m.staked_points,
            },
        })

    return {
        "discovery_version": "1.0.0",
        "documentation_root": "https://raw.githubusercontent.com/michaelxmchn/aims-gateway/main/docs/MASTER_INDEX.md",
        "api": {
            "name": "AIMS Gateway",
            "version": "1.0.0",
            "description": "AI-Mediated Skill Network — Task Dispatch & Settlement Gateway",
            "protocol": "REST over HTTP",
            "content_type": "application/json",
        },
        "server": {"current_time": time.time(), "timezone": "UTC"},
        "authentication": {
            "scheme": "EIP-191",
            "description": (
                "Every POST to /api/* endpoints must include three signed headers. "
                "GET /api/discovery, GET /api/health, and POST /api/skills/upload are exempt."
            ),
            "headers": {
                "X-Wallet-Address": {"type": "string", "description": "EVM wallet address (0x-prefixed, 42 chars)"},
                "X-Signature": {"type": "string", "description": "EIP-191 personal_sign hex signature over the raw body"},
                "X-Timestamp": {"type": "string", "description": "UNIX epoch seconds (float). Must be within 300s."},
            },
            "example_curl": (
                '# EIP-191 personal_sign — see bootstrap_helper.py for the full flow\n'
                'WALLET="0x..."; TS=$(date +%s)\n'
                'BODY=\'{"skill_id":"amazon_scraper","params":{},"user_id":"$WALLET"}\'\n'
                '# Sign the raw body bytes via Python (eth_account):\n'
                '# from eth_account.messages import encode_defunct\n'
                '# sig = wallet.sign_message(encode_defunct(primitive=body.encode()))\n'
                'curl -X POST "$BASE_URL/api/run" \\\n'
                '  -H "X-Wallet-Address: $WALLET" -H "X-Signature: $SIG" \\\n'
                '  -H "X-Timestamp: $TS" \\\n'
                '  -H "Content-Type: application/json" -d "$BODY"'
            ),
        },
        "skills": skills_list,
        "endpoints": [
            {
                "category": "Task Management",
                "description": "Claim, submit, and monitor tasks.",
                "operations": [
                    {"method": "POST", "path": "/api/tasks/claim", "summary": "Claim a PENDING task.", "auth_required": True},
                    {"method": "POST", "path": "/api/tasks/submit", "summary": "Submit completed task result.", "auth_required": True},
                    {"method": "GET", "path": "/api/tasks/{task_id}/status", "summary": "Poll task status.", "auth_required": False},
                    {"method": "GET", "path": "/api/tasks/{task_id}/pot", "summary": "Fetch Proof-of-Task.", "auth_required": False},
                ],
            },
            {
                "category": "Skill Management",
                "description": "Upload, inspect, and execute skills.",
                "operations": [
                    {"method": "POST", "path": "/api/skills/upload", "summary": "Upload skill zip.", "auth_required": False},
                    {"method": "GET", "path": "/api/skills/{skill_id}/logic", "summary": "Fetch skill logic.py.", "auth_required": False},
                    {"method": "POST", "path": "/api/run", "summary": "Execute a skill.", "auth_required": True},
                ],
            },
            {
                "category": "Worker",
                "description": "Worker registration and liveness.",
                "operations": [
                    {"method": "POST", "path": "/api/workers/heartbeat", "summary": "Send keep-alive.", "auth_required": True},
                ],
            },
            {
                "category": "System",
                "description": "Health check, discovery, admin.",
                "operations": [
                    {"method": "GET", "path": "/api/health", "summary": "Return system health.", "auth_required": False},
                    {"method": "GET", "path": "/api/discovery", "summary": "This document.", "auth_required": False},
                ],
            },
            {
                "category": "Wallet & Credits",
                "description": "On-chain wallet operations.",
                "operations": [
                    {"method": "POST", "path": "/api/wallet/deposit", "summary": "Deposit USDC (proxy).", "auth_required": True},
                    {"method": "GET", "path": "/api/wallet/balance", "summary": "Check USDC balance.", "auth_required": True},
                ],
            },
        ],
        "links": {
            "openclaw_manifest": {
                "url": f"{base_url}/manifests/openclaw_skill.json",
                "description": "OpenClaw-compatible manifest for agent orchestration",
            },
            "health": {"url": f"{base_url}/api/health", "description": "Quick health check."},
        },
        "notes": [
            "Auth uses EIP-712 typed data signatures (not HMAC-SHA256).",
            "X-User-ID must be an EVM address (0x + 40 hex chars).",
            "X-Timestamp must be within 300s of server time (replay protection).",
            "X-Nonce must be monotonic per address (replay protection).",
            "X-Deadline prevents signature reuse beyond the specified time.",
            "Contract: AIMSSettlement on Base (USDC 6-decimals, 80/20 split).",
        ],
    }


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
    ``output_schema`` (JSON Schema).

    **On SUCCESS:**
      1. Release escrow with tier-based gas billing
      2. Request on-chain settlement via ``BillingEngine.request_settlement``
      3. Generate Proof-of-Task (PoT) for the worker
      4. Return PoT in the response

    **On FAILURE:**
      1. Apply penalty (strike)
      2. Release reservation (no on-chain settlement)
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
        await _run_in_thread(broker.complete_task, req.task_id, "FAILED")
        return SubmitResponse(
            task_id=req.task_id,
            worker_id=req.worker_id,
            outcome="REJECTED",
            error="Result failed JSON Schema validation",
        )

    # ── 4. Complete task (may re-queue for pipeline intermediate step) ─
    completion = await _run_in_thread(broker.complete_task, req.task_id, "SUCCESS")

    if not completion.get("settle", True):
        # Pipeline intermediate step — task re-queued as PENDING, no settlement
        return SubmitResponse(
            task_id=req.task_id,
            worker_id=req.worker_id,
            outcome="PIPELINE_CONTINUED",
            error=(
                f"Pipeline step {completion.get('pipeline_step', 0)}/"
                f"{completion.get('total_steps', 0)} completed"
            ),
        )

    # ── 5. Final step — calculate execution time & settle escrow ──────
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

    # ── 6. On-chain settlement & PoT generation ───────────────────────
    pot_sig: str | None = None
    # Use the locked worker address from broker storage (not self-reported)
    # to prevent worker-address tampering in the settlement flow.
    locked_worker = claimed_worker
    settlement = await _run_in_thread(
        billing.request_settlement,
        req.task_id,
        task_meta.user_id,
        locked_worker,
    )
    if settlement.get("status") == "COMPLETED":
        pot = settlement.get("pot")
        if pot is not None:
            pot_sig = pot.signature
            await _run_in_thread(broker.set_pot_signature, req.task_id, pot_sig)

    return SubmitResponse(
        task_id=req.task_id,
        worker_id=req.worker_id,
        outcome=detail.outcome if detail else "COMPLETED",
        gas_cost=detail.gas_cost if detail else 0.0,
        total_cost=detail.total_cost if detail else 0.0,
        platform_tax=detail.platform_tax if detail else 0.0,
        developer_payout=detail.developer_payout if detail else 0.0,
        unused_refund=detail.unused_refund if detail else 0.0,
        pot=pot_sig,
    )


# ── Wallet endpoints (proxy to on-chain contract) ─────────────────────────


@app.post("/api/wallet/deposit", response_model=DepositResponse)
async def wallet_deposit(req: DepositRequest):
    """Deposit credits into a user's on-chain wallet.

    In production: the user deposits directly into the contract.
    This endpoint proxies the deposit for convenience and testing.
    """
    # Convert float USDC to atomic units (6 decimals)
    amount_atomic = int(round(req.amount * 10**6))

    from src.chain.settlement import ChainSettlement
    chain = ChainSettlement(os.getenv("AIMS_RPC_URL", ""))
    contract = chain.contract

    # For InMemorySettlementContract, deposit directly
    contract.deposit(req.user_id, amount_atomic)

    new_balance = contract.get_user_balance(req.user_id)

    return DepositResponse(
        user_id=req.user_id,
        amount=req.amount,
        new_balance=float(new_balance) / 10**6,
    )


@app.get("/api/wallet/balance")
async def wallet_balance(user_id: str):
    """Get on-chain USDC balance for a user.

    Query parameter: ``?user_id=<evm_address>``.
    Reads from the settlement contract view function (no gas).
    """
    from src.chain.settlement import ChainSettlement
    chain = ChainSettlement(os.getenv("AIMS_RPC_URL", ""))
    contract = chain.contract
    balance_atomic = contract.get_user_balance(user_id)
    credits = float(balance_atomic) / 10**6

    return BalanceResponse(user_id=user_id, credits=credits)


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


@app.get("/api/tasks/{task_id}/pot")
async def task_pot(task_id: str):
    """Retrieve the Proof-of-Task for a completed task.

    The worker fetches this after task completion and presents the
    signature to ``claimReward()`` on the settlement contract.
    """
    pot = pot_manager.get_pot(task_id) if pot_manager else None
    if pot is None:
        raise HTTPException(status_code=404, detail=f"No PoT found for task {task_id}")

    return PotResponse(
        task_id=pot.task_id,
        worker_address=pot.worker_address,
        signature=pot.signature,
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

    # ── 3. Check on-chain balance (early exit) ──────────────────────────
    credit_balance = await _run_in_thread(billing.check_user_balance, req.user_id)
    if credit_balance < BillingEngine.COST_PER_TASK_USDC:
        required_str = f"{BillingEngine.COST_PER_TASK_USDC / 10**6:.6f}"
        balance_str = f"{credit_balance / 10**6:.6f}"
        raise HTTPException(
            status_code=402,
            detail=(
                f"Insufficient USDC balance. Required: {required_str}, "
                f"balance: {balance_str}"
            ),
        )

    # ── 3b. Budget control: max_fee vs minimum pipeline cost ────────────
    num_steps = len(req.pipeline) if req.pipeline else 1
    min_cost_atomic = BillingEngine.COST_PER_TASK_USDC * num_steps
    max_budget_atomic = int(round(req.max_budget * 10**6))
    if max_budget_atomic < min_cost_atomic:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Insufficient budget allocated. Minimum: "
                f"{min_cost_atomic / 10**6:.6f} USDC for {num_steps} step(s), "
                f"provided: {req.max_budget:.6f} USDC"
            ),
        )

    # ── 4. Auto-seed MockLedger if new wallet (dev/test mode) ────────────────
    usdt_balance = await _run_in_thread(ledger.get_user_usdt, req.user_id)
    if usdt_balance < 1.0:
        await _run_in_thread(ledger.seed_usdt, req.user_id, 50.0)
        logger.info("Auto-seeded MockLedger %s with 50.0 USDT (dev mode)", req.user_id)

    # ── 5. Create escrow & publish task ──────────────────────────────────────
    task_id = await _run_in_thread(
        broker.publish_task,
        user_id=req.user_id,
        asin=f"dynamic-{req.skill_id}",
        developer_premium=req.developer_premium,
        max_budget=req.max_budget,
        skill_id=req.skill_id,
        compute_tier=req.compute_tier,
        payload=req.params,
        pipeline=req.pipeline,
    )
    if task_id is None:
        raise HTTPException(status_code=402, detail="Insufficient balance for escrow hold")

    return RunResponse(task_id=task_id)


@app.get("/api/tasks/{task_id}/status", response_model=TaskStatusResponse)
async def task_status(task_id: str):
    """Return the current status of a task (for polling after ``/api/run``)."""
    status = await _run_in_thread(broker.get_task_status, task_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    result = None
    outcome = None
    pot_sig = broker.get_pot_signature(task_id)
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
        pot=pot_sig,
    )
