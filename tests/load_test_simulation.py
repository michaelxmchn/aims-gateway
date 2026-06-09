#!/usr/bin/env python3
"""
tests/load_test_simulation.py — Unattended multiprocessing load test.

Spins up 20 worker processes that claim and submit tasks through the
FastAPI Gateway Server with HMAC-SHA256 signed requests, simulating
a production DePIN workload.

Usage::

    python tests/load_test_simulation.py

The script starts the server, seeds test data, spawns workers, and
prints a summary — zero manual interaction required.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import multiprocessing
import os
import random
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.gateway.server import AIMS_SIGNING_SECRET, compute_signature

# ── Config ─────────────────────────────────────────────────────────────────

HOST = "127.0.0.1"
PORT = 8765
BASE_URL = f"http://{HOST}:{PORT}"
NUM_WORKERS = 20
TOTAL_TASKS = 100  # matches /api/admin/setup publish count
WORKER_TIMEOUT = 120  # seconds per worker before forced exit

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("loadtest")


# ── HTTP helpers with signature ────────────────────────────────────────────


def _signed_request(method: str, url: str, body: dict | None = None,
                    worker_id: str = "") -> tuple[int, dict | str]:
    """Make an HTTP request with HMAC-SHA256 signature headers.

    Returns ``(status_code, parsed_json_or_raw_text)``.
    """
    ts = str(int(time.time()))
    body_bytes = json.dumps(body).encode() if body else b""
    sig = compute_signature(body_bytes, ts, worker_id)

    headers = {
        "Content-Type": "application/json",
        "X-Signature": sig,
        "X-Timestamp": ts,
        "X-User-ID": worker_id,
    }
    req = urllib.request.Request(
        url, data=body_bytes if body else None, headers=headers, method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            ct = resp.headers.get("Content-Type", "")
            if "json" in ct:
                return resp.status, json.loads(raw)
            return resp.status, raw.decode()
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read())
        except Exception:
            detail = str(exc)
        return exc.code, detail


# ── Worker process ─────────────────────────────────────────────────────────


def worker_loop(worker_id: str, barrier: multiprocessing.Barrier) -> int:
    """Claim-and-submit loop until the broker runs dry.

    Returns the number of successfully completed tasks.
    """
    completed = 0
    retries = 0
    max_retries = 3

    # Wait for all workers to be spawned before hitting the server
    barrier.wait()

    while True:
        # ── Claim a task ──────────────────────────────────────────────
        status, data = _signed_request(
            "POST", f"{BASE_URL}/api/tasks/claim",
            body={"worker_id": worker_id},
            worker_id=worker_id,
        )

        if status == 204:
            # No pending tasks — either all done or not published yet
            if completed > 0 or retries > 5:
                break
            retries += 1
            time.sleep(0.2)
            continue

        if status != 200:
            retries += 1
            if retries > max_retries:
                logger.error("[%s] claim failed after %d retries: %s", worker_id, retries, data)
                break
            time.sleep(0.3 * retries)
            continue

        task_id = data.get("task_id", "unknown")
        retries = 0  # reset on success

        # ── Simulate execution ────────────────────────────────────────
        time.sleep(random.uniform(0.05, 0.2))

        # ── Submit result (matches amazon_scraper output_schema) ──────
        result_data = {
            "products": [{"asin": f"LOAD-ASIN-{task_id}", "price": 19.99}],
            "total_found": 1,
            "search_term": f"load-test-{task_id}",
        }
        status, submit_data = _signed_request(
            "POST", f"{BASE_URL}/api/tasks/submit",
            body={
                "task_id": task_id,
                "worker_id": worker_id,
                "result_data": result_data,
            },
            worker_id=worker_id,
        )

        if status == 200:
            completed += 1
        else:
            # Self-healing — log but keep going
            logger.warning(
                "[%s] submit %s failed (status=%d): %s",
                worker_id, task_id, status, submit_data,
            )

    return completed


# ── Main orchestration ──────────────────────────────────────────────────────


def main() -> int:
    print("=" * 60)
    print("  AIMS Load Test Simulation")
    print(f"  Workers: {NUM_WORKERS}   Tasks: {TOTAL_TASKS}")
    print("=" * 60)

    # ── 1. Start server ───────────────────────────────────────────────
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{repo_root}:{env.get('PYTHONPATH', '')}"
    server_proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "src.gateway.server:app",
            "--host", HOST,
            "--port", str(PORT),
            "--log-level", "warning",
        ],
        cwd=repo_root,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    print(f"\n  Server starting on {BASE_URL}  (pid={server_proc.pid}) ...")

    # Wait for the server to become responsive
    for attempt in range(30):
        try:
            with urllib.request.urlopen(f"{BASE_URL}/api/health", timeout=2):
                break
        except Exception:
            time.sleep(0.5)
    else:
        print("  FAILED: server did not start within 15 s")
        server_proc.kill()
        return 1
    print("  Server is ready.\n")

    # ── 2. Seed test data ─────────────────────────────────────────────
    try:
        req = urllib.request.Request(
            f"{BASE_URL}/api/admin/setup",
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            seed = json.loads(resp.read())
        print(f"  Seeded: {seed['tasks_published']} tasks, "
              f"user balance=${seed['user_balance']:.2f}")
        assert seed["tasks_published"] > 0, "No tasks published!"
    except Exception as exc:
        print(f"  FAILED: seed step — {exc}")
        # Debug: drain stderr from the server process
        try:
            out, err = server_proc.communicate(timeout=2)
            if err:
                print(f"  Server stderr:\n{err.decode()[:2000]}")
        except Exception:
            pass
        server_proc.kill()
        return 1

    # ── 3. Spawn workers ──────────────────────────────────────────────
    ctx = multiprocessing.get_context("fork")
    barrier = ctx.Barrier(NUM_WORKERS)
    workers: list[ctx.Process] = []
    results: list[ctx.Queue] = []

    for i in range(NUM_WORKERS):
        q = ctx.Queue()
        wid = f"load_worker_{i:02d}"
        p = ctx.Process(target=_worker_wrapper, args=(wid, barrier, q))
        workers.append(p)
        results.append(q)
        p.start()

    print(f"  Spawned {NUM_WORKERS} worker processes, waiting for completion ...\n")

    # ── 4. Wait for all workers ───────────────────────────────────────
    start_ts = time.time()
    for p in workers:
        p.join(timeout=WORKER_TIMEOUT)
    elapsed = time.time() - start_ts

    # Kill any stragglers
    for p in workers:
        if p.is_alive():
            p.terminate()

    # ── 5. Collect results ────────────────────────────────────────────
    total_completed = 0
    worker_breakdown: list[tuple[str, int]] = []
    for i, q in enumerate(results):
        count = q.get() if not q.empty() else -1
        wid = f"load_worker_{i:02d}"
        worker_breakdown.append((wid, count))
        if count > 0:
            total_completed += count

    # ── 6. Fetch server metrics ───────────────────────────────────────
    try:
        req = urllib.request.Request(f"{BASE_URL}/api/health")
        with urllib.request.urlopen(req, timeout=5) as resp:
            health = json.loads(resp.read())
    except Exception:
        health = {"error": "unreachable"}

    # ── 7. Summary ────────────────────────────────────────────────────
    print("=" * 60)
    print("  LOAD TEST SUMMARY")
    print("=" * 60)
    print(f"\n  Duration:           {elapsed:.2f} s")
    print(f"  Workers:            {NUM_WORKERS}")
    print(f"  Tasks published:    {TOTAL_TASKS}")
    print(f"  Tasks completed:    {total_completed}")
    print(f"  Throughput:         {total_completed / max(elapsed, 0.01):.1f} tasks/s")
    print(f"\n  --- Server Metrics ---")
    if "error" not in health:
        print(f"  Pending tasks:      {health.get('tasks_pending', '?')}")
        print(f"  Completed tasks:    {health.get('tasks_completed', '?')}")
        print(f"  Workers registered: {health.get('workers_registered', '?')}")
        print(f"  Treasury USDT:      ${health.get('treasury_usdt', 0):.2f}")
    else:
        print(f"  Health check: {health['error']}")

    print(f"\n  --- Worker Breakdown ---")
    for wid, count in worker_breakdown:
        if count > 0:
            print(f"  {wid}: {count} tasks")

    success_rate = (total_completed / max(TOTAL_TASKS, 1)) * 100
    print(f"\n  Success rate:       {success_rate:.1f}%")
    print(f"  Status:            {'PASSED ✓' if total_completed > 0 else 'FAILED ⚠'}")

    # ── 8. Cleanup ────────────────────────────────────────────────────
    server_proc.terminate()
    server_proc.wait(timeout=10)

    print(f"\n{'=' * 60}")
    return 0 if total_completed > 0 else 1


def _worker_wrapper(wid: str, barrier: multiprocessing.Barrier, queue: multiprocessing.Queue) -> None:
    """Run the worker loop and put the result count on *queue*."""
    count = worker_loop(wid, barrier)
    queue.put(count)


if __name__ == "__main__":
    sys.exit(main())
