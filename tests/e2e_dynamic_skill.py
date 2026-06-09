#!/usr/bin/env python3
"""E2E smoke test for the dynamic skill plugin system.

Tests the full lifecycle:
  1. Start gateway server
  2. Upload a zip skill (hello_world)
  3. Call /api/run to enqueue a dynamic task
  4. Worker claims, bootstraps, executes, and submits
  5. Poll status → verify correct output
"""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import time
from typing import Any

# Ensure the project root is on sys.path for bootstrap imports
_PROJECT_ROOT = "/home/michael/web3-community"
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
logger = logging.getLogger("e2e_dynamic")

GATEWAY_URL = os.getenv("AIMS_GATEWAY_URL", "http://localhost:9876")
SIGNING_SECRET = os.getenv("AIMS_SIGNING_SECRET", "AIMS_MOCK_SECRET_2026")
WORKER_ID = "e2e-dynamic-worker"

HEARTBEAT_URL = f"{GATEWAY_URL}/api/workers/heartbeat"
CLAIM_URL = f"{GATEWAY_URL}/api/tasks/claim"
SUBMIT_URL = f"{GATEWAY_URL}/api/tasks/submit"
UPLOAD_URL = f"{GATEWAY_URL}/api/skills/upload"
RUN_URL = f"{GATEWAY_URL}/api/run"
HEALTH_URL = f"{GATEWAY_URL}/api/health"
SETUP_URL = f"{GATEWAY_URL}/api/admin/setup"

ZIP_PATH = "/tmp/hello_world.zip"
USER_ID = "e2e_dynamic_user"


def _sig_headers(body: dict | None, uid: str) -> dict:
    import hashlib, hmac, time as tmod
    ts = str(int(tmod.time()))
    body_bytes = json.dumps(body).encode() if body else b""
    msg = body_bytes + b"|" + ts.encode() + b"|" + uid.encode()
    sig = hmac.new(SIGNING_SECRET.encode(), msg, hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/json" if body else "",
        "X-Signature": sig,
        "X-Timestamp": ts,
        "X-User-ID": uid,
    }


def sig_post(url: str, body: dict | None, uid: str = WORKER_ID) -> requests.Response:
    return requests.post(url, json=body, headers=_sig_headers(body, uid), timeout=15)


def sig_get(url: str, uid: str = WORKER_ID) -> requests.Response:
    return requests.get(url, headers=_sig_headers(None, uid), timeout=15)


def wait_for_health(timeout: int = 15) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(HEALTH_URL, timeout=3)
            if r.status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(1)
    return False


# ── 1. Start server (if running locally) ─────────────────────────────────

server_proc: subprocess.Popen | None = None
if "localhost" in GATEWAY_URL or "127.0.0.1" in GATEWAY_URL:
    port = GATEWAY_URL.split(":")[-1]
    logger.info("Starting gateway server on port %s ...", port)
    env = os.environ.copy()
    env.setdefault("AIMS_SIGNING_SECRET", SIGNING_SECRET)
    server_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.gateway.server:app",
         "--host", "0.0.0.0", "--port", port],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if not wait_for_health():
        logger.error("Server failed to start")
        server_proc.kill()
        sys.exit(1)
    logger.info("Server is healthy")
else:
    logger.info("Using remote gateway: %s", GATEWAY_URL)

