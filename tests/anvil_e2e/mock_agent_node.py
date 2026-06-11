"""Mock Agent Node — worker simulator for Anvil E2E tests.

Receives tasks from the AIMS Gateway, simulates execution, and returns a
worker-signed Proof-of-Task (ECDSA signature over ``keccak256(taskId)``).

Endpoints
---------
- ``POST /api/execute`` — execute a skill task and return PoT

Configuration
-------------
- ``WORKER_KEY`` — worker's ECDSA private key (env, default: anvil key #1)
- ``WORKER_PORT`` — HTTP listen port (env, default: 8001)
- ``EXECUTION_DELAY`` — simulated execution time in seconds (env, default: 0.1)
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import uvicorn
from eth_account import Account
from eth_utils import keccak
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("mock-agent-node")

# ── Configuration ──────────────────────────────────────────────────────────
WORKER_KEY = os.getenv("WORKER_KEY", "")
WORKER_PORT = int(os.getenv("WORKER_PORT", "8001"))
EXECUTION_DELAY = float(os.getenv("EXECUTION_DELAY", "0.1"))

assert WORKER_KEY, "WORKER_KEY environment variable is required"

_WORKER_ACCT = Account.from_key(WORKER_KEY)
logger.info("Worker account: %s", _WORKER_ACCT.address)

app = FastAPI(title="Mock Agent Node", version="1.0.0")


def _sign_pot(task_id_bytes: bytes) -> str:
    """Sign keccak256(taskId) with the worker's private key.

    Returns 130-char hex string (65 bytes, no 0x prefix).
    """
    hash_to_sign = keccak(task_id_bytes)
    signed = Account.unsafe_sign_hash(hash_to_sign, WORKER_KEY)
    return signed.signature.hex()


@app.post("/api/execute")
async def execute_task(request: Request):
    """Execute a skill task and return a worker-signed Proof-of-Task.

    Request body
    ------------
    - ``task_id``: str — human-readable task identifier
    - ``task_id_bytes``: str — hex-encoded bytes32 task identifier
    - ``skill``: str — skill name
    - ``params``: dict — skill parameters
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "invalid JSON"})

    task_id: str = body.get("task_id", "")
    task_id_bytes_hex: str = body.get("task_id_bytes", "")
    skill: str = body.get("skill", "")
    params: dict = body.get("params", {})

    if not task_id or not task_id_bytes_hex:
        return JSONResponse(status_code=400, content={"error": "task_id and task_id_bytes are required"})

    logger.info("Executing task=%s skill=%s params=%s", task_id, skill, params)

    # ── Simulate execution delay ────────────────────────────────────────
    if EXECUTION_DELAY > 0:
        time.sleep(EXECUTION_DELAY)

    # ── Generate mock result ────────────────────────────────────────────
    result = json.dumps({
        "task_id": task_id,
        "status": "completed",
        "output": f"Mock execution result for {skill} task {task_id}",
        "timestamp": int(time.time()),
    })

    # ── Sign Proof-of-Task ─────────────────────────────────────────────
    task_id_bytes = bytes.fromhex(task_id_bytes_hex)
    pot_signature = _sign_pot(task_id_bytes)

    logger.info(
        "Task %s completed | worker=%s | pot_len=%d",
        task_id, _WORKER_ACCT.address, len(pot_signature),
    )

    return {
        "status": "completed",
        "task_id": task_id,
        "result": result,
        "pot_signature": pot_signature,
    }


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "worker": _WORKER_ACCT.address,
    }


# ── Entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "mock_agent_node:app",
        host="0.0.0.0",
        port=WORKER_PORT,
        log_level="info",
        reload=False,
    )
