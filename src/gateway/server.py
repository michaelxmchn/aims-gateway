"""Gateway Server — production-grade FastAPI task dispatcher for AIMS (Layer 5).

Provides HTTP endpoints for DePIN workers to claim and submit tasks,
with JSON Schema validation, tier-based gas billing, slashing, and
EIP-712 typed-data signature authentication.
"""

from __future__ import annotations

import asyncio
import collections
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from threading import Lock
from typing import Any, AsyncIterator

from eth_account import Account
from fastapi import FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from eth_account.messages import encode_defunct

from src.chain.nonce_manager import NonceManager
from src.chain.pot import POTManager
from src.gateway.canary import CanaryManager
from src.gateway.circuit_breaker import CircuitBreaker
from src.gateway.licensing import LicensingManager
from src.gateway.trial import FreeTrialManager, FreeTrialError
from src.gateway.broker import TaskBroker
from src.gateway.skill_store import SkillStore, SkillStoreError
from src.gateway.storage import Storage
from src.ledger.mock_counter import MockLedger
from src.skills.registry import SkillRegistry
from src.gateway.billing import BillingEngine, CommerceEngine, BillingMode, RevenuePhase, USDC_UNIT
from src.gateway.chain_listener import ChainListener
from src.gateway.ledger import TransactionLedger
from src.judge.judge_agent import JudgeEngine

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

CREDIT_SCORE_NS = "worker:credit"
"""Storage namespace for worker credit scores (0-100 integer)."""

DEVELOPER_INTEGRATION_NS = "developer:integration"
"""Storage namespace for one-click developer integration mappings."""

TASK_VAULT_NS = "task_vault"
"""Storage namespace for task-vault escrow addresses (扫码付款唯一托管钱包)."""

# ── Global instances (singleton per process) ──────────────────────────────

storage = Storage()
ledger = MockLedger(storage=storage)
broker = TaskBroker(ledger, storage=storage)
registry = SkillRegistry()
skill_store = SkillStore(storage=storage)

# Transaction history ledger — records deposits, withdraws, task deductions
tx_ledger = TransactionLedger(storage=storage)

# Load any previously uploaded skills into the registry
skill_store.load_into_registry(registry)

# Web3 billing singletons
nonce_manager = NonceManager(storage)
pot_manager = POTManager(storage, AIMS_GATEWAY_PRIVATE_KEY) if AIMS_GATEWAY_PRIVATE_KEY else None

# Canary watermark — anti-piracy ECDSA-signed token per task
_canary_manager = None
if AIMS_GATEWAY_PRIVATE_KEY:
    _canary_manager = CanaryManager(
        storage,
        AIMS_GATEWAY_PRIVATE_KEY,
        os.getenv("AIMS_GATEWAY_ADDRESS", ""),
    )

# AIMS 2.0 Licensing — single-use random seed key issuance
_licensing_manager = None
if AIMS_GATEWAY_PRIVATE_KEY:
    _licensing_manager = LicensingManager(storage, AIMS_GATEWAY_PRIVATE_KEY)

# Universal First-Task-Free trial enforcement
_trial_manager = FreeTrialManager(storage)

# Lazy-init contract via ChainSettlement (InMemory or Web3 based on env)
from src.chain.contract_client import Web3SettlementContract
from src.chain.settlement import ChainSettlement
_chain_settlement = ChainSettlement(os.getenv("AIMS_RPC_URL", ""))
_contract = _chain_settlement.contract  # InMemorySettlementContract or Web3SettlementContract

# In Web3 mode, on-chain deposit requires user's own signature.
# Maintain a local fallback dict so the proxy deposit endpoint never 500s.
_local_deposits: dict[str, int] = {}
_is_web3_mode = isinstance(_contract, Web3SettlementContract)

billing = BillingEngine(
    storage=storage,
    treasury_address=os.getenv("AIMS_TREASURY", "0xTreasury00000000000000000000000000000000001"),
    gateway_address=os.getenv("AIMS_GATEWAY_ADDRESS", ""),
    gateway_signing_key=AIMS_GATEWAY_PRIVATE_KEY,
    contract_client=_contract,
    pot_manager=pot_manager,
)

# ── SSE settlement broadcast (defined before CommerceEngine uses it) ─────

_settlement_buffer: collections.deque = collections.deque(maxlen=200)
"""Thread-safe ring buffer for settlement events — SSE consumers poll this."""

_settlement_buffer_lock: Lock = Lock()
"""Protects _settlement_buffer against concurrent threadpool writes."""


def broadcast_settlement(event: dict) -> None:
    """Thread-safe bridge: called from threadpool workers to enqueue a settlement event."""
    with _settlement_buffer_lock:
        _settlement_buffer.append(event)


# AIMS 2.0 Commerce Engine — multi-mode billing orchestration
commerce = CommerceEngine(
    storage=storage,
    trial_manager=_trial_manager,
    billing=billing,
    pot_manager=pot_manager,
    on_settlement=broadcast_settlement,
)

# ── AI Judge — scores task output 0-100, executes refund on fail ───────

_judge_engine = JudgeEngine(
    contract_client=_contract,
    gateway_private_key=AIMS_GATEWAY_PRIVATE_KEY,
    on_refund_alert=broadcast_settlement,
    model=os.getenv("LLM_MODEL_NAME", "deepseek-chat"),
)

# ── Circuit Breaker — 3-state fault isolation with SSE alerts ───────

_breaker = CircuitBreaker(
    storage=storage,
    on_state_change=lambda old, new: broadcast_settlement({
        "action": "circuit_breaker_transition",
        "from": old,
        "to": new,
        "ts": time.time(),
    }),
)

# ── Chain Listener — background poller for settlement events ──────────

AIMS_RPC_URL: str = os.getenv("AIMS_RPC_URL", "")
_chain_listener = ChainListener(
    contract_client=_contract,
    rpc_url=AIMS_RPC_URL,
    contract_address=AIMS_CONTRACT_ADDRESS,
    gateway_private_key=AIMS_GATEWAY_PRIVATE_KEY,
    on_settlement=broadcast_settlement,
    on_refund=broadcast_settlement,
    storage=storage,
)

# Worker heartbeat tracking: worker_id → last_seen_unix_ts
worker_heartbeats: dict[str, float] = {}
_heartbeat_lock = Lock()

# ── App lifespan (startup/shutdown) ──────────────────────────────────────


@asynccontextmanager
async def lifespan(app_instance: FastAPI) -> AsyncIterator[None]:
    """Start background services on startup, clean up on shutdown."""
    # Startup: start the chain event listener
    _chain_listener.start()
    yield
    # Shutdown: stop background threads
    _chain_listener.stop()