try:
    # ── 2. Seed test data ─────────────────────────────────────────────────
    logger.info("Seeding test data via admin/setup ...")
    r = requests.post(SETUP_URL, timeout=15)
    r.raise_for_status()
    setup = r.json()
    logger.info("Setup: %s", setup)

    # Seed the user balance for /api/run escrow
    # (admin/setup seeds 'loadtest_user', we need our own)
    ledger_rpc = f"{GATEWAY_URL}/api/admin/setup"
    # Just re-use the admin-setup user for simplicity
    test_user = "loadtest_user"

    # ── 3. Upload skill ───────────────────────────────────────────────────
    logger.info("Uploading hello_world skill ...")
    with open(ZIP_PATH, "rb") as f:
        zip_bytes = f.read()
    headers = _sig_headers(None, WORKER_ID)
    headers.pop("Content-Type", None)  # multipart doesn't use JSON content-type
    r = requests.post(
        UPLOAD_URL,
        files={"zip_file": ("hello_world.zip", zip_bytes, "application/zip")},
        headers=headers,
        timeout=15,
    )
    assert r.status_code == 200, f"Upload failed: {r.status_code} {r.text}"
    upload = r.json()
    logger.info("Upload result: %s", upload)
    assert upload["skill_id"] == "hello_world"
    assert upload["version"] == "1.0.0"

    # ── 4. Call /api/run ──────────────────────────────────────────────────
    logger.info("Enqueuing dynamic task via /api/run ...")
    r = sig_post(RUN_URL, {
        "skill_id": "hello_world",
        "params": {"name": "AIMS"},
        "user_id": test_user,
        "developer_premium": 0.01,
        "max_budget": 2.0,
        "compute_tier": 1,
    }, uid=test_user)
    assert r.status_code == 200, f"/api/run failed: {r.status_code} {r.text}"
    run_resp = r.json()
    task_id = run_resp["task_id"]
    logger.info("Task created: %s", task_id)

    # ── 5. Worker heartbeat ───────────────────────────────────────────────
    r = sig_post(HEARTBEAT_URL, {"worker_id": WORKER_ID})
    assert r.status_code == 200, f"Heartbeat failed: {r.text}"

    # ── 6. Worker claims the correct task ────────────────────────────────
    logger.info("Worker claiming (draining pre-seeded tasks) ...")
    task = None
    for _ in range(200):
        r = sig_post(CLAIM_URL, {"worker_id": WORKER_ID})
        if r.status_code == 204:
            logger.warning("Queue empty before finding our task!")
            break
        assert r.status_code == 200, f"Claim failed: {r.status_code} {r.text}"
        t = r.json()
        if t["task_id"] == task_id:
            task = t
            break
        # Drain this pre-seeded task by submitting a mock result
        logger.info("Draining pre-seeded %s ...", t["task_id"])
        sig_post(SUBMIT_URL, {
            "task_id": t["task_id"],
            "worker_id": WORKER_ID,
            "result_data": {"asin": t.get("asin", "?"), "price": 10.0},
        })

    assert task is not None, f"Never found our task {task_id}"
    assert task["payload"] == {"name": "AIMS"}, f"Wrong payload: {task['payload']}"
    logger.info("Claimed task with payload: %s", task["payload"])

    # ── 7. Worker executes via bootstrap ──────────────────────────────────
    from src.worker.bootstrap import execute_dynamic_skill

    logger.info("Executing dynamic skill ...")
    result = execute_dynamic_skill(
        gateway_url=GATEWAY_URL,
        skill_id="hello_world",
        payload={"name": "AIMS"},
        worker_id=WORKER_ID,
    )
    logger.info("Execution result: %s", result)
    assert result == {"greeting": "Hello, AIMS!", "length": 12}

    # ── 8. Worker submits result ──────────────────────────────────────────
    logger.info("Submitting result ...")
    r = sig_post(SUBMIT_URL, {
        "task_id": task_id,
        "worker_id": WORKER_ID,
        "result_data": result,
    })
    assert r.status_code == 200, f"Submit failed: {r.status_code} {r.text}"
    submit_resp = r.json()
    logger.info("Submit receipt: %s", submit_resp)
    assert submit_resp["outcome"] == "COMPLETED", f"Unexpected outcome: {submit_resp}"

    # ── 9. Poll status ────────────────────────────────────────────────────
    r = sig_get(f"{GATEWAY_URL}/api/tasks/{task_id}/status")
    assert r.status_code == 200, f"Status poll failed: {r.status_code}"
    status = r.json()
    logger.info("Final status: %s", status)
    assert status["status"] == "SUCCESS", f"Task not SUCCESS: {status}"
    assert status["outcome"] == "COMPLETED"

    logger.info("=" * 50)
    logger.info("ALL CHECKS PASSED  ✅")
    logger.info("=" * 50)

finally:
    if server_proc:
        logger.info("Shutting down server ...")
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_proc.kill()
