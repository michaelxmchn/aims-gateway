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
- ``X-AIMS-Timestamp`` — UNIX seconds; rejected if ±300 s from now

Billing interceptor
-------------------
Before routing, the gateway calls ``availableBalance(consumer)`` on-chain.
If ``balance < TASK_COST`` (0.05 ETH), returns **402 Payment Required**.

Worker routing
--------------
On success, the gateway forwards the task to the mock agent node
(``mock_agent_node.py``), receives a worker-signed Proof-of-Task,
verifies it off-chain, then builds + signs + broadcasts the
``settleTask`` transaction using the gateway's hot wallet.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import uvicorn
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_utils import keccak, to_bytes
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from web3 import Web3

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("aims-gateway")

# ── Configuration (overridable via env) ─────────────────────────────────────
ANVIL_RPC = os.getenv("ANVIL_RPC", "http://127.0.0.1:8545")
CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS", "")
GATEWAY_KEY = os.getenv("GATEWAY_KEY", "")
WORKER_URL = os.getenv("WORKER_URL", "http://127.0.0.1:8001")

TASK_COST_WEI = Web3.to_wei(0.05, "ether")
AUTH_TIMEOUT = 300  # seconds

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

# ── FastAPI app ─────────────────────────────────────────────────────────────

app = FastAPI(title="AIMS Gateway", version="1.0.0")

# Lazy-initialised Web3 + contract
_web3: Web3 | None = None
_contract: Any = None
_gateway_account: Account | None = None


def _get_web3() -> Web3:
    global _web3
    if _web3 is None:
        _web3 = Web3(Web3.HTTPProvider(ANVIL_RPC))
        assert _web3.is_connected(), f"Cannot connect to Anvil at {ANVIL_RPC}"
        logger.info("Connected to Anvil: %s (chain_id=%d)", ANVIL_RPC, _web3.eth.chain_id)
    return _web3


def _get_contract():
    global _contract
    if _contract is None:
        w3 = _get_web3()
        _contract = w3.eth.contract(address=Web3.to_checksum_address(CONTRACT_ADDRESS), abi=CONTRACT_ABI)
        logger.info("Contract loaded at %s", CONTRACT_ADDRESS)
    return _contract


def _get_gateway_account() -> Account:
    global _gateway_account
    if _gateway_account is None:
        _gateway_account = Account.from_key(GATEWAY_KEY)
        logger.info("Gateway account: %s", _gateway_account.address)
    return _gateway_account


# ── Header helper (case-insensitive) ────────────────────────────────────────

def _get_header(request: Request, name: str) -> str | None:
    """Extract a header value case-insensitively."""
    # Direct match first
    val = request.headers.get(name) or request.headers.get(name.lower())
    if val:
        return val
    # Scan all keys
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

    # ── Read body once (cache for downstream) ──────────────────────────
    body_bytes = await request.body()

    # ── Extract headers (case-insensitive) ────────────────────────────
    address_hdr = _get_header(request, "X-AIMS-Address")
    sig_hdr = _get_header(request, "X-AIMS-Signature")
    ts_hdr = _get_header(request, "X-AIMS-Timestamp")

    # ── Validate presence ─────────────────────────────────────────────
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

    # ── Validate address format ───────────────────────────────────────
    address = address_hdr.strip()
    if not Web3.is_address(address):
        return JSONResponse(status_code=403, content={"error": "invalid EVM address"})

    addr_checksum = Web3.to_checksum_address(address)

    # ── Validate timestamp window ─────────────────────────────────────
    try:
        ts = int(ts_hdr.strip())
    except ValueError:
        return JSONResponse(status_code=403, content={"error": "invalid timestamp"})

    now = int(time.time())
    if abs(now - ts) > AUTH_TIMEOUT:
        return JSONResponse(status_code=403, content={"error": "timestamp expired"})

    # ── Recover signer from EIP-191 signature ─────────────────────────
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

    # ── Attach consumer address to request state ──────────────────────
    request.state.consumer = addr_checksum
    request.state.body_bytes = body_bytes
    return await call_next(request)


# ── Health ──────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    w3 = _get_web3()
    block = w3.eth.block_number
    return {"status": "ok", "chain_id": w3.eth.chain_id, "block": block}


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
    import httpx
    worker_payload = {
        "task_id": task_id,
        "task_id_bytes": task_id_bytes.hex(),
        "skill": skill,
        "params": params,
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{WORKER_URL}/api/execute",
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

    # ── Build + sign + broadcast settleTask ───────────────────────────
    w3 = _get_web3()
    contract = _get_contract()
    gateway_acct = _get_gateway_account()

    settle_tx = contract.functions.settleTask(
        task_id_bytes,
        pot_bytes,
        Web3.to_checksum_address(developer),
        Web3.to_checksum_address(worker),
        consumer,
    ).build_transaction({
        "from": gateway_acct.address,
        "nonce": w3.eth.get_transaction_count(gateway_acct.address),
        "gas": 200_000,
        "gasPrice": w3.eth.gas_price,
    })

    signed_tx = gateway_acct.sign_transaction(settle_tx)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

    if receipt["status"] != 1:
        logger.error("settleTask reverted: tx=%s", tx_hash.hex())
        return JSONResponse(status_code=500, content={"error": "settleTask reverted"})

    logger.info(
        "Task %s settled: tx=%s block=%d",
        task_id, tx_hash.hex(), receipt["blockNumber"],
    )

    # ── Read updated balances ─────────────────────────────────────────
    new_balance = contract.functions.getBalance(consumer).call()
    dev_balance = w3.eth.get_balance(Web3.to_checksum_address(developer))
    worker_balance = w3.eth.get_balance(Web3.to_checksum_address(worker))
    gateway_balance = w3.eth.get_balance(gateway_acct.address)

    return {
        "status": "completed",
        "task_id": task_id,
        "tx_hash": tx_hash.hex(),
        "block_number": receipt["blockNumber"],
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