app = FastAPI(
    title="AIMS Gateway",
    version="1.0.0",
    description="AIMS DePIN Network — Task Dispatch & Settlement Gateway",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# ── CORS (allow frontend dev servers to connect) ────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Dev only — restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── SSE settlement broadcast ────────────────────────────────────────────────


@app.get("/api/v2/feed/stream")
async def settlement_feed_stream(request: Request):
    """SSE endpoint — streams real-time settlement events to connected clients.

    Polls ``_settlement_buffer`` every 2 seconds, yielding new events as
    ``data:`` frames.  Sends a ``: keepalive`` comment when idle to keep
    the connection alive.
    """
    async def event_generator():
        seen = 0
        while True:
            new_events = []
            with _settlement_buffer_lock:
                current = list(_settlement_buffer)
                if len(current) > seen:
                    new_events = current[seen:]
                    seen = len(current)
            for event in new_events:
                yield f"data: {json.dumps(event)}\n\n"
            if not new_events:
                yield ": keepalive\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

# ── Static frontend ─────────────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def index():
    """Serve the AIMS Gateway landing page."""
    with open("static/index.html", "r") as f:
        return HTMLResponse(content=f.read())


@app.get("/console")
async def console():
    """Serve the AIMS Web3 Console — wallet-connected dashboard."""
    with open("static/console.html", "r") as f:
        return HTMLResponse(content=f.read())


@app.get("/docs")
async def docs():
    """Serve the human-readable developer docs."""
    with open("static/docs.html", "r") as f:
        return HTMLResponse(content=f.read())

# ── EIP-191 personal_sign wallet verification middleware ────────────────────

EXEMPT_PATHS = {
    "/api/health",
    "/api/discovery",
    "/api/skills/upload",
    "/api/auth/pre-check",
    "/api/v2/feed/stream",
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

    # GET requests to public read endpoints are exempt from auth
    if request.method == "GET" and (
        path.startswith("/api/tasks/")
        or path.startswith("/api/skills/")
        or path.startswith("/api/wallet/balance")
        or path.startswith("/api/wallet/history")
        or path.startswith("/api/worker/credit-score")
        or path.startswith("/api/developer/")
        or path.startswith("/api/commerce/")
    ):
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


class PublishTaskRequest(BaseModel):
    """Extended run request with Task Market metadata (Consumer Publish Task UI)."""
    skill_id: str = Field(..., min_length=1, max_length=64)
    params: dict[str, Any] = Field(default_factory=dict)
    user_id: str = Field(..., min_length=1, max_length=128)
    developer_premium: float = Field(default=0.0, ge=0.0)
    max_budget: float = Field(default=2.0, ge=0.0)
    compute_tier: int = Field(default=1, ge=1, le=3)
    pipeline: list[str] | None = Field(default=None, description="Sequential skill IDs for task chaining. First element must match skill_id.")
    task_name: str = Field(default="", max_length=128, description="Human-readable task name for the Task Market")
    description: str = Field(default="", max_length=500, description="Free-text task description for the Task Market")
    is_custom: bool = Field(default=False, description="If True, only workers meeting credit_score_required can claim")
    credit_score_required: int = Field(default=0, ge=0, le=100, description="Minimum worker credit score (0-100) for custom tasks")


class ClaimSpecificRequest(BaseModel):
    task_id: str = Field(..., min_length=1, max_length=64)
    worker_id: str = Field(..., min_length=1, max_length=128)
    credit_score: int = Field(default=0, ge=0, le=100, description="Worker's credit score for custom-task validation")


class CreditScoreRequest(BaseModel):
    wallet: str = Field(..., min_length=1, max_length=128)
    score: int = Field(..., ge=0, le=100, description="Credit score 0-100")


class CreditScoreResponse(BaseModel):
    wallet: str
    score: int


class PendingTasksResponse(BaseModel):
    tasks: list[dict[str, Any]]
    count: int


class IntegrateRequest(BaseModel):
    skill_name_or_url: str = Field(..., min_length=1, max_length=512, description="Skill name or third-party API URL")
    wallet_address: str = Field(..., min_length=42, max_length=42, description="EVM wallet for revenue settlement")


class IntegrationStatusResponse(BaseModel):
    wallet: str
    skills: list[dict]
    count: int


class VaultStatusResponse(BaseModel):
    task_id: str
    vault_address: str
    balance: float = 0.0
    status: str


class PublishTaskResponse(BaseModel):
    task_id: str
    status: str = "PENDING"
    vault_address: str = ""
    vault_status: str = ""


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


class WithdrawRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128)
    amount: float = Field(..., gt=0.0, description="Amount to withdraw in USDC")


class WithdrawResponse(BaseModel):
    user_id: str
    amount: float
    new_balance: float
    tx_id: str


class FiatDepositRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128)
    amount: float = Field(..., gt=0.0, description="Fiat amount in USD")
    card_token: str | None = Field(default="mock_stripe_token", description="Stripe card token (mock)")


class FiatDepositResponse(BaseModel):
    user_id: str
    amount: float
    new_balance: float
    tx_id: str
    payment_method: str = "stripe_mock"


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
    """Legacy field — same as party_address. Kept for backwards compatibility."""
    party_address: str = ""
    signature: str


# ── Auth pre-check models ──────────────────────────────────────────────


class PreCheckRequest(BaseModel):
    message: str = Field(..., min_length=1, description="The signed message (format: AIMS_GATEWAY_AUTH:{wallet}:{skill_id})")
    signature: str = Field(..., min_length=1, description="EIP-191 personal_sign hex signature")


class PreCheckResponse(BaseModel):
    wallet: str
    verified: bool
    ts: float


# ── AIMS 2.0 Licensing models ────────────────────────────────────────────


class RegisterMetadataRequest(BaseModel):
    skill_id: str = Field(..., min_length=1, max_length=64)
    contributor_address: str = Field(
        ..., min_length=42, max_length=42,
        description="EVM wallet address (0x + 40 hex) of the contributor",
    )
    encrypted_source: str = Field(
        ..., min_length=1, max_length=2048,
        description="Encrypted download URL or IPFS CID for the skill source",
    )
    monetization: dict[str, Any] | None = Field(
        default=None,
        description="Optional monetization config: {function_type, billing_mode, rate_limit_per_day}",
    )


class RegisterMetadataResponse(BaseModel):
    status: str
    skill_id: str


class LicenseKeyRequest(BaseModel):
    task_id: str = Field(..., min_length=1, max_length=64)


class LicenseKeyResponse(BaseModel):
    task_id: str
    seed: str
    status: str


# ── AIMS 2.0 Commerce Matrix models ─────────────────────────────────────


class PurchaseSubscriptionRequest(BaseModel):
    skill_id: str = Field(..., min_length=1, max_length=64)


class PurchaseBuyoutRequest(BaseModel):
    skill_id: str = Field(..., min_length=1, max_length=64)


class PurchaseResponse(BaseModel):
    status: str
    amount_atomic: int = 0
    amount_usdc: float = 0.0
    expires_at: float | None = None
    error: str = ""


class SetPricingRequest(BaseModel):
    skill_id: str = Field(..., min_length=1, max_length=64)
    per_task_atomic: int | None = None
    subscription_monthly_atomic: int | None = None
    buyout_license_atomic: int | None = None


class SetRevenuePhaseRequest(BaseModel):
    phase: str = Field(..., pattern=r"^(q1|q2_q5)$")


class SeedPlgPoolRequest(BaseModel):
    amount_atomic: int = Field(..., gt=0)


class CommercePricingResponse(BaseModel):
    skill_id: str
    billing_mode: str
    per_task_atomic: int
    per_task_usdc: float
    subscription_monthly_atomic: int
    subscription_monthly_usdc: float
    buyout_license_atomic: int
    buyout_license_usdc: float


class PoolStatusResponse(BaseModel):
    subscription_pool_atomic: int
    subscription_pool_usdc: float
    buyout_pool_atomic: int
    buyout_pool_usdc: float
    plg_subsidy_pool_atomic: int
    plg_subsidy_pool_usdc: float
    revenue_phase: str


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


def _get_skill_billing_mode(skill_id: str) -> str:
    """Look up the billing mode from registered skill metadata.

    Returns ``"pay_per_task"`` as the default if no monetization info has
    been stored (backwards-compatible fallback).
    """
    meta_key = f"skill:metadata:{skill_id}"
    meta = storage.get(meta_key)
    if meta is None:
        return "pay_per_task"
    monetization = meta.get("monetization")
    if not isinstance(monetization, dict):
        return "pay_per_task"
    return monetization.get("billing_mode", "pay_per_task")


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

    if not _is_web3_mode:
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


class JudgeTestRequest(BaseModel):
    task_input: dict[str, Any] = Field(default_factory=dict)
    task_output: dict[str, Any] = Field(default_factory=dict)
    skill_id: str = Field(default="test_skill")


class JudgeTestResponse(BaseModel):
    score: int
    passed: bool
    reason: str
    latency_ms: float


@app.post("/api/admin/judge", response_model=JudgeTestResponse)
async def admin_judge(req: JudgeTestRequest):
    """Test the AI Judge engine with arbitrary input/output pairs."""
    verdict = _judge_engine.score(
        task_input=req.task_input,
        task_output=req.task_output,
        skill_id=req.skill_id,
    )
    return JudgeTestResponse(
        score=verdict.score,
        passed=verdict.passed,
        reason=verdict.reason,
        latency_ms=verdict.latency_ms,
    )


@app.get("/api/admin/listener")
async def admin_listener():
    """Return the chain listener status."""
    return _chain_listener.get_status()


@app.get("/api/admin/circuit-breaker")
async def admin_circuit_breaker():
    """Return the current circuit breaker state and thresholds."""
    return _breaker.status()


@app.post("/api/admin/emergency-pause")
async def admin_emergency_pause():
    """Emergency stop — forces circuit breaker to OPEN state.

    All subsequent ``/api/run`` calls will be rejected with 503.
    SSE red alert broadcast via ``broadcast_settlement``.

    To resume normal operation, call ``POST /api/admin/reset``.
    """
    state = _breaker.admin_force_open()
    logger.critical("🔴 EMERGENCY PAUSE — circuit forced to OPEN by admin")
    broadcast_settlement({
        "action": "emergency_pause",
        "state": state.value,
        "ts": time.time(),
    })
    return {"status": "paused", "state": state.value}


