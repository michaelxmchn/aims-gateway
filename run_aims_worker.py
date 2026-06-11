#!/usr/bin/env python3
"""AIMS Worker Node — standalone OpenClaw-compatible worker for multi-machine deployment.

Claims tasks from the AIMS Gateway via HTTP, executes them locally, and submits
results with EIP-191 signed Proof-of-Task back to the gateway for on-chain
70/25/5 settlement.

Usage
-----
::

    # Set your worker private key (anvil key #10 in dev)
    export WORKER_KEY="0xf214f2b2cd398c806f84e317254e0f0b801d0643303237d746c6c2c7f1bcdb8f"

    # Point to the gateway (cores machine running gateway.py)
    export AIMS_GATEWAY_URL="http://192.168.1.17:8000"

    # Optional: set a custom worker_id (defaults to wallet address)
    export WORKER_ID="openclaw-node-01"

    # Run
    python3 run_aims_worker.py
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import httpx
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_utils import keccak

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s  %(message)s",
)
logger = logging.getLogger("aims-worker")

# ═════════════════════════════════════════════════════════════════════════════
#  Configuration
# ═════════════════════════════════════════════════════════════════════════════

GATEWAY_URL = os.getenv("AIMS_GATEWAY_URL", "http://192.168.1.17:8000").rstrip("/")
WORKER_KEY = os.getenv("WORKER_KEY", "")
WORKER_ID = os.getenv("WORKER_ID", "")
CLAIM_TIMEOUT = int(os.getenv("CLAIM_TIMEOUT", "30"))  # seconds to execute a task
HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", "15"))  # seconds
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "3"))  # seconds between claim attempts

if not WORKER_KEY:
    raise SystemExit("FATAL: WORKER_KEY environment variable is required. "
                      "Set it to the worker's ECDSA private key (0x-prefixed, 64 hex).")

# Validate key format
_hex_key = WORKER_KEY.removeprefix("0x")
if len(_hex_key) != 64:
    raise SystemExit(f"FATAL: WORKER_KEY has invalid length ({len(_hex_key)} hex chars, expected 64).")
try:
    int(_hex_key, 16)
except ValueError:
    raise SystemExit("FATAL: WORKER_KEY is not a valid hex string.")

_WORKER_ACCT = Account.from_key(WORKER_KEY)
_WORKER_ADDRESS = _WORKER_ACCT.address
_WORKER_ID = WORKER_ID or _WORKER_ADDRESS

logger.info("Worker identity:")
logger.info("  address:    %s", _WORKER_ADDRESS)
logger.info("  worker_id:  %s", _WORKER_ID)
logger.info("  gateway:    %s", GATEWAY_URL)


# ═════════════════════════════════════════════════════════════════════════════
#  EIP-191 signing helpers
# ═════════════════════════════════════════════════════════════════════════════

def eip191_sign(body_bytes: bytes) -> str:
    """Sign the raw body with EIP-191 personal_sign.

    Uses ``encode_defunct`` which adds the ``\\x19Ethereum Signed Message:\\n``
    prefix — identical to what the gateway middleware does on the verification
    side via ``Account.recover_message``.

    Returns 130 hex chars (no 0x prefix).
    """
    signable = encode_defunct(primitive=body_bytes)
    signed = _WORKER_ACCT.sign_message(signable)
    return signed.signature.hex()


def auth_headers(body: bytes) -> dict[str, str]:
    """Build the three EIP-191 auth headers for a request."""
    return {
        "X-Wallet-Address": _WORKER_ADDRESS,
        "X-Signature": eip191_sign(body),
        "X-Timestamp": str(int(time.time())),
        "Content-Type": "application/json",
    }


def sign_pot(task_id_bytes: bytes) -> str:
    """Sign keccak256(taskId) with the worker's private key.

    Produces the Proof-of-Task that the gateway verifies off-chain before
    calling ``settleTask`` on the contract.

    Returns 130 hex chars (no 0x prefix).
    """
    h = keccak(task_id_bytes)
    signed = Account.unsafe_sign_hash(h, WORKER_KEY)
    return signed.signature.hex()


# ═════════════════════════════════════════════════════════════════════════════
#  Heartbeat
# ═════════════════════════════════════════════════════════════════════════════

_last_heartbeat: float = 0


async def send_heartbeat(client: httpx.AsyncClient) -> bool:
    """POST /api/workers/heartbeat with EIP-191 auth.

    Reports this worker's address to the gateway so it appears in the
    ``workers_active`` count on ``GET /api/health``.
    """
    global _last_heartbeat
    now = time.time()
    if now - _last_heartbeat < HEARTBEAT_INTERVAL:
        return True  # not due yet

    payload = {"worker_id": _WORKER_ID}
    body = json.dumps(payload).encode("utf-8")
    headers = auth_headers(body)

    try:
        resp = await client.post(
            f"{GATEWAY_URL}/api/workers/heartbeat",
            content=body,
            headers=headers,
            timeout=10,
        )
        if resp.status_code == 200:
            _last_heartbeat = now
            logger.debug("Heartbeat ack'd by gateway")
            return True
        else:
            logger.warning("Heartbeat returned HTTP %d: %s", resp.status_code, resp.text[:120])
            return False
    except Exception as exc:
        logger.warning("Heartbeat failed: %s", exc)
        return False


# ═════════════════════════════════════════════════════════════════════════════
#  Task claim & execute
# ═════════════════════════════════════════════════════════════════════════════

async def claim_task(client: httpx.AsyncClient) -> dict[str, Any] | None:
    """POST /api/tasks/claim to pull a PENDING task from the broker.

    Returns the task dict on success, or ``None`` if the queue is empty.
    """
    payload = {"worker_id": _WORKER_ID}
    body = json.dumps(payload).encode("utf-8")
    headers = auth_headers(body)

    try:
        resp = await client.post(
            f"{GATEWAY_URL}/api/tasks/claim",
            content=body,
            headers=headers,
            timeout=10,
        )
        if resp.status_code == 204:
            return None
        if resp.status_code == 200:
            return resp.json()
        logger.warning("Claim returned HTTP %d: %s", resp.status_code, resp.text[:200])
        return None
    except Exception as exc:
        logger.warning("Claim request failed: %s", exc)
        return None


def execute_skill(task: dict[str, Any]) -> dict[str, Any]:
    """Execute the claimed skill locally and return result data.

    In production this would call the actual skill logic (e.g. via
    ``importlib`` or a subprocess).  Here we simulate a realistic output.
    """
    skill_id = task.get("skill_id", "unknown")
    params = task.get("payload") or task.get("params") or {}
    task_id = task["task_id"]

    logger.info("Executing skill=%s task=%s params=%s", skill_id, task_id, params)

    # Simulate execution delay proportional to compute tier
    tier = task.get("compute_tier", 1)
    delay = 0.5 * tier
    time.sleep(delay)

    # Generate mock result
    result_data = {
        "task_id": task_id,
        "status": "completed",
        "skill": skill_id,
        "output": {
            "data": f"Mock execution result for {skill_id} — task {task_id}",
            "params_received": params,
            "execution_time_s": delay,
        },
        "timestamp": int(time.time()),
    }

    return result_data


# ═════════════════════════════════════════════════════════════════════════════
#  Task submit — the critical settlement endpoint
# ═════════════════════════════════════════════════════════════════════════════

async def submit_result(
    client: httpx.AsyncClient,
    task_id: str,
    result_data: dict[str, Any],
    pot_signature: str,
) -> dict[str, Any] | None:
    """POST /api/tasks/submit with EIP-191 signed task result + PoT.

    This is the key settlement handshake:

    1. The gateway receives the result + PoT signature.
    2. It verifies the PoT off-chain (``Account._recover_hash``).
    3. It calls ``settleTask`` on the Solidity contract.
    4. The contract splits 70/25/5 among Developer / Worker / Treasury.

    Returns the gateway's response dict, or ``None`` on failure.
    """
    payload = {
        "task_id": task_id,
        "worker_id": _WORKER_ID,
        "result_data": result_data,
        "pot_signature": pot_signature,
    }
    body = json.dumps(payload).encode("utf-8")
    headers = auth_headers(body)

    try:
        resp = await client.post(
            f"{GATEWAY_URL}/api/tasks/submit",
            content=body,
            headers=headers,
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            outcome = data.get("outcome", "UNKNOWN")
            pot = data.get("pot", "")
            logger.info(
                "Submit OK: task=%s outcome=%s pot=%s gas=%.4f payout=%.4f",
                task_id, outcome,
                pot[:20] + "…" if pot else "none",
                data.get("gas_cost", 0),
                data.get("developer_payout", 0),
            )
            return data
        else:
            logger.error(
                "Submit FAILED: task=%s HTTP %d — %s",
                task_id, resp.status_code, resp.text[:300],
            )
            return None
    except Exception as exc:
        logger.error("Submit request failed: task=%s error=%s", task_id, exc)
        return None


# ═════════════════════════════════════════════════════════════════════════════
#  Main worker loop
# ═════════════════════════════════════════════════════════════════════════════

async def run_worker_loop() -> None:
    """Infinite claim → execute → submit loop.

    The worker:
    1. Sends a startup heartbeat.
    2. Repeatedly tries to claim a PENDING task from the broker.
    3. On claim: executes the skill, signs the PoT, submits result.
    4. Between cycles: sends heartbeats on the configured interval.
    """
    stats = {"claimed": 0, "completed": 0, "failed": 0}

    logger.info("─" * 50)
    logger.info("Worker node started — polling %s", GATEWAY_URL)
    logger.info("  worker_id:     %s", _WORKER_ID)
    logger.info("  worker_addr:   %s", _WORKER_ADDRESS)
    logger.info("  poll_interval: %ds", POLL_INTERVAL)
    logger.info("  heartbeat:     every %ds", HEARTBEAT_INTERVAL)
    logger.info("─" * 50)

    async with httpx.AsyncClient(timeout=15) as client:
        # ── Startup heartbeat ────────────────────────────────────────────
        await send_heartbeat(client)

        # ── Main loop ─────────────────────────────────────────────────────
        while True:
            try:
                # Heartbeat (rate-limited internally)
                await send_heartbeat(client)

                # Claim a task
                task = await claim_task(client)
                if task is None:
                    await asyncio.sleep(POLL_INTERVAL)
                    continue

                stats["claimed"] += 1
                task_id = task["task_id"]
                skill_id = task.get("skill_id", "unknown")
                logger.info("Claimed: task=%s skill=%s", task_id, skill_id)

                # Execute
                result_data = execute_skill(task)

                # Generate Proof-of-Task: ECDSA sign keccak256(taskId)
                task_id_bytes = keccak(text=task_id)
                pot_sig = sign_pot(task_id_bytes)

                # Submit with PoT
                submit_resp = await submit_result(client, task_id, result_data, pot_sig)
                if submit_resp is not None:
                    stats["completed"] += 1
                else:
                    stats["failed"] += 1

                # Log stats every 5 tasks
                if (stats["claimed"] % 5) == 0:
                    logger.info(
                        "Stats: claimed=%d completed=%d failed=%d",
                        stats["claimed"], stats["completed"], stats["failed"],
                    )

            except KeyboardInterrupt:
                logger.info("Shutdown requested.")
                break
            except Exception as exc:
                logger.error("Unexpected error in main loop: %s", exc, exc_info=True)
                await asyncio.sleep(POLL_INTERVAL * 2)

    logger.info("─" * 50)
    logger.info("Worker stopped.  Final stats:")
    logger.info("  claimed:   %d", stats["claimed"])
    logger.info("  completed: %d", stats["completed"])
    logger.info("  failed:    %d", stats["failed"])
    logger.info("─" * 50)


# ═════════════════════════════════════════════════════════════════════════════
#  Entry point
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import asyncio

    try:
        asyncio.run(run_worker_loop())
    except KeyboardInterrupt:
        logger.info("Exiting.")
