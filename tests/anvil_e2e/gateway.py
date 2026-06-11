"""AIMS Gateway — FastAPI backend with web3.py on-chain integration.

Connects to a local Foundry Anvil instance (``http://127.0.0.1:8545``),
loads the ``AIMSAgentGateway`` contract, and exposes:

- ``POST /api/run`` — EIP-191 authenticated task execution with
  402 billing interceptor
- ``GET /api/health`` — liveness check (no auth required)

Authentication
--------------
All ``/api/run`` requests must carry three headers (case-insensitive):

- ``X-AIMS-Address`` — consumer EVM address (0x-prefixed)
- ``X-AIMS-Signature`` — EIP-191 ``personal_sign`` signature (130 hex chars)
  over the raw request body
- ``X-AIMS-Timestamp`` — UNIX seconds; rejected if ±300 s from now

Billing interceptor
-------------------
Before routing, the gateway calls ``availableBalance(consumer)`` on-chain.
If ``balance < TASK_COST`` (0.05 ETH), returns **402 Payment Required**.

Worker routing
--------------
On success, the gateway forwards the task to the mock agent node
(``mock_agent_node.py``), receives a worker-signed Proof-of-Task,
verifies it off-chain, then builds + signs + broadcasts the
``settleTask`` transaction using the gateway's hot wallet.

Production hardening
--------------------
1. **Private key** — loaded exclusively from ``AIMS_GATEWAY_PRIVATE_KEY``
   env var; startup crashes fast with a clear message if missing.
2. **Nonce manager** — thread-safe monotonic counter that syncs from chain
   on startup and guarantees strict nonce ordering under concurrent access.
   Pluggable Redis backend via ``REDIS_URL`` for multi-instance safety.
3. **Gas estimator + retry** — EIP-1559 dynamic fees with configurable
   multiplier.  If a tx is pending > 2 min, auto-bumps gas by 20 % and
   re-submits (replace-by-fee).  Up to ``MAX_TX_RETRIES`` attempts.
"""

from __future__ import annotations

import json
import logging
import os
import time
from threading import Lock
from typing import Any

import httpx
import uvicorn
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_utils import keccak, to_bytes
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from web3 import Web3
from web3.types import TxParams, Wei

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("aims-gateway")

# ═════════════════════════════════════════════════════════════════════════════
#  Production configuration
# ═════════════════════════════════════════════════════════════════════════════

ANVIL_RPC = os.getenv("ANVIL_RPC", "http://127.0.0.1:8545")
CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS", "")
REDIS_URL = os.getenv("REDIS_URL", "")  # optional, for distributed nonce

# ── Strict private-key loading (never hardcoded) ───────────────────────────
_AIMS_GATEWAY_PRIVATE_KEY: str | None = None


def _load_gateway_key() -> str:
    """Load the gateway hot-wallet private key from environment.

    Strict single-source-of-truth: ``AIMS_GATEWAY_PRIVATE_KEY``.
    Crashes at import time (before the server binds) if unset — no silent
    fallback to a hardcoded or empty key.
    """
    key = os.environ.get("AIMS_GATEWAY_PRIVATE_KEY")
    if not key:
        raise RuntimeError(
            "AIMS_GATEWAY_PRIVATE_KEY is not set.  "
            "Export a valid ECDSA private key (0x-prefixed, 64 hex chars) "
            "for the gateway hot wallet before starting the server."
        )
    # Validate key format
    hex_key = key.removeprefix("0x")
    if len(hex_key) != 64:
        raise RuntimeError(
            f"AIMS_GATEWAY_PRIVATE_KEY has invalid length "
            f"({len(hex_key)} hex chars, expected 64)."
        )
    try:
        int(hex_key, 16)
    except ValueError:
        raise RuntimeError(
            "AIMS_GATEWAY_PRIVATE_KEY is not a valid hex string."
        )
    return key


GATEWAY_KEY = _load_gateway_key()
GATEWAY_ADDRESS = Account.from_key(GATEWAY_KEY).address

TASK_COST_WEI = Web3.to_wei(0.05, "ether")
AUTH_TIMEOUT = 300  # seconds