@app.post("/api/admin/reset")
async def admin_reset():
    """Admin-triggered full reset: any state → CLOSED, all counters cleared.

    Only effective after the OPEN cooldown window (120s by default) if the
    breaker is in OPEN state, or immediately from CLOSED/HALF_OPEN.
    """
    state = _breaker.admin_reset()
    logger.info("🔧 Admin reset — circuit breaker returned to CLOSED")
    broadcast_settlement({
        "action": "circuit_breaker_reset",
        "state": state.value,
        "ts": time.time(),
    })
    return {"status": "reset", "state": state.value}


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
                "agent_hint": m.agent_hint,
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
                "description": "Upload, inspect, execute, and register skills.",
                "operations": [
                    {"method": "POST", "path": "/api/skills/upload", "summary": "Upload skill zip.", "auth_required": False},
                    {"method": "POST", "path": "/api/skills/register-metadata", "summary": "Register lightweight routing metadata for a skill.", "auth_required": True},
                    {"method": "POST", "path": "/api/skills/register-developer", "summary": "Register developer wallet for 70% settlement.", "auth_required": True},
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
            {
                "category": "Licensing & Routing",
                "description": "AIMS 2.0 lightweight routing and dynamic key issuance.",
                "operations": [
                    {"method": "POST", "path": "/api/skills/register-metadata", "summary": "Register skill routing metadata.", "auth_required": True},
                    {"method": "POST", "path": "/api/licensing/request-key", "summary": "Request single-use license key for a task.", "auth_required": True},
                ],
            },
            {
                "category": "Task Market",
                "description": "Publish, browse, and claim tasks in the Task Market (抢单池).",
                "operations": [
                    {"method": "POST", "path": "/api/tasks/publish", "summary": "Publish a task to the Task Market (with escrow freeze).", "auth_required": True},
                    {"method": "GET", "path": "/api/tasks/pending", "summary": "List all PENDING tasks for the market.", "auth_required": False},
                    {"method": "POST", "path": "/api/tasks/claim-specific", "summary": "Claim a specific task by ID (with credit check).", "auth_required": True},
                ],
            },
            {
                "category": "Worker Credit",
                "description": "Credit score system for worker reputation (0-100).",
                "operations": [
                    {"method": "GET", "path": "/api/worker/credit-score/{wallet}", "summary": "Get a worker's credit score.", "auth_required": False},
                    {"method": "POST", "path": "/api/worker/credit-score", "summary": "Set a worker's credit score (admin).", "auth_required": True},
                ],
            },
            {
                "category": "Developer Integration",
                "description": "One-Click Integration for developers — map skills/URLs to wallets.",
                "operations": [
                    {"method": "POST", "path": "/api/developer/integrate", "summary": "One-click integrate skill or URL to wallet.", "auth_required": True},
                    {"method": "GET", "path": "/api/developer/integration/{wallet}", "summary": "Get integration status.", "auth_required": False},
                ],
            },
            {
                "category": "Task Vault (扫码付款)",
                "description": "Unique escrow vault per task — fiat/QR funded, AI Judge released.",
                "operations": [
                    {"method": "POST", "path": "/api/tasks/{id}/simulate-fiat-payment", "summary": "Simulate fiat → vault funding.", "auth_required": True},
                    {"method": "GET", "path": "/api/tasks/{id}/vault-status", "summary": "Poll vault funding & release status.", "auth_required": False},
                    {"method": "POST", "path": "/api/tasks/{id}/settle-from-vault", "summary": "Manually trigger vault settlement (admin).", "auth_required": True},
                ],
            },
        ],
        "links": {
            "developer_guide": {
                "url": f"{base_url}/developer-guide",
                "description": "AIMS Skill Developer Guide — build, publish, and monetize Skills",
            },
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

    # ── 3. Canary watermark verification (before schema, to strip stealth field) ─
    canary_piracy = False
    canary_reason = ""
    if _canary_manager is not None:
        canary_result = _canary_manager.verify_token(req.task_id, req.result_data)
        if not canary_result["valid"]:
            canary_piracy = True
            canary_reason = canary_result["reason"]

    # Strip _canary_token before schema validation (stealth watermark field)
    schema_input = (
        {k: v for k, v in req.result_data.items() if k != "_canary_token"}
        if "_canary_token" in req.result_data
        else req.result_data
    )

    # ── 4. JSON Schema validation ─────────────────────────────────────
    schema = (manifest.output_schema or {}) if manifest else {}
    if schema:
        valid = await _run_in_thread(
            broker.validate_result_generic, schema_input, schema, req.worker_id,
        )
    else:
        valid = isinstance(schema_input, dict)

    if not valid:
        await _run_in_thread(broker.complete_task, req.task_id, "FAILED")
        return SubmitResponse(
            task_id=req.task_id,
            worker_id=req.worker_id,
            outcome="REJECTED",
            error="Result failed JSON Schema validation",
        )

    # ── 4b. Canary gate — block settlement if piracy detected ─────────
    if canary_piracy:
        logger.warning(
            "CANARY_PIRACY_DETECTED: task=%s worker=%s reason=%s",
            req.task_id, req.worker_id, canary_reason,
        )
        _canary_manager.blacklist_worker(req.worker_id)
        await _run_in_thread(broker.complete_task, req.task_id, "FAILED")
        return SubmitResponse(
            task_id=req.task_id,
            worker_id=req.worker_id,
            outcome="FORBIDDEN_PIRACY",
            error=f"SKILL_PIRACY_DETECTED: {canary_reason}",
        )

    # ── 5. AI Judge gate — score output quality before settlement ────────
    judge_verdict = _judge_engine.score(
        task_input=task_meta.payload or {},
        task_output=schema_input,
        skill_id=skill_id,
        output_schema=schema,
    )
    if not judge_verdict.passed:
        logger.warning(
            "JUDGE_FAIL: task=%s worker=%s score=%d reason=%s",
            req.task_id, req.worker_id, judge_verdict.score, judge_verdict.reason,
        )
        # Record failure in circuit breaker (may trigger HALF_OPEN or OPEN)
        _breaker.record_failure(reason=f"Judge score {judge_verdict.score}/100")
        # Execute on-chain refund
        _judge_engine.refund_on_chain(
            task_id=req.task_id,
            user_address=task_meta.user_id,
            amount=BillingEngine.COST_PER_TASK_USDC,
            reason=f"AI Judge score {judge_verdict.score}/100: {judge_verdict.reason}",
        )
        await _run_in_thread(broker.complete_task, req.task_id, "FAILED")
        return SubmitResponse(
            task_id=req.task_id,
            worker_id=req.worker_id,
            outcome="REFUNDED",
            error=f"AI Judge score {judge_verdict.score}/100 — quality below threshold ({judge_verdict.reason})",
        )
    else:
        # Record success — resets consecutive failure counter, self-heals HALF_OPEN
        _breaker.record_success()

    # ── 6. Complete task (may re-queue for pipeline intermediate step) ─
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

    # ── 5b. Vault settlement (if task was vault-funded via 扫码付款) ─────
    vault_key = f"{TASK_VAULT_NS}:{req.task_id}"
    vault_data_raw = storage.dict_get(TASK_VAULT_NS, req.task_id)
    if vault_data_raw and vault_data_raw.get("status") == "funded":
        vault_result = _settle_vault(req.task_id)
        pot_sig = None
        if pot_manager:
            try:
                from eth_account.messages import encode_defunct
                pot_message = encode_defunct(primitive=f"AIMS_POT:{req.task_id}:{req.worker_id}".encode())
                pot_sig_obj = pot_manager.generate_pot(req.task_id, req.worker_id)
                if pot_sig_obj:
                    pot_sig = pot_sig_obj.signature if hasattr(pot_sig_obj, "signature") else str(pot_sig_obj)
                    await _run_in_thread(broker.set_pot_signature, req.task_id, pot_sig)
            except Exception:
                pass

        broadcast_settlement({
            "action": "vault_settle_complete",
            "task_id": req.task_id,
            "amounts": vault_result,
            "ts": time.time(),
        })

        return SubmitResponse(
            task_id=req.task_id,
            worker_id=req.worker_id,
            outcome="COMPLETED",
            total_cost=vault_result.get("balance", 0),
            developer_payout=vault_result.get("developer", 0),
            platform_tax=vault_result.get("treasury", 0),
            pot=pot_sig,
        )

    # ── 6. Final step — calculate execution time & settle escrow ──────
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

    # ── 6. Mode-aware settlement via Commerce Engine ──────────────────
    pot_sig: str | None = None
    locked_worker = claimed_worker
    billing_mode = _get_skill_billing_mode(skill_id)
    trial_count = _trial_manager.get_usage_count(task_meta.user_id, skill_id)
    is_free_trial = (trial_count == 1)

    settlement = await _run_in_thread(
        commerce.charge_and_settle,
        req.task_id,
        task_meta.user_id,
        locked_worker,
        skill_id,
        billing_mode=billing_mode,
        is_free_trial=is_free_trial,
    )
    if settlement.get("status") == "COMPLETED":
        pot = settlement.get("pot")
        if pot is not None:
            if hasattr(pot, "signature"):
                pot_sig = pot.signature
            elif isinstance(pot, dict):
                pot_sig = pot.get("signature", "")
            else:
                pot_sig = str(pot)
            await _run_in_thread(broker.set_pot_signature, req.task_id, pot_sig)

        # Track consumer spend for metered mode
        if billing_mode == BillingMode.PAY_PER_TASK and not is_free_trial:
            amount = settlement.get("amount", billing.COST_PER_TASK_USDC)
            await _run_in_thread(commerce.record_consumer_spend, task_meta.user_id, skill_id, amount)

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


# ── Task Market endpoints (Publish Task, Pending Tasks, Claim-Specific) ──


@app.get("/api/tasks/pending", response_model=PendingTasksResponse)
async def pending_tasks():
    """Return all PENDING tasks for the Task Market (抢单池).

    Workers browse this list in the Developer tab to find tasks to claim.
    Returns ``tasks`` (list) and ``count`` (int).
    """
    tasks = await _run_in_thread(broker.get_pending_tasks)
    return PendingTasksResponse(tasks=tasks, count=len(tasks))


@app.post("/api/tasks/claim-specific")
async def claim_specific_task(req: ClaimSpecificRequest, request: Request):
    """Claim a specific PENDING task by ID (with optional credit check).

    For ``is_custom`` tasks, validates that ``credit_score >=
    credit_score_required``.  Returns the task metadata on success, or
    **403** / **404** on failure.
    """
    task = await _run_in_thread(
        broker.claim_specific_task, req.task_id, req.worker_id, req.credit_score,
    )
    if task is None:
        # Check if the task even exists to differentiate 404 vs 403
        existing = await _run_in_thread(broker.get_task_meta, req.task_id)
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Task {req.task_id} not found")
        return Response(
            status_code=403,
            content=json.dumps({
                "detail": f"Task {req.task_id} requires credit_score >= {existing.credit_score_required}",
                "credit_score_required": existing.credit_score_required,
            }),
            media_type="application/json",
        )

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


# ── Worker Credit Score endpoints ─────────────────────────────────────────


@app.get("/api/worker/credit-score/{wallet}", response_model=CreditScoreResponse)
async def get_credit_score(wallet: str):
    """Return the credit score (0-100) for a worker wallet.

    Credit score reflects task completion quality and reliability.
    Custom tasks require ``credit_score >= credit_score_required``.
    Default score is **0** (new workers).
    """
    score = storage.dict_get(CREDIT_SCORE_NS, wallet) or 0
    return CreditScoreResponse(wallet=wallet, score=int(score))


@app.post("/api/worker/credit-score", response_model=CreditScoreResponse)
async def set_credit_score(req: CreditScoreRequest):
    """Set a worker's credit score (admin / AI Judge).

    Accepts ``wallet`` and ``score`` (0-100).  Overwrites any existing
    score for the wallet.
    """
    storage.dict_set(CREDIT_SCORE_NS, req.wallet, req.score)
    logger.info("Credit score set: wallet=%s score=%d", req.wallet, req.score)
    return CreditScoreResponse(wallet=req.wallet, score=req.score)


# ── One-Click Developer Integration ────────────────────────────────────────


@app.post("/api/developer/integrate")
async def developer_integrate(req: IntegrateRequest):
    """一键接入（One-Click Integration）— map skill/URL to wallet.

    Accepts a skill name or third-party API URL and binds it to the
    developer's wallet address.  When the skill is invoked, revenue is
    automatically routed to the bound wallet via 70/25/5 split.

    The system auto-detects whether the input is a URL (third-party API)
    or a known skill name and stores the mapping accordingly.
    """
    wallet = req.wallet_address.lower()
    existing_raw = storage.dict_get(DEVELOPER_INTEGRATION_NS, wallet) or {}
    existing_skills = existing_raw.get("skills", []) if isinstance(existing_raw, dict) else []

    # Detect URL vs skill name
    is_url = req.skill_name_or_url.startswith("http://") or req.skill_name_or_url.startswith("https://")
    entry = {
        "name": req.skill_name_or_url if not is_url else "",
        "url": req.skill_name_or_url if is_url else "",
        "mapped_at": time.time(),
        "type": "url_proxy" if is_url else "skill_map",
    }

    # Prevent duplicates
    for s in existing_skills:
        if (is_url and s.get("url") == req.skill_name_or_url) or (not is_url and s.get("name") == req.skill_name_or_url):
            return {"status": "exists", "wallet": wallet, "skill": req.skill_name_or_url}

    existing_skills.append(entry)
    integration_data = {
        "wallet": wallet,
        "skills": existing_skills,
        "updated_at": time.time(),
    }
    storage.dict_set(DEVELOPER_INTEGRATION_NS, wallet, integration_data)

    # If it's a known skill name, auto-register developer wallet for 70% split
    if not is_url:
        manifest = registry.get(req.skill_name_or_url)
        if manifest is not None:
            billing.register_developer(req.skill_name_or_url, wallet)
            logger.info("Developer auto-registered: skill=%s wallet=%s", req.skill_name_or_url, wallet)

    logger.info(
        "One-click integrate: wallet=%s input=%s type=%s",
        wallet, req.skill_name_or_url, entry["type"],
    )

    return {
        "status": "ok",
        "wallet": wallet,
        "skill": req.skill_name_or_url,
        "type": entry["type"],
        "skills_count": len(existing_skills),
    }


@app.get("/api/developer/integration/{wallet}", response_model=IntegrationStatusResponse)
async def developer_integration_status(wallet: str):
    """Return the one-click integration status for a developer wallet."""
    raw = storage.dict_get(DEVELOPER_INTEGRATION_NS, wallet.lower())
    if not raw or not isinstance(raw, dict):
        return IntegrationStatusResponse(wallet=wallet, skills=[], count=0)
    skills = raw.get("skills", [])
    return IntegrationStatusResponse(wallet=wallet, skills=skills, count=len(skills))


# ── Vault (扫码付款唯一托管钱包) endpoints ──────────────────────────────


import hashlib


def _generate_vault_address(task_id: str) -> str:
    """Generate a deterministic unique vault address from task_id.

    Format: ``0xV`` + SHA-256(task_id)[:39] → 42-char EVM address.
    The ``V`` prefix distinguishes vault addresses from user wallets.
    """
    digest = hashlib.sha256(f"aims:vault:{task_id}".encode()).hexdigest()
    return "0xV" + digest[:39]


def _settle_vault(task_id: str) -> dict:
    """Execute 70/25/5 vault settlement for a vault-funded task.

    Called after AI Judge passes.  Reads the vault balance, distributes
    to developer (70%), worker (25%), and treasury (5%), then marks
    the vault as RELEASED.

    Returns a dict with the split breakdown, or an error status.
    """
    vault_data = storage.dict_get(TASK_VAULT_NS, task_id)
    if vault_data is None:
        return {"status": "NO_VAULT"}
    if vault_data.get("status") != "funded":
        return {"status": "INVALID_STATE", "current": vault_data.get("status")}

    balance = vault_data.get("balance", 0.0)
    dev_share = round(balance * 0.70, 6)
    worker_share = round(balance * 0.25, 6)
    treasury_share = round(balance * 0.05, 6)

    vault_data["status"] = "released"
    vault_data["settled_at"] = time.time()
    vault_data["split"] = {
        "developer_70": dev_share,
        "worker_25": worker_share,
        "treasury_5": treasury_share,
    }
    storage.dict_set(TASK_VAULT_NS, task_id, vault_data)

    logger.info(
        "VAULT_SETTLE: task=%s balance=%.6f dev=%.6f worker=%.6f treasury=%.6f",
        task_id, balance, dev_share, worker_share, treasury_share,
    )

    broadcast_settlement({
        "action": "vault_settle",
        "task_id": task_id,
        "amounts": {
            "total": balance,
            "developer_70": dev_share,
            "worker_25": worker_share,
            "treasury_5": treasury_share,
        },
        "ts": time.time(),
    })

    return {
        "status": "RELEASED",
        "balance": balance,
        "developer": dev_share,
        "worker": worker_share,
        "treasury": treasury_share,
        "vault_address": vault_data.get("vault_address", ""),
    }


@app.post("/api/tasks/{task_id}/simulate-fiat-payment")
async def simulate_fiat_payment(task_id: str):
    """Simulate fiat payment → fund the task vault (扫码付款模拟).

    Marks the vault as FUNDED and deposits the task budget (in USDC)
    into the vault balance.  This simulates the flow:
      1. User scans QR code / pays via credit card
      2. Fiat bridge converts USD → USDC
      3. USDC deposited to unique task vault address
      4. Task becomes available in the market (escrow frozen)
    """
    vault_data = storage.dict_get(TASK_VAULT_NS, task_id)
    if vault_data is None:
        raise HTTPException(status_code=404, detail=f"No vault for task {task_id}")
    if vault_data.get("status") != "unfunded":
        raise HTTPException(
            status_code=409,
            detail=f"Vault for task {task_id} is in state '{vault_data.get('status')}', expected 'unfunded'",
        )

    budget = vault_data.get("budget", 2.0)
    vault_data["status"] = "funded"
    vault_data["balance"] = budget
    vault_data["fiat_paid"] = True
    vault_data["funded_at"] = time.time()
    vault_data["payment_method"] = "mock_stripe_qr"
    storage.dict_set(TASK_VAULT_NS, task_id, vault_data)

    logger.info(
        "VAULT_FUNDED: task=%s vault=%s amount=%.6f USDC (fiat simulation)",
        task_id, vault_data.get("vault_address", ""), budget,
    )

    broadcast_settlement({
        "action": "vault_funded",
        "task_id": task_id,
        "vault_address": vault_data.get("vault_address", ""),
        "amount": budget,
        "payment_method": "mock_stripe_qr",
        "ts": time.time(),
    })

    return {
        "status": "funded",
        "task_id": task_id,
        "vault_address": vault_data.get("vault_address", ""),
        "balance": budget,
        "message": f"✅ Vault funded with {budget:.2f} USDC — task is now available in the market",
    }


@app.get("/api/tasks/{task_id}/vault-status", response_model=VaultStatusResponse)
async def vault_status(task_id: str):
    """Poll the vault funding status for a task.

    Returns the vault address, current balance, and status
    (``unfunded`` | ``funded`` | ``released``).
    """
    vault_data = storage.dict_get(TASK_VAULT_NS, task_id)
    if vault_data is None:
        raise HTTPException(status_code=404, detail=f"No vault for task {task_id}")
    return VaultStatusResponse(
        task_id=task_id,
        vault_address=vault_data.get("vault_address", ""),
        balance=vault_data.get("balance", 0.0),
        status=vault_data.get("status", "unknown"),
    )


@app.post("/api/tasks/{task_id}/settle-from-vault")
async def settle_from_vault_endpoint(task_id: str):
    """Manually trigger vault settlement for a funded task.

    Used for testing / admin.  In production, vault settlement is
    automatically triggered by the AI Judge after task submission.
    Executes the 70/25/5 split from the vault balance.
    """
    vault_data = storage.dict_get(TASK_VAULT_NS, task_id)
    if vault_data is None:
        raise HTTPException(status_code=404, detail=f"No vault for task {task_id}")
    if vault_data.get("status") != "funded":
        raise HTTPException(
            status_code=409,
            detail=f"Vault for task {task_id} is in state '{vault_data.get('status')}', expected 'funded'",
        )
    result = _settle_vault(task_id)
    return result


# ── Publish Task endpoint (Consumer Publish Task UI) ──────────────────────


@app.post("/api/tasks/publish", response_model=PublishTaskResponse)
async def publish_task(req: PublishTaskRequest):
    """Publish a task to the Task Market (Consumer Publish Task UI).

    Accepts the same fields as ``/api/run`` plus Task Market metadata
    (``task_name``, ``description``, ``is_custom``, ``credit_score_required``).
    Creates an escrow hold, registers a PENDING broker task, and generates
    a unique task-vault address for fiat/QR escrow funding (扫码付款唯一托管钱包).

    The vault is created in ``unfunded`` state.  Call
    ``POST /api/tasks/{id}/simulate-fiat-payment`` to fund it.
    """
    # ── 0. Circuit breaker gate ─────────────────────────────────────
    if not _breaker.can_pass(f"publish:{req.skill_id}"):
        raise HTTPException(
            status_code=503,
            detail="Gateway is OPEN — accepting no new tasks. Try again later.",
        )

    # ── 1. Look up manifest ─────────────────────────────────────────
    manifest = registry.get(req.skill_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"Skill '{req.skill_id}' not found")

    # ── 2. Validate required params ─────────────────────────────────
    schema = manifest.input_schema or {}
    required = schema.get("required", [])
    for field in required:
        if field not in req.params:
            raise HTTPException(
                status_code=400,
                detail=f"Missing required parameter: {field}",
            )

    # ── 3. Trial enforcement ────────────────────────────────────────
    billing_mode = _get_skill_billing_mode(req.skill_id)
    try:
        _trial_manager.enforce(
            wallet=req.user_id,
            skill_id=req.skill_id,
            billing_mode=billing_mode,
        )
    except FreeTrialError as exc:
        raise HTTPException(status_code=402, detail=str(exc))

    # ── 4. Balance check (skip for free trial) ──────────────────────
    trial_count = _trial_manager.get_usage_count(req.user_id, req.skill_id)
    on_free_trial = (trial_count == 1)

    if not on_free_trial:
        local_bal = _local_deposits.get(req.user_id, 0) if _is_web3_mode else 0
        credit_balance = await _run_in_thread(
            billing.check_user_balance, req.user_id, local_bal,
        )
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

    # ── 5. Budget control ───────────────────────────────────────────
    num_steps = len(req.pipeline) if req.pipeline else 1
    min_cost_atomic = BillingEngine.COST_PER_TASK_USDC * num_steps
    max_budget_atomic = int(round(req.max_budget * 10**6))
    if max_budget_atomic < min_cost_atomic:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Insufficient budget. Minimum: "
                f"{min_cost_atomic / 10**6:.6f} USDC for {num_steps} step(s), "
                f"provided: {req.max_budget:.6f} USDC"
            ),
        )

    # ── 6. Auto-seed MockLedger if new wallet ───────────────────────
    usdt_balance = await _run_in_thread(ledger.get_user_usdt, req.user_id)
    if usdt_balance < 1.0:
        await _run_in_thread(ledger.seed_usdt, req.user_id, 50.0)

    # ── 7. Publish task with market metadata ────────────────────────
    task_id = await _run_in_thread(
        broker.publish_task,
        user_id=req.user_id,
        asin=f"market-{req.skill_id}",
        developer_premium=req.developer_premium,
        max_budget=req.max_budget,
        skill_id=req.skill_id,
        compute_tier=req.compute_tier,
        payload=req.params,
        pipeline=req.pipeline,
        task_name=req.task_name,
        description=req.description,
        is_custom=req.is_custom,
        credit_score_required=req.credit_score_required,
    )
    if task_id is None:
        raise HTTPException(status_code=402, detail="Insufficient balance for escrow hold")

    # ── 8. Generate unique task-vault address (扫码付款唯一托管钱包) ──
    vault_address = _generate_vault_address(task_id)
    vault_data = {
        "task_id": task_id,
        "vault_address": vault_address,
        "balance": 0.0,
        "status": "unfunded",
        "budget": req.max_budget,
        "fiat_paid": False,
        "created_at": time.time(),
        "user_id": req.user_id,
        "skill_id": req.skill_id,
    }
    storage.dict_set(TASK_VAULT_NS, task_id, vault_data)

    logger.info(
        "VAULT_CREATED: task=%s vault=%s budget=%.2f (unfunded)",
        task_id, vault_address, req.max_budget,
    )

    return PublishTaskResponse(
        task_id=task_id,
        vault_address=vault_address,
        vault_status="unfunded",
    )


