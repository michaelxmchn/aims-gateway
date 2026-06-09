"""Production DePIN Worker — claims & submits tasks through the AIMS Gateway.

Run::

    python -m src.worker.worker

The worker runs an infinite loop:

  1. **Claim** — ``POST /api/tasks/claim`` → get next PENDING task
  2. **Execute** — run the skill logic (mock for now; plug in real skills later)
  3. **Submit** — ``POST /api/tasks/submit`` → trigger JSON Schema validation & gas billing
  4. **Heartbeat** — ``POST /api/workers/heartbeat`` every 15 s → keep-alive signal
"""

from __future__ import annotations

import json
import logging
import random
import sys
import time
from typing import Any

import requests

from src.worker.config import (
    CLAIM_ENDPOINT,
    GATEWAY_URL,
    HEARTBEAT_INTERVAL,
    HEARTBEAT_ENDPOINT,
    MAX_RETRIES,
    POLL_INTERVAL,
    SUBMIT_ENDPOINT,
    WORKER_ID,
)
from src.worker.utils.signer import sign_headers

# Dynamic skill bootstrap
from src.worker.bootstrap import execute_dynamic_skill as _execute_dynamic

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(f"worker.{WORKER_ID}")


# ── HTTP helpers ──────────────────────────────────────────────────────────────


def _signed_post(url: str, body: dict[str, Any] | None = None) -> requests.Response:
    """POST with HMAC-SHA256 signature headers."""
    headers = sign_headers(body, WORKER_ID)
    return requests.post(url, json=body, headers=headers, timeout=30)


def _signed_get(url: str) -> requests.Response:
    """GET with HMAC-SHA256 signature headers (for heartbeats with no body)."""
    headers = sign_headers(None, WORKER_ID)
    return requests.get(url, headers=headers, timeout=15)


# ── Heartbeat ─────────────────────────────────────────────────────────────────


def send_heartbeat() -> bool:
    """Send a keep-alive heartbeat to the gateway.

    The payload carries the worker's identity so the gateway can track
    ``last_seen`` per worker for liveness monitoring.

    Returns ``True`` on success.
    """
    try:
        resp = _signed_post(HEARTBEAT_ENDPOINT, {"worker_id": WORKER_ID})
        if resp.status_code == 200:
            return True
        logger.warning("heartbeat returned %s", resp.status_code)
    except requests.RequestException as exc:
        logger.warning("heartbeat failed: %s", exc)
    return False


# ── Task lifecycle ────────────────────────────────────────────────────────────


def claim_task() -> dict[str, Any] | None:
    """Poll the gateway for a PENDING task.

    Returns the task dict on success, or ``None`` when the queue is empty.
    """
    for attempt in range(MAX_RETRIES):
        try:
            resp = _signed_post(CLAIM_ENDPOINT, {"worker_id": WORKER_ID})
            if resp.status_code == 204:
                return None  # queue empty
            if resp.status_code == 200:
                return resp.json()
            logger.warning("claim attempt %d/%d: %s", attempt + 1, MAX_RETRIES, resp.status_code)
        except requests.RequestException as exc:
            logger.warning("claim attempt %d/%d error: %s", attempt + 1, MAX_RETRIES, exc)

        if attempt < MAX_RETRIES - 1:
            time.sleep(0.5 * (attempt + 1))

    return None


def execute_task(task: dict[str, Any]) -> dict[str, Any]:
    """Execute the claimed task.

    If the task carries a ``payload``, the worker uses the dynamic skill
    bootstrap — fetching ``logic.py`` from the gateway, loading it via
    ``importlib``, and calling ``execute(payload)``.

    Otherwise it falls back to mock execution (simulated work with a
    random delay).
    """
    task_id = task.get("task_id", "unknown")
    skill_id = task.get("skill_id", "")
    payload = task.get("payload")

    # ── Dynamic skill path ───────────────────────────────────────────────
    if payload is not None and skill_id:
        try:
            from src.worker.bootstrap import execute_dynamic_skill
            logger.info("bootstrap dynamic skill '%s' for task %s", skill_id, task_id)
            return execute_dynamic_skill(
                gateway_url=GATEWAY_URL,
                skill_id=skill_id,
                payload=payload,
                worker_id=WORKER_ID,
            )
        except Exception as exc:
            logger.warning(
                "dynamic skill '%s' failed for %s: %s — falling back to mock",
                skill_id, task_id, exc,
            )
            # Fall through to mock execution

    # ── Mock execution (legacy / static skills) ──────────────────────────
    asin = task.get("asin", "UNKNOWN-ASIN")
    compute_tier = task.get("compute_tier", 1)

    delay = random.uniform(0.1, 0.5) * compute_tier
    time.sleep(delay)

    logger.info(
        "executed (mock) task %s (tier=%s, asin=%s) in %.2fs",
        task_id, compute_tier, asin, delay,
    )

    return {
        "products": [{"asin": asin, "price": round(random.uniform(5.0, 50.0), 2)}],
        "total_found": random.randint(1, 5),
        "search_term": f"product-{asin}",
    }


def submit_result(task_id: str, result_data: dict[str, Any]) -> dict[str, Any] | None:
    """Submit the execution result for validation and settlement.

    Returns the gateway's response dict, or ``None`` on repeated failure.
    """
    for attempt in range(MAX_RETRIES):
        try:
            resp = _signed_post(SUBMIT_ENDPOINT, {
                "task_id": task_id,
                "worker_id": WORKER_ID,
                "result_data": result_data,
            })
            if resp.status_code == 200:
                return resp.json()
            logger.warning(
                "submit attempt %d/%d: %s — %s",
                attempt + 1, MAX_RETRIES, resp.status_code, resp.text[:200],
            )
        except requests.RequestException as exc:
            logger.warning(
                "submit attempt %d/%d error: %s",
                attempt + 1, MAX_RETRIES, exc,
            )

        if attempt < MAX_RETRIES - 1:
            time.sleep(1.0 * (attempt + 1))

    return None


# ── Main loop ─────────────────────────────────────────────────────────────────


def main() -> None:
    logger.info("starting worker loop → %s", CLAIM_ENDPOINT)
    tasks_completed = 0
    last_heartbeat = 0.0

    while True:
        now = time.time()

        # ── Heartbeat ────────────────────────────────────────────────────
        if now - last_heartbeat >= HEARTBEAT_INTERVAL:
            if send_heartbeat():
                last_heartbeat = now
            # Don't block the work loop on heartbeat failure

        # ── Claim ────────────────────────────────────────────────────────
        task = claim_task()
        if task is None:
            time.sleep(POLL_INTERVAL)
            continue

        logger.info("claimed task %s", task.get("task_id", "?"))

        # ── Execute ──────────────────────────────────────────────────────
        result_data = execute_task(task)

        # ── Submit ───────────────────────────────────────────────────────
        receipt = submit_result(task["task_id"], result_data)
        if receipt is not None:
            tasks_completed += 1
            outcome = receipt.get("outcome", "?")
            payout = receipt.get("developer_payout", 0.0)
            logger.info(
                "task %s → %s | payout=$%.2f | completed=%d",
                task["task_id"], outcome, payout, tasks_completed,
            )
        else:
            logger.error("task %s submit failed after %d retries", task["task_id"], MAX_RETRIES)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("shutting down (completed %d tasks)", tasks_completed)
        sys.exit(0)