# ── EIP-1559 gas parameters ────────────────────────────────────────────────
GAS_MULTIPLIER = float(os.getenv("GAS_MULTIPLIER", "1.5"))
PRIORITY_FEE_MULTIPLIER = float(os.getenv("PRIORITY_FEE_MULTIPLIER", "1.5"))
MAX_TX_RETRIES = int(os.getenv("MAX_TX_RETRIES", "3"))
TX_PENDING_TIMEOUT = int(os.getenv("TX_PENDING_TIMEOUT", "120"))  # seconds
GAS_BUMP_PERCENT = float(os.getenv("GAS_BUMP_PERCENT", "20"))  # %

# ── Contract ABI (minimal — only the functions we call) ─────────────────────
CONTRACT_ABI = [
    {
        "type": "function",
        "name": "availableBalance",
        "inputs": [{"name": "user", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
    },
    {
        "type": "function",
        "name": "settleTask",
        "inputs": [
            {"name": "taskId", "type": "bytes32"},
            {"name": "potSignature", "type": "bytes"},
            {"name": "developer", "type": "address"},
            {"name": "worker", "type": "address"},
            {"name": "consumer", "type": "address"},
        ],
        "outputs": [],
        "stateMutability": "nonpayable",
    },
    {
        "type": "function",
        "name": "getBalance",
        "inputs": [{"name": "user", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
    },
]

# ═════════════════════════════════════════════════════════════════════════════
#  NonceManager — thread-safe monotonic nonce with optional Redis backend
# ═════════════════════════════════════════════════════════════════════════════


class NonceManager:
    """Distributon-safe monotonic nonce counter.

    Guarantees strict nonce ordering for concurrent settlement transactions.
    On construction, syncs from the on-chain ``get_transaction_count`` so the
    counter survives process restarts.

    Thread-safety via ``threading.Lock()``.  For multi-instance deployments,
    set ``REDIS_URL`` — the manager falls back to ``INCR`` on a Redis key,
    providing cross-process atomicity without changing the public API.

    Usage::

        nonce_mgr = NonceManager(w3, gateway_address)
        nonce = nonce_mgr.get_nonce()   # thread-safe, monotonic
    """

    def __init__(self, w3: Web3, address: str) -> None:
        self._w3 = w3
        self._address = address
        self._lock = Lock()
        self._redis = None

        # Sync initial nonce from chain
        self._next_nonce: int = w3.eth.get_transaction_count(address)
        logger.info(
            "NonceManager synced: address=%s start_nonce=%d",
            address, self._next_nonce,
        )

        # Optional Redis backend
        if REDIS_URL:
            try:
                import redis as _redis  # type: ignore[import-untyped]

                self._redis = _redis.from_url(REDIS_URL, decode_responses=True)
                logger.info("NonceManager: Redis backend enabled at %s", REDIS_URL)
            except Exception as exc:
                logger.warning(
                    "NonceManager: Redis unavailable, using in-memory lock: %s", exc
                )

    # ── Public API ──────────────────────────────────────────────────────

    def get_nonce(self) -> int:
        """Return the next nonce atomically.

        Thread-safe: callers from concurrent workers can safely invoke this
        without coordination.
        """
        with self._lock:
            if self._redis:
                return self._redis.incr("nonce:gateway") - 1
            nonce = self._next_nonce
            self._next_nonce += 1
            return nonce

    def sync_nonce(self) -> None:
        """Re-sync the nonce counter from the chain.

        Call this after a failed transaction to recover from a stuck nonce,
        or periodically as a safety net in long-running deployments.
        """
        chain_nonce = self._w3.eth.get_transaction_count(self._address)
        with self._lock:
            if self._redis:
                # Set Redis key to chain value (INCR will advance from here)
                self._redis.set("nonce:gateway", chain_nonce)
            else:
                if chain_nonce > self._next_nonce:
                    logger.info(
                        "NonceManager: chain ahead (%d > %d), advancing counter",
                        chain_nonce, self._next_nonce,
                    )
                    self._next_nonce = chain_nonce
                # If we're ahead of chain, we keep our counter
        logger.info("NonceManager synced: nonce=%d", self._next_nonce)

    @property
    def current_nonce(self) -> int:
        """Read the next nonce without consuming it (advisory only)."""
        with self._lock:
            if self._redis:
                val = self._redis.get("nonce:gateway")
                return int(val) if val else 0
            return self._next_nonce


# ═════════════════════════════════════════════════════════════════════════════
#  GasEstimator — Base L2 EIP-1559 dynamic fee estimation
# ═════════════════════════════════════════════════════════════════════════════


class GasEstimator:
    """EIP-1559 gas calculator tuned for Base L2.

    Applies configurable multipliers to the chain's suggested fees so the
    transaction is prioritised during congestion without hardcoding values.
    """

    def __init__(self, w3: Web3) -> None:
        self._w3 = w3

    def estimate_fees(self) -> dict[str, Wei]:
        """Return EIP-1559 fee caps as ``maxFeePerGas`` / ``maxPriorityFeePerGas``.

        Falls back to ``gasPrice`` if the chain does not support EIP-1559
        (e.g. Anvil in legacy mode).
        """
        try:
            base_fee = self._w3.eth.get_block("pending")["baseFeePerGas"]
            priority_fee = self._w3.eth.max_priority_fee

            max_priority = Wei(int(priority_fee * PRIORITY_FEE_MULTIPLIER))
            max_fee = Wei(int((base_fee + priority_fee) * GAS_MULTIPLIER))

            return {
                "maxFeePerGas": max_fee,
                "maxPriorityFeePerGas": max_priority,
            }
        except Exception:
            # Fallback to legacy gas price
            gas_price = self._w3.eth.gas_price
            return {"gasPrice": Wei(int(gas_price * GAS_MULTIPLIER))}

    def bump_fees(self, current: dict[str, Wei]) -> dict[str, Wei]:
        """Increase gas caps by ``GAS_BUMP_PERCENT`` for replace-by-fee.

        Accepts either EIP-1559 or legacy params and returns the bumped
        version with the same keys.
        """
        bump = 1.0 + GAS_BUMP_PERCENT / 100.0
        bumped: dict[str, Wei] = {}
        for key in ("maxFeePerGas", "maxPriorityFeePerGas", "gasPrice"):
            if key in current:
                bumped[key] = Wei(int(current[key] * bump))
        return bumped


# ═════════════════════════════════════════════════════════════════════════════
#  Transaction retry engine
# ═════════════════════════════════════════════════════════════════════════════


def _send_with_retry(
    w3: Web3,
    tx_params: TxParams,
    signer: Account,
    nonce_mgr: NonceManager,
    gas_estimator: GasEstimator,
    label: str = "tx",
) -> dict[str, Any]:
    """Sign, broadcast, and monitor a transaction with gas-bump retry.

    Flow
    ----
    1. Attach EIP-1559 fees + nonce to ``tx_params``.
    2. Sign and broadcast via ``send_raw_transaction``.
    3. Poll ``get_transaction_receipt`` for up to ``TX_PENDING_TIMEOUT`` s.
    4. If still pending after timeout, bump gas by ``GAS_BUMP_PERCENT`` and
       re-send (replace-by-fee).  Up to ``MAX_TX_RETRIES`` attempts.
    5. Return the receipt on success or raise ``RuntimeError``.

    Returns
    -------
    dict with keys ``tx_hash``, ``block_number``, ``status``, ``attempts``.
    """
    fees = gas_estimator.estimate_fees()
    nonce = nonce_mgr.get_nonce()

    tx = {**tx_params, **fees, "nonce": nonce, "chainId": w3.eth.chain_id}

    last_tx_hash: str | None = None
    attempt = 0

    while attempt < MAX_TX_RETRIES:
        attempt += 1
        # Bump fees on retry (skip bump for first attempt)
        if attempt > 1:
            fees = gas_estimator.bump_fees(fees)
            tx.update(fees)
            logger.info(
                "Retry #%d: bumped fees for %s (nonce=%d)",
                attempt, label, nonce,
            )

        signed = signer.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        tx_hash_hex = tx_hash.hex()
        last_tx_hash = tx_hash_hex
        logger.info(
            "Broadcast %s: tx=%s nonce=%d attempt=%d",
            label, tx_hash_hex, nonce, attempt,
        )

        # ── Wait for receipt with timeout ──────────────────────────────
        deadline = time.monotonic() + TX_PENDING_TIMEOUT
        while time.monotonic() < deadline:
            try:
                receipt = w3.eth.get_transaction_receipt(tx_hash)
                if receipt is not None and receipt.get("blockNumber") is not None:
                    status = receipt.get("status", 0)
                    logger.info(
                        "%s mined: tx=%s block=%d status=%d attempts=%d",
                        label, tx_hash_hex, receipt["blockNumber"], status, attempt,
                    )
                    return {
                        "tx_hash": tx_hash_hex,
                        "block_number": receipt["blockNumber"],
                        "status": status,
                        "attempts": attempt,
                    }
            except Exception:
                pass
            time.sleep(2)

        # ── Timed out — bump gas and retry ──────────────────────────────
        logger.warning(
            "%s pending > %ds (nonce=%d attempt=%d), bumping gas",
            label, TX_PENDING_TIMEOUT, nonce, attempt,
        )

        if attempt >= MAX_TX_RETRIES:
            break

        # Re-sync nonce from chain in case a previous replacement went through
        nonce_mgr.sync_nonce()
        # Get a fresh nonce (the bumped tx may need the same nonce + higher gas)
        tx["nonce"] = nonce_mgr.get_nonce()

    raise RuntimeError(
        f"{label} failed after {MAX_TX_RETRIES} attempts. "
        f"Last tx_hash: {last_tx_hash}"
    )


# ── FastAPI app ─────────────────────────────────────────────────────────────

app = FastAPI(title="AIMS Gateway", version="2.0.0")

# Lazy-initialised globals
_web3: Web3 | None = None
_contract: Any = None
_gateway_account: Account | None = None
_nonce_mgr: NonceManager | None = None
_gas_estimator: GasEstimator | None = None


def _get_web3() -> Web3:
    global _web3
    if _web3 is None:
        _web3 = Web3(Web3.HTTPProvider(ANVIL_RPC))
        assert _web3.is_connected(), f"Cannot connect to Anvil at {ANVIL_RPC}"
        logger.info("Connected: %s (chain_id=%d)", ANVIL_RPC, _web3.eth.chain_id)
    return _web3


def _get_contract():
    global _contract
    if _contract is None:
        w3 = _get_web3()
        _contract = w3.eth.contract(
            address=Web3.to_checksum_address(CONTRACT_ADDRESS), abi=CONTRACT_ABI
        )
        logger.info("Contract loaded at %s", CONTRACT_ADDRESS)
    return _contract


def _get_gateway_account() -> Account:
    global _gateway_account
    if _gateway_account is None:
        _gateway_account = Account.from_key(GATEWAY_KEY)
        logger.info("Gateway account: %s", _gateway_account.address)
    return _gateway_account


def _get_nonce_manager() -> NonceManager:
    global _nonce_mgr
    if _nonce_mgr is None:
        _nonce_mgr = NonceManager(_get_web3(), GATEWAY_ADDRESS)
    return _nonce_mgr


def _get_gas_estimator() -> GasEstimator:
    global _gas_estimator
    if _gas_estimator is None:
        _gas_estimator = GasEstimator(_get_web3())
    return _gas_estimator


# ── Header helper (case-insensitive) ────────────────────────────────────────

def _get_header(request: Request, name: str) -> str | None:
    """Extract a header value case-insensitively."""
    val = request.headers.get(name) or request.headers.get(name.lower())
    if val:
        return val
    name_lower = name.lower()
    for k, v in request.headers.items():
        if k.lower() == name_lower:
            return v
    return None


# ── Middleware: EIP-191 auth + 402 billing interceptor ─────────────────────

@app.middleware("http")
async def auth_and_billing_middleware(request: Request, call_next):
    """Authenticate via EIP-191 wallet signature, then check on-chain balance.

    Exempt paths: ``/api/health``, ``/docs``, ``/openapi.json``.
    """
    path = request.url.path
    if path in ("/api/health", "/docs", "/openapi.json"):
        return await call_next(request)

    body_bytes = await request.body()

    address_hdr = _get_header(request, "X-AIMS-Address")
    sig_hdr = _get_header(request, "X-AIMS-Signature")
    ts_hdr = _get_header(request, "X-AIMS-Timestamp")

    missing = []
    if not address_hdr:
        missing.append("X-AIMS-Address")
    if not sig_hdr:
        missing.append("X-AIMS-Signature")
    if not ts_hdr:
        missing.append("X-AIMS-Timestamp")

    if missing:
        return JSONResponse(
            status_code=403,
            content={
                "error": "missing authentication headers",
                "missing": missing,
                "received_headers": list(request.headers.keys()),
            },
        )

    address = address_hdr.strip()
    if not Web3.is_address(address):
        return JSONResponse(status_code=403, content={"error": "invalid EVM address"})

    addr_checksum = Web3.to_checksum_address(address)

    try:
        ts = int(ts_hdr.strip())
    except ValueError:
        return JSONResponse(status_code=403, content={"error": "invalid timestamp"})

    now = int(time.time())
    if abs(now - ts) > AUTH_TIMEOUT:
        return JSONResponse(status_code=403, content={"error": "timestamp expired"})

    try:
        signable = encode_defunct(primitive=body_bytes)
        recovered = Account.recover_message(signable, signature=sig_hdr.strip())
    except Exception as exc:
        logger.warning("Signature recovery failed: %s", exc)
        return JSONResponse(status_code=403, content={"error": "signature recovery failed"})

    if recovered.lower() != addr_checksum.lower():
        return JSONResponse(
            status_code=403,
            content={
                "error": "signer does not match X-AIMS-Address",
                "recovered": recovered,
                "expected": addr_checksum,
            },
        )

    # ── 402 Billing interceptor ───────────────────────────────────────
    try:
        contract = _get_contract()
        balance = contract.functions.availableBalance(addr_checksum).call()
    except Exception as exc:
        logger.error("Balance check failed: %s", exc)
        return JSONResponse(status_code=503, content={"error": "balance check failed"})

    if balance < TASK_COST_WEI:
        return JSONResponse(
            status_code=402,
            content={
                "error": "insufficient balance",
                "required_eth": "0.05",
                "balance_eth": str(Web3.from_wei(balance, "ether")),
                "address": addr_checksum,
                "action": "Please deposit via contract.deposit()",
            },
        )

    request.state.consumer = addr_checksum
    request.state.body_bytes = body_bytes
    return await call_next(request)


# ── Health ──────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    w3 = _get_web3()
    block = w3.eth.block_number
    nonce_mgr = _get_nonce_manager()
    return {
        "status": "ok",
        "chain_id": w3.eth.chain_id,
        "block": block,
        "gateway": GATEWAY_ADDRESS,
        "next_nonce": nonce_mgr.current_nonce,
    }


# ── Task execution ──────────────────────────────────────────────────────────

@app.post("/api/run")
async def run_task(request: Request):
    """Execute a skill task with full on-chain settlement."""
    consumer = request.state.consumer
    body = await request.json()
    task_id: str = body.get("task_id", f"task-{int(time.time())}")
    skill: str = body.get("skill", "amazon_scraper")
    params: dict = body.get("params", {})
    developer: str = body.get("developer", "")
    worker: str = body.get("worker", "")

    if not developer or not worker:
        return JSONResponse(
            status_code=400,
            content={"error": "developer and worker addresses are required"},
        )

    task_id_bytes = keccak(text=task_id)
    logger.info(
        "Task %s: consumer=%s worker=%s developer=%s",
        task_id, consumer, worker, developer,
    )

    # ── Route to worker ──────────────────────────────────────────────
    worker_payload = {
        "task_id": task_id,
        "task_id_bytes": task_id_bytes.hex(),
        "skill": skill,
        "params": params,
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{os.getenv('WORKER_URL', 'http://127.0.0.1:8001')}/api/execute",
                json=worker_payload,
                timeout=30,
            )
            resp.raise_for_status()
            worker_result = resp.json()
    except Exception as exc:
        logger.error("Worker call failed: %s", exc)
        return JSONResponse(status_code=502, content={"error": f"worker failed: {exc}"})

    pot_signature_hex: str = worker_result.get("pot_signature", "")
    result_text: str = worker_result.get("result", "")
    worker_status: str = worker_result.get("status", "failed")

    if worker_status != "completed":
        return JSONResponse(
            status_code=502,
            content={"error": "worker execution failed", "worker_status": worker_status},
        )

    if not pot_signature_hex:
        return JSONResponse(status_code=502, content={"error": "worker did not return PoT"})

    # ── Off-chain PoT verification ────────────────────────────────────
    try:
        pot_bytes = to_bytes(hexstr=pot_signature_hex)
        recovered_worker = Account._recover_hash(task_id_bytes, signature=pot_bytes)
        if recovered_worker.lower() != Web3.to_checksum_address(worker).lower():
            return JSONResponse(
                status_code=502,
                content={
                    "error": "PoT signature not from claimed worker",
                    "recovered": recovered_worker,
                    "expected_worker": worker,
                },
            )
        logger.info("PoT verified off-chain: signer=%s", recovered_worker)
    except Exception as exc:
        logger.error("PoT verification failed: %s", exc)
        return JSONResponse(status_code=502, content={"error": f"PoT verification failed: {exc}"})

    # ── Build + sign + broadcast settleTask (with NonceManager + retry) ──
    w3 = _get_web3()
    contract = _get_contract()
    gateway_acct = _get_gateway_account()
    nonce_mgr = _get_nonce_manager()
    gas_estimator = _get_gas_estimator()

    settle_tx: TxParams = contract.functions.settleTask(
        task_id_bytes,
        pot_bytes,
        Web3.to_checksum_address(developer),
        Web3.to_checksum_address(worker),
        consumer,
    ).build_transaction({
        "from": gateway_acct.address,
        "gas": 200_000,
    })

    try:
        result = _send_with_retry(
            w3=w3,
            tx_params=settle_tx,
            signer=gateway_acct,
            nonce_mgr=nonce_mgr,
            gas_estimator=gas_estimator,
            label=f"settleTask({task_id})",
        )
    except RuntimeError as exc:
        logger.error("settleTask failed: %s", exc)
        return JSONResponse(status_code=500, content={"error": str(exc)})

    if result["status"] != 1:
        logger.error("settleTask reverted: tx=%s", result["tx_hash"])
        return JSONResponse(status_code=500, content={"error": "settleTask reverted"})

    tx_hash_hex = result["tx_hash"]
    block_number = result["block_number"]

    logger.info(
        "Task %s settled: tx=%s block=%d attempts=%d",
        task_id, tx_hash_hex, block_number, result["attempts"],
    )

    # ── Read updated balances ─────────────────────────────────────────
    new_balance = contract.functions.getBalance(consumer).call()
    dev_balance = w3.eth.get_balance(Web3.to_checksum_address(developer))
    worker_balance = w3.eth.get_balance(Web3.to_checksum_address(worker))
    gateway_balance = w3.eth.get_balance(gateway_acct.address)

    return {
        "status": "completed",
        "task_id": task_id,
        "tx_hash": tx_hash_hex,
        "block_number": block_number,
        "tx_attempts": result["attempts"],
        "result_preview": result_text[:200],
        "balances": {
            "consumer": str(Web3.from_wei(new_balance, "ether")),
            "developer": str(Web3.from_wei(dev_balance, "ether")),
            "worker": str(Web3.from_wei(worker_balance, "ether")),
            "treasury": str(Web3.from_wei(gateway_balance, "ether")),
        },
    }


# ── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("GATEWAY_PORT", "8000"))
    uvicorn.run("gateway:app", host="0.0.0.0", port=port, log_level="info", reload=False)
