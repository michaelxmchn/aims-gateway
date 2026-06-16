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
    compute_tier = task.get("compute_tier", 1)
    search_term = (payload.get("search_term", "") if isinstance(payload, dict) else "")

    delay = random.uniform(0.1, 0.5) * compute_tier
    time.sleep(delay)

    logger.info(
        "executed (mock) task %s (tier=%s, search='%s') in %.2fs",
        task_id, compute_tier, search_term, delay,
    )

    # Realistic Amazon-style mock data — uses search_term context
    all_products = {
        "electronics": [
            ("B09G9D7K7P", "Wireless Bluetooth Headphones Noise Cancelling Over-Ear", 59.99, 4.6),
            ("B0B1V7K9Z3", "USB-C Fast Charging Cable 6ft 3-Pack Nylon Braided", 12.99, 4.8),
            ("B0C1H2J3K4", "Portable External SSD 1TB USB 3.2 Gen 2 Up to 1050MB/s", 89.99, 4.7),
            ("B0D2F3G4H5", "Smart Home WiFi Router AX6000 Dual Band 6-Stream", 129.99, 4.5),
            ("B0E3R4T5Y6", "Mechanical Gaming Keyboard RGB Hot-Swappable Switch", 79.99, 4.6),
            ("B0F4G5H6J7", "27英寸 4K IPS 显示器 USB-C 90W 供电 HDR400", 349.99, 4.7),
            ("B0G5H6J7K8", "100W GaN 充电器 4口 快速充电站 兼容全设备", 45.99, 4.8),
        ],
        "wholesale": [
            ("B0K1L2M3N4", "Wholesale Lot 50x Bluetooth 5.3 Earbuds Bulk Packaging OEM", 299.99, 4.3),
            ("B0L2M3N4O5", "Bulk USB-C to Lightning Cable 100-Pack Wholesale White", 189.99, 4.5),
            ("B0M3N4O5P6", "Wholesale Portable Power Bank 10000mAh 20-Pack Lot", 459.99, 4.4),
            ("B0N4O5P6Q7", "Bulk Order Mini Wireless Speaker 50-Pack OEM White Label", 599.99, 4.2),
            ("B0O5P6Q7R8", "Wholesale Smart Plug WiFi 4-Pack 100 Units Lot", 1299.99, 4.6),
            ("B0P6Q7R8S9", "Bulk Mechanical Keyboard Switch Set 500-Pack OEM",
             249.99, 4.5),
        ],
        "components": [
            ("B0Q7R8S9T1", "Resistor Kit 0603 0805 1206 SMD 5000-Piece Assortment", 24.99, 4.7),
            ("B0R8S9T1U2", "Raspberry Pi 5 8GB Single Board Computer", 79.99, 4.8),
            ("B0S9T1U2V3", "Arduino Mega 2560 Rev3 Development Board Official", 48.99, 4.6),
            ("B0T1U2V3W4", "ESP32 WiFi BLE Development Board 10-Pack", 89.99, 4.7),
            ("B0U2V3W4X5", "FPGA Development Board Artix-7 XC7A35T", 169.99, 4.4),
            ("B0V3W4X5Y6", "Raspberry Pi 5 Active Cooler Official Aluminum Heatsink",
             5.99, 4.5),
        ],
    }

    # Select product pool based on search term
    term_lower = search_term.lower()
    if any(w in term_lower for w in ["wholesale", "bulk", "lot", "oem", "bulk order"]):
        pool = all_products["wholesale"] + all_products["electronics"][:3]
    elif any(w in term_lower for w in ["component", "board", "chip", "fpga", "raspberry", "arduino"]):
        pool = all_products["components"] + all_products["electronics"][2:5]
    else:
        pool = all_products["electronics"]

    product_count = min(len(pool), random.randint(3, len(pool)))
    sampled = random.sample(pool, product_count)
    products = []
    for asin, title, price, rating in sampled:
        products.append({
            "asin": asin,
            "title": title,
            "price": price,
            "rating": rating,
            "review_count": random.randint(50, 15000),
            "in_stock": True,
            "fulfilled_by_amazon": True,
            "shipping_info": "FREE Prime delivery",
        })

    result = {
        "products": products,
        "total_found": product_count,
        "search_term": search_term,
        "page": 1,
        "results_per_page": 20,
    }

    # Pass through canary watermark from payload (anti-piracy)
    if isinstance(payload, dict) and "_canary_token" in payload:
        result["_canary_token"] = payload["_canary_token"]

    return result


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