# ── Developer Guide route ─────────────────────────────────────────────────


@app.get("/developer-guide", response_class=HTMLResponse)
async def developer_guide():
    """Serve the AIMS_SKILL_GUIDE.md as HTML for external developers."""
    guide_path = os.path.join(os.path.dirname(__file__), "..", "..", "AIMS_SKILL_GUIDE.md")
    try:
        with open(guide_path, "r") as f:
            md_content = f.read()
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Guide not found</h1><p>Please generate AIMS_SKILL_GUIDE.md</p>", status_code=404)

    # Simple markdown→HTML conversion (enough for a developer doc)
    html_body = _render_markdown_as_html(md_content)

    return HTMLResponse(content=f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AIMS Skill Developer Guide</title>
<style>
  body{{font-family:'SF Mono',monospace;background:#0f172a;color:#cbd5e1;line-height:1.7;padding:2rem;max-width:960px;margin:0 auto}}
  h1{{color:#deff9a;font-size:2rem;border-bottom:1px solid rgba(222,255,154,0.2);padding-bottom:.5rem}}
  h2{{color:#a78bfa;margin-top:2rem}}
  h3{{color:#60a5fa}}
  code{{background:rgba(222,255,154,0.08);padding:.1rem .3rem;border-radius:3px;font-size:.85em;color:#deff9a}}
  pre{{background:#0a0f1a;padding:1rem;border-radius:6px;overflow-x:auto;border:1px solid rgba(222,255,154,0.08)}}
  pre code{{background:transparent;padding:0}}
  a{{color:#60a5fa}}
  table{{border-collapse:collapse;width:100%;margin:1rem 0}}
  th,td{{border:1px solid rgba(222,255,154,0.15);padding:.5rem;text-align:left;font-size:.85rem}}
  th{{background:rgba(222,255,154,0.06);color:#deff9a}}
  hr{{border:none;border-top:1px solid rgba(222,255,154,0.1);margin:2rem 0}}
</style>
</head>
<body>
{html_body}
</body>
</html>""")


def _render_markdown_as_html(md: str) -> str:
    """Basic markdown→HTML renderer for the developer guide."""
    import re
    lines = md.split("\n")
    html_parts: list[str] = []
    in_code_block = False
    code_buffer: list[str] = []
    in_table = False

    for line in lines:
        # Code block
        if line.startswith("```"):
            if in_code_block:
                html_parts.append(f"<pre><code>{''.join(code_buffer)}</code></pre>")
                code_buffer = []
                in_code_block = False
            else:
                in_code_block = True
            continue
        if in_code_block:
            code_buffer.append(line.replace("<", "&lt;").replace(">", "&gt;") + "\n")
            continue

        # Headers
        if line.startswith("### "):
            html_parts.append(f"<h3>{line[4:]}</h3>")
        elif line.startswith("## "):
            html_parts.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("# "):
            html_parts.append(f"<h1>{line[2:]}</h1>")
        # Horizontal rule
        elif re.match(r"^---+\s*$", line) or re.match(r"^\*\*\*+\s*$", line):
            html_parts.append("<hr>")
        # Table row
        elif "|" in line and line.strip().startswith("|"):
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if in_table:
                if re.match(r"^[\s|:,\-]+$", line):
                    continue
                html_parts.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
            else:
                in_table = True
                html_parts.append("<table><thead><tr>" + "".join(f"<th>{c}</th>" for c in cells) + "</tr></thead><tbody>")
        else:
            if in_table and line.strip() == "":
                in_table = False
                html_parts.append("</tbody></table>")
            # Inline formatting
            line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
            line = re.sub(r"`(.+?)`", r"<code>\1</code>", line)
            line = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', line)
            if line.strip() == "":
                html_parts.append("<br>")
            elif line.strip().startswith("- "):
                html_parts.append(f"<li>{line.strip()[2:]}</li>")
            elif line.strip().startswith("1. "):
                html_parts.append(f"<li>{line.strip()[3:]}</li>")
            else:
                html_parts.append(f"<p>{line}</p>")

    if in_code_block:
        html_parts.append(f"<pre><code>{''.join(code_buffer)}</code></pre>")
    if in_table:
        html_parts.append("</tbody></table>")

    return "\n".join(html_parts)


# ── Wallet endpoints (proxy to on-chain contract) ─────────────────────────


@app.post("/api/wallet/deposit", response_model=DepositResponse)
async def wallet_deposit(req: DepositRequest):
    """Deposit credits into a user's on-chain wallet.

    In production: the user deposits directly into the contract.
    This endpoint proxies the deposit for convenience and testing.
    In Web3 mode, maintains a local in-memory balance fallback so the
    endpoint never 500s — the gateway cannot sign on behalf of arbitrary
    users for on-chain deposits.
    """
    # Convert float USDC to atomic units (6 decimals)
    amount_atomic = int(round(req.amount * 10**6))

    if _is_web3_mode:
        # On-chain deposit requires user's own signature — use local fallback
        _local_deposits[req.user_id] = _local_deposits.get(req.user_id, 0) + amount_atomic
        onchain = _contract.get_user_balance(req.user_id)
        new_balance = onchain + _local_deposits[req.user_id]
        logger.info(
            "Proxy deposit %s +%.6f USDC (local fallback, Web3 mode)",
            req.user_id, req.amount,
        )
    else:
        _contract.deposit(req.user_id, amount_atomic)
        new_balance = _contract.get_user_balance(req.user_id)

    # Record deposit in transaction history ledger
    tx_ledger.record(
        txn_type="deposit",
        user_id=req.user_id,
        amount=req.amount,
        description=f"Wallet deposit of {req.amount:.2f} USDC",
    )

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
    In Web3 mode, includes any proxy-deposited local balance.
    """
    balance_atomic = _contract.get_user_balance(user_id)
    if _is_web3_mode:
        balance_atomic += _local_deposits.get(user_id, 0)
    credits = float(balance_atomic) / 10**6

    return BalanceResponse(user_id=user_id, credits=credits)


@app.post("/api/wallet/withdraw", response_model=WithdrawResponse)
async def wallet_withdraw(req: WithdrawRequest):
    """Withdraw USDC from the user's gateway balance back to their wallet.

    Deducts from the internal balance (or local fallback in Web3 mode)
    and records the transaction in the user history ledger.
    """
    # Check available balance
    balance_atomic = _contract.get_user_balance(req.user_id)
    if _is_web3_mode:
        balance_atomic += _local_deposits.get(req.user_id, 0)

    amount_atomic = int(round(req.amount * 10**6))
    if balance_atomic < amount_atomic:
        raise HTTPException(
            status_code=402,
            detail=f"Insufficient balance. Available: {balance_atomic / 10**6:.6f} USDC, requested: {req.amount:.6f}",
        )

    # Deduct from balance
    if _is_web3_mode:
        current_local = _local_deposits.get(req.user_id, 0)
        if current_local >= amount_atomic:
            _local_deposits[req.user_id] = current_local - amount_atomic
        else:
            # Deduct from on-chain balance via local fallback
            _local_deposits[req.user_id] = 0
    else:
        _contract.withdraw(req.user_id, amount_atomic)

    # Recalculate new balance
    new_balance_atomic = _contract.get_user_balance(req.user_id)
    if _is_web3_mode:
        new_balance_atomic += _local_deposits.get(req.user_id, 0)

    # Record in transaction ledger
    tx_id = tx_ledger.record(
        txn_type="withdraw",
        user_id=req.user_id,
        amount=req.amount,
        description=f"Withdrawal of {req.amount:.2f} USDC to wallet {req.user_id[:10]}...",
    )

    logger.info("Withdraw: user=%s amount=%.6f tx=%s", req.user_id, req.amount, tx_id)

    return WithdrawResponse(
        user_id=req.user_id,
        amount=req.amount,
        new_balance=float(new_balance_atomic) / 10**6,
        tx_id=tx_id,
    )


@app.post("/api/wallet/fiat-deposit", response_model=FiatDepositResponse)
async def wallet_fiat_deposit(req: FiatDepositRequest):
    """Mock fiat/Stripe credit card deposit bridge.

    Simulates a Stripe payment confirmation, then auto-deposits the
    equivalent USDC into the user's gateway balance and records the
    transaction in the user history ledger.
    """
    # ── 1. Mock Stripe charge (always succeeds in dev/test) ────────────
    logger.info(
        "Fiat deposit (mock): user=%s amount=%.2f card_token=%s",
        req.user_id, req.amount, req.card_token,
    )

    # ── 2. Convert fiat USD → USDC and deposit ─────────────────────────
    amount_atomic = int(round(req.amount * 10**6))

    if _is_web3_mode:
        _local_deposits[req.user_id] = _local_deposits.get(req.user_id, 0) + amount_atomic
    else:
        _contract.deposit(req.user_id, amount_atomic)

    new_balance_atomic = _contract.get_user_balance(req.user_id)
    if _is_web3_mode:
        new_balance_atomic += _local_deposits.get(req.user_id, 0)

    # ── 3. Record in transaction ledger ───────────────────────────────
    tx_id = tx_ledger.record(
        txn_type="deposit",
        user_id=req.user_id,
        amount=req.amount,
        description=f"Fiat/Stripe deposit of ${req.amount:.2f} (mock card {req.card_token[:12]}...)",
        metadata={"method": "stripe_mock", "card_token": req.card_token},
    )

    logger.info("Fiat deposit complete: user=%s amount=%.2f tx=%s", req.user_id, req.amount, tx_id)

    return FiatDepositResponse(
        user_id=req.user_id,
        amount=req.amount,
        new_balance=float(new_balance_atomic) / 10**6,
        tx_id=tx_id,
    )


@app.get("/api/wallet/history")
async def wallet_history(user_id: str, limit: int = 50):
    """Return the personal transaction history for a wallet.

    Includes deposits, withdrawals, and task billing entries.
    Query parameters: ``?user_id=<evm_address>&limit=N``.
    """
    if not user_id:
        raise HTTPException(status_code=400, detail="Missing required query parameter: user_id")
    entries = tx_ledger.get_user_history(user_id, limit=limit)
    return {
        "user_id": user_id,
        "entries": entries,
        "count": len(entries),
    }


@app.get("/api/admin/audit")
async def audit_trail(task_id: str | None = None, limit: int = 100):
    """Query the reversible settlement audit trail.

    Optional ``?task_id=<task_id>`` filters to one task.
    ``?limit=N`` controls max entries (default 100).
    """
    return {
        "entries": billing.get_audit_trail(task_id=task_id, limit=limit),
        "summary": billing.get_audit_summary(),
    }


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
async def task_pot(task_id: str, request: Request):
    """Retrieve the Proof-of-Task for a completed task.

    The worker fetches this after task completion and presents the
    signature to ``claimReward()`` on the settlement contract.

    Supports querying both worker PoT (default) and developer PoT
    via the optional ``?party=`` query parameter.
    """
    party = request.query_params.get("party", "")
    pot = pot_manager.get_pot(task_id, party_address=party) if pot_manager else None
    # Fallback: if no party given, try the task's worker address
    if pot is None and not party:
        try:
            status = broker.get_task_status(task_id)
            worker_id = status.get("worker_id") if status else None
            if worker_id:
                pot = pot_manager.get_pot(task_id, party_address=worker_id)
        except Exception:
            pass
    if pot is None:
        raise HTTPException(status_code=404, detail=f"No PoT found for task {task_id}")

    return PotResponse(
        task_id=pot.task_id,
        worker_address=pot.party_address,
        party_address=pot.party_address,
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


class RegisterDeveloperRequest(BaseModel):
    skill_id: str = Field(..., min_length=1, max_length=64)
    developer_address: str = Field(
        ..., min_length=42, max_length=42,
        description="EVM wallet address (0x + 40 hex)",
    )


@app.post("/api/skills/register-developer", response_model=dict)
async def register_developer(req: RegisterDeveloperRequest):
    """Register a developer wallet address for a skill.

    The registered address receives **70%** of task settlement (via
    ``claimDeveloperReward``).  Can only be called by the gateway admin.
    """
    manifest = registry.get(req.skill_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"Skill '{req.skill_id}' not found")
    billing.register_developer(req.skill_id, req.developer_address)
    return {
        "status": "ok",
        "skill_id": req.skill_id,
        "developer_address": req.developer_address,
    }


@app.post("/api/skills/register-metadata", response_model=RegisterMetadataResponse)
async def register_skill_metadata(req: RegisterMetadataRequest):
    """Register lightweight routing metadata for a skill.

    Records the skill_id, contributor wallet address, and encrypted
    download source.  Storage is limited to a few KB per entry.
    """
    ns = "skill:metadata"
    meta_key = f"{ns}:{req.skill_id}"
    existing = storage.get(meta_key)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Metadata for skill '{req.skill_id}' already registered",
        )
    meta = {
        "skill_id": req.skill_id,
        "contributor_address": req.contributor_address,
        "encrypted_source": req.encrypted_source,
        "ts": time.time(),
    }
    if req.monetization:
        meta["monetization"] = req.monetization
    storage.set(meta_key, meta)
    logger.info(
        "Metadata registered: skill=%s contributor=%s billing_mode=%s",
        req.skill_id, req.contributor_address,
        (req.monetization or {}).get("billing_mode", "unknown"),
    )
    return RegisterMetadataResponse(status="ok", skill_id=req.skill_id)


@app.post("/api/licensing/request-key", response_model=LicenseKeyResponse)
async def request_license_key(req: LicenseKeyRequest, request: Request):
    """Request a single-use random seed key for a task.

    **Three mandatory checks before issuance:**

    1. **Task state** — Task must be in CLAIMED or SUCCESS state (locked escrow).
    2. **Wallet ownership** — ``X-Wallet-Address`` must match the task's
       ``user_id`` (EIP-191 signature already verified by middleware).
    3. **Replay guard** — Each ``Task_ID`` can only receive one key.

    On success, returns the derived random seed and marks the task as
    ``ACTIVATED_ONCE``.
    """
    if _licensing_manager is None:
        raise HTTPException(status_code=503, detail="Licensing manager not available (no gateway key configured)")

    wallet_address = (
        request.headers.get("X-Wallet-Address")
        or request.headers.get("X-User-ID")
        or ""
    )

    # ── 1. Task state validation ────────────────────────────────────────
    status = await _run_in_thread(broker.get_task_status, req.task_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Task {req.task_id} not found")

    task_state = status.get("status", "")
    if task_state not in ("CLAIMED", "SUCCESS"):
        raise HTTPException(
            status_code=400,
            detail=f"Task {req.task_id} is in state '{task_state}', expected CLAIMED or SUCCESS",
        )

    # ── 2. Wallet ownership validation ──────────────────────────────────
    task_meta = await _run_in_thread(broker.get_task_meta, req.task_id)
    if task_meta is None:
        raise HTTPException(status_code=404, detail=f"Metadata for {req.task_id} not found")

    if wallet_address.lower() != task_meta.user_id.lower():
        raise HTTPException(
            status_code=403,
            detail=(
                f"Wallet {wallet_address} does not match task owner "
                f"{task_meta.user_id}"
            ),
        )

    # ── 3. Replay guard — single-use per Task_ID ────────────────────────
    if _licensing_manager.is_license_issued(req.task_id):
        current_status = _licensing_manager.get_license_status(req.task_id)
        raise HTTPException(
            status_code=409,
            detail=f"License already issued for task {req.task_id} (status={current_status})",
        )

    # ── 4. Issue key ────────────────────────────────────────────────────
    record = _licensing_manager.issue_key(req.task_id, wallet_address)
    logger.info(
        "License key issued: task=%s user=%s status=%s",
        req.task_id, wallet_address, record["status"],
    )
    return LicenseKeyResponse(
        task_id=req.task_id,
        seed=record["seed"],
        status=record["status"],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# AIMS 2.0 Commerce Matrix Endpoints
# ═══════════════════════════════════════════════════════════════════════════════


@app.post("/api/commerce/subscription", response_model=PurchaseResponse)
async def purchase_subscription(req: PurchaseSubscriptionRequest, request: Request):
    """Purchase a monthly subscription pass for a skill.

    Deducts the subscription price from the consumer's on-chain balance
    and activates a 30-day pass.  Subsequent invocations within the
    subscription period draw from the subscription pool rather than the
    consumer's individual balance.
    """
    wallet_address = (
        request.headers.get("X-Wallet-Address")
        or request.headers.get("X-User-ID")
        or ""
    )
    if not wallet_address:
        raise HTTPException(status_code=403, detail="Missing wallet address header")

    result = await _run_in_thread(
        commerce.purchase_subscription, wallet_address, req.skill_id, _contract,
    )
    if result["status"] == "FAILED":
        raise HTTPException(status_code=402, detail=result["error"])

    return PurchaseResponse(
        status=result["status"],
        amount_atomic=result["amount_atomic"],
        amount_usdc=result["amount_atomic"] / USDC_UNIT,
        expires_at=result.get("expires_at"),
    )


@app.post("/api/commerce/buyout", response_model=PurchaseResponse)
async def purchase_buyout(req: PurchaseBuyoutRequest, request: Request):
    """Purchase a perpetual buyout license for a skill.

    One-time USDC payment grants unlimited lifetime access to the skill.
    Subsequent invocations draw from the buyout pool (only worker bandwidth
    and platform tax apply).
    """
    wallet_address = (
        request.headers.get("X-Wallet-Address")
        or request.headers.get("X-User-ID")
        or ""
    )
    if not wallet_address:
        raise HTTPException(status_code=403, detail="Missing wallet address header")

    result = await _run_in_thread(
        commerce.purchase_buyout, wallet_address, req.skill_id, _contract,
    )
    if result["status"] == "FAILED":
        raise HTTPException(status_code=402, detail=result["error"])

    return PurchaseResponse(
        status=result["status"],
        amount_atomic=result["amount_atomic"],
        amount_usdc=result["amount_atomic"] / USDC_UNIT,
    )


@app.get("/api/commerce/pricing/{skill_id}", response_model=CommercePricingResponse)
async def skill_pricing(skill_id: str):
    """Return pricing for all three billing modes for a skill."""
    pricing = commerce.get_skill_pricing(skill_id)
    billing_mode = _get_skill_billing_mode(skill_id)
    return CommercePricingResponse(
        skill_id=skill_id,
        billing_mode=billing_mode,
        per_task_atomic=pricing["per_task_atomic"],
        per_task_usdc=pricing["per_task_atomic"] / USDC_UNIT,
        subscription_monthly_atomic=pricing["subscription_monthly_atomic"],
        subscription_monthly_usdc=pricing["subscription_monthly_atomic"] / USDC_UNIT,
        buyout_license_atomic=pricing["buyout_license_atomic"],
        buyout_license_usdc=pricing["buyout_license_atomic"] / USDC_UNIT,
    )


@app.get("/api/commerce/pools", response_model=PoolStatusResponse)
async def pool_status():
    """Return current pool balances for subscription, buyout, and PLG subsidy."""
    phase = commerce.get_revenue_phase().value
    return PoolStatusResponse(
        subscription_pool_atomic=commerce._subscription_pool(),
        subscription_pool_usdc=commerce._subscription_pool() / USDC_UNIT,
        buyout_pool_atomic=commerce._buyout_pool(),
        buyout_pool_usdc=commerce._buyout_pool() / USDC_UNIT,
        plg_subsidy_pool_atomic=commerce._plg_pool(),
        plg_subsidy_pool_usdc=commerce._plg_pool() / USDC_UNIT,
        revenue_phase=phase,
    )


@app.get("/api/commerce/phase")
async def revenue_phase():
    """Return the current revenue split phase (q1 = 70/25/5, q2_q5 = 95/0/5)."""
    phase = commerce.get_revenue_phase()
    dev_bps, worker_bps, treasury_bps = commerce._split_bps()
    return {
        "phase": phase.value,
        "developer_pct": dev_bps / 100,
        "worker_pct": worker_bps / 100,
        "treasury_pct": treasury_bps / 100,
    }


@app.post("/api/commerce/phase")
async def set_revenue_phase(req: SetRevenuePhaseRequest):
    """Switch revenue split phase (admin)."""
    commerce.set_revenue_phase(req.phase)
    dev_bps, worker_bps, treasury_bps = commerce._split_bps()
    logger.info("Revenue phase set to %s", req.phase)
    return {
        "status": "ok",
        "phase": req.phase,
        "developer_pct": dev_bps / 100,
        "worker_pct": worker_bps / 100,
        "treasury_pct": treasury_bps / 100,
    }


@app.post("/api/commerce/pricing", response_model=CommercePricingResponse)
async def set_skill_pricing(req: SetPricingRequest):
    """Set custom pricing for a skill (admin)."""
    commerce.set_skill_pricing(
        req.skill_id,
        per_task_atomic=req.per_task_atomic,
        subscription_monthly_atomic=req.subscription_monthly_atomic,
        buyout_license_atomic=req.buyout_license_atomic,
    )
    pricing = commerce.get_skill_pricing(req.skill_id)
    billing_mode = _get_skill_billing_mode(req.skill_id)
    return CommercePricingResponse(
        skill_id=req.skill_id,
        billing_mode=billing_mode,
        per_task_atomic=pricing["per_task_atomic"],
        per_task_usdc=pricing["per_task_atomic"] / USDC_UNIT,
        subscription_monthly_atomic=pricing["subscription_monthly_atomic"],
        subscription_monthly_usdc=pricing["subscription_monthly_atomic"] / USDC_UNIT,
        buyout_license_atomic=pricing["buyout_license_atomic"],
        buyout_license_usdc=pricing["buyout_license_atomic"] / USDC_UNIT,
    )


@app.post("/api/commerce/seed-plg", response_model=dict)
async def seed_plg_pool(req: SeedPlgPoolRequest):
    """Seed the PLG subsidy pool from treasury (admin)."""
    new_balance = commerce.seed_plg_pool(req.amount_atomic)
    return {
        "status": "ok",
        "added_atomic": req.amount_atomic,
        "added_usdc": req.amount_atomic / USDC_UNIT,
        "new_pool_balance_atomic": new_balance,
        "new_pool_balance_usdc": new_balance / USDC_UNIT,
    }


@app.get("/api/commerce/spend/{wallet}/{skill_id}")
async def consumer_spend(wallet: str, skill_id: str):
    """Return cumulative consumer spend for (wallet, skill_id)."""
    total_atomic = commerce.get_consumer_spend(wallet, skill_id)
    return {
        "wallet": wallet,
        "skill_id": skill_id,
        "total_spent_atomic": total_atomic,
        "total_spent_usdc": total_atomic / USDC_UNIT,
    }
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
    # ── 0. Circuit breaker gate − reject if OPEN ────────────────────────
    if not _breaker.can_pass(f"run_skill:{req.skill_id}"):
        raise HTTPException(
            status_code=503,
            detail="Gateway is in OPEN state — accepting no new tasks. "
                   "Try again later or contact admin.",
        )

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

    # ── 3. Universal First-Task-Free trial enforcement (before balance) ──
    billing_mode = _get_skill_billing_mode(req.skill_id)
    try:
        _trial_manager.enforce(
            wallet=req.user_id,
            skill_id=req.skill_id,
            billing_mode=billing_mode,
        )
    except FreeTrialError as exc:
        raise HTTPException(status_code=402, detail=str(exc))

    # ── 4. Check on-chain balance (skip for first free trial) ───────────
    trial_count = _trial_manager.get_usage_count(req.user_id, req.skill_id)
    on_free_trial = (trial_count == 1)  # just consumed the trial above

    if not on_free_trial:
        local_bal = _local_deposits.get(req.user_id, 0) if _is_web3_mode else 0
        credit_balance = await _run_in_thread(
            billing.check_user_balance, req.user_id, local_bal,
        )
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
    else:
        logger.info(
            "Free trial granted: wallet=%s skill=%s (1st call, billing_mode=%s)",
            req.user_id, req.skill_id, billing_mode,
        )

    # ── 5. Budget control: max_fee vs minimum pipeline cost ────────────
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

    # ── 6. Auto-seed MockLedger if new wallet (dev/test mode) ────────────────
    usdt_balance = await _run_in_thread(ledger.get_user_usdt, req.user_id)
    if usdt_balance < 1.0:
        await _run_in_thread(ledger.seed_usdt, req.user_id, 50.0)
        logger.info("Auto-seeded MockLedger %s with 50.0 USDT (dev mode)", req.user_id)

    # ── 7. Inject canary watermark into task params ──────────────────────────
    if _canary_manager is not None:
        _canary_token = _canary_manager.generate_token()
        req.params["_canary_token"] = _canary_token

    # ── 8. Create escrow & publish task ──────────────────────────────────────
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

    # Record canary token against the published task_id
    if task_id and _canary_manager is not None:
        _canary_manager.record_task(task_id, _canary_token)

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


# ── Auth pre-check endpoint ──────────────────────────────────────────


@app.post("/api/auth/pre-check", response_model=PreCheckResponse)
async def auth_precheck(req: PreCheckRequest):
    """Verify an AIMS_GATEWAY_AUTH beacon signature.

    The frontend signs ``AIMS_GATEWAY_AUTH:{wallet}:{skill_id}`` with
    MetaMask.  This endpoint recovers the signer and confirms ownership
    before the task execution flow begins.
    """
    try:
        signable = encode_defunct(primitive=req.message.encode())
        recovered = Account.recover_message(signable, signature=req.signature)
    except Exception as exc:
        raise HTTPException(status_code=403, detail=f"Signature verification failed: {exc}")

    parts = req.message.split(":")
    expected_wallet = parts[1].lower() if len(parts) >= 2 else ""
    verified = recovered.lower() == expected_wallet

    return PreCheckResponse(
        wallet=recovered,
        verified=verified,
        ts=time.time(),
    )
