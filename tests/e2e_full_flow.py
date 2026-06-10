#!/usr/bin/env python3
"""
tests/e2e_full_flow.py — Production-Level E2E Integration Test.

Spins up 10 concurrent HMAC-signed worker threads against the AIMS Gateway,
with optional SOCKS5 proxy rotation for multi-egress simulation.

Usage::

    # Local dev (starts its own server)
    python tests/e2e_full_flow.py

    # Against production Fly.io gateway
    AIMS_GATEWAY_URL=https://api.aimsgateway.com \\
    AIMS_SIGNING_SECRET=your-secret \\
    python tests/e2e_full_flow.py

    # With SOCKS5 proxy rotation (3 proxies on different ports)
    AIMS_PROXY_PORTS=7890,7891,7892 \\
    python tests/e2e_full_flow.py
"""

from __future__ import annotations

import json
import logging
import os
import random
import signal
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("e2e")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.worker.utils.signer import sign_headers

# ── Config ─────────────────────────────────────────────────────────────────

LOCAL_PORT = 9876
"""Port for the local uvicorn instance (avoid conflicts with 8765)."""

GATEWAY_URL: str = os.getenv(
    "AIMS_GATEWAY_URL",
    f"http://127.0.0.1:{LOCAL_PORT}",  # local by default; override for production
)
CLAIM_URL = f"{GATEWAY_URL}/api/tasks/claim"
SUBMIT_URL = f"{GATEWAY_URL}/api/tasks/submit"
HEALTH_URL = f"{GATEWAY_URL}/api/health"
SETUP_URL = f"{GATEWAY_URL}/api/admin/setup"

NUM_WORKERS = 10
"""Number of concurrent worker threads."""

RUN_DURATION = 60
"""Test duration in seconds."""

# Proxy ports — set AIMS_PROXY_PORTS to e.g. "7890,7891,7892" to enable
PROXY_PORTS: list[int] = []
_proxy_ports_raw = os.getenv("AIMS_PROXY_PORTS", "")
if _proxy_ports_raw:
    PROXY_PORTS = [int(p.strip()) for p in _proxy_ports_raw.split(",") if p.strip()]
USE_PROXIES = len(PROXY_PORTS) > 0

if USE_PROXIES:
    try:
        import socks  # noqa: F401 — verify PySocks is installed
    except ImportError:
        print(
            "  ERROR: AIMS_PROXY_PORTS is set but PySocks is not installed.\n"
            "  Install with: pip install pysocks"
        )
        sys.exit(1)


# ── HTTP helpers ───────────────────────────────────────────────────────────


def _detect_egress_ip(session: object, proxy_label: str = "direct") -> str:
    """Detect the egress IP seen by an external service.

    Tries ``https://api.ipify.org?format=json`` (Cloudflare-resolved),
    falls back to ``https://httpbin.org/ip``, then ``https://ifconfig.me``.
    """
    for url in (
        "https://api.ipify.org?format=json",
        "https://httpbin.org/ip",
        "https://ifconfig.me",
    ):
        try:
            resp = session.get(url, timeout=10)
            if resp.status_code == 200:
                text = resp.text.strip()
                # Try JSON parse
                try:
                    data = resp.json()
                    for key in ("ip", "origin"):
                        if key in data:
                            return str(data[key])
                except Exception:
                    pass
                # Plain-text response (ifconfig.me)
                if text and not text.startswith("<"):
                    return text
        except Exception:
            continue
    return f"unknown ({proxy_label})"


def _pick_proxy() -> tuple[str, str] | None:
    """Pick a random proxy from the configured ports.

    Returns ``(scheme, url)`` tuple or ``None`` if proxies are disabled.
    """
    if not USE_PROXIES or not PROXY_PORTS:
        return None
    port = random.choice(PROXY_PORTS)
    return ("socks5", f"socks5://127.0.0.1:{port}")


def _signed_post(
    url: str,
    body: dict,
    worker_id: str,
    proxy: tuple[str, str] | None = None,
) -> tuple[int, dict | str]:
    """POST with HMAC-SHA256 signature, optional SOCKS5 proxy.

    Returns ``(status_code, parsed_json_or_error_string)``.
    """
    import requests as req

    headers = sign_headers(body, worker_id)
    session = req.Session()

    if proxy:
        scheme, proxy_url = proxy
        session.proxies = {
            "http": proxy_url,
            "https": proxy_url,
        }

    try:
        resp = session.post(url, json=body, headers=headers, timeout=30)
        ct = resp.headers.get("Content-Type", "")
        if "json" in ct:
            return resp.status_code, resp.json()
        return resp.status_code, resp.text
    except req.exceptions.RequestException as exc:
        return 0, str(exc)
    finally:
        session.close()


# ── Worker thread ──────────────────────────────────────────────────────────


def worker_loop(worker_id: str, proxy: tuple[str, str] | None) -> dict:
    """Run the claim → execute → submit loop for *worker_id*.

    Returns a result dict with counts and diagnostics.
    """
    result = {
        "worker_id": worker_id,
        "claimed": 0,
        "submitted": 0,
        "failed": 0,
        "errors": [],
        "egress_ip": "unknown",
    }

    # Detect egress IP
    import requests as req

    session = req.Session()
    if proxy:
        session.proxies = {"http": proxy[1], "https": proxy[1]}
    result["egress_ip"] = _detect_egress_ip(session, proxy[1] if proxy else "direct")
    session.close()

    deadline = time.time() + RUN_DURATION

    while time.time() < deadline:
        # ── 1. Claim ───────────────────────────────────────────────────
        status, data = _signed_post(
            CLAIM_URL,
            body={"worker_id": worker_id},
            worker_id=worker_id,
            proxy=proxy,
        )

        if status == 204:
            # No pending tasks — wait and retry
            time.sleep(0.5)
            continue

        if status != 200:
            err = data.get("detail") if isinstance(data, dict) else str(data)
            result["errors"].append(f"claim failed (HTTP {status}): {err}")
            result["failed"] += 1
            time.sleep(1.0)
            continue

        task_id = data.get("task_id", "unknown")
        result["claimed"] += 1

        # ── 2. Simulate Browser Fingerprint task (2s) ──────────────────
        time.sleep(2.0)

        result_data = {
            "products": [
                {
                    "asin": f"E2E-ASIN-{task_id}",
                    "price": round(random.uniform(10.0, 200.0), 2),
                },
            ],
            "total_found": random.randint(1, 15),
            "search_term": f"e2e-test-{worker_id}-{task_id}",
        }

        # ── 3. Submit ──────────────────────────────────────────────────
        submit_body = {
            "task_id": task_id,
            "worker_id": worker_id,
            "result_data": result_data,
        }
        sub_status, sub_data = _signed_post(
            SUBMIT_URL,
            body=submit_body,
            worker_id=worker_id,
            proxy=proxy,
        )

        if sub_status == 200:
            result["submitted"] += 1
            outcome = sub_data.get("outcome", "COMPLETED") if isinstance(sub_data, dict) else "?"
            logger.info(
                "[%s] task=%-24s outcome=%-10s gas=$%.4f  payout=$%.4f  refund=$%.2f",
                worker_id, task_id, outcome,
                sub_data.get("gas_cost", 0) if isinstance(sub_data, dict) else 0,
                sub_data.get("developer_payout", 0) if isinstance(sub_data, dict) else 0,
                sub_data.get("unused_refund", 0) if isinstance(sub_data, dict) else 0,
            )
        else:
            detail = ""
            if isinstance(sub_data, dict):
                detail = json.dumps(sub_data, ensure_ascii=False)
            else:
                detail = str(sub_data)
            result["errors"].append(f"submit {task_id} failed (HTTP {sub_status}): {detail}")
            result["failed"] += 1

    return result


# ── Orchestration ──────────────────────────────────────────────────────────


def start_local_server() -> subprocess.Popen | None:
    """Start a local uvicorn server if we're not targeting production."""
    local_url = f"http://127.0.0.1:{LOCAL_PORT}"
    if GATEWAY_URL != local_url:
        print(f"  Targeting production gateway: {GATEWAY_URL}")
        return None

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{repo_root}:{env.get('PYTHONPATH', '')}"
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "src.gateway.server:app",
            "--host", "127.0.0.1",
            "--port", str(LOCAL_PORT),
            "--log-level", "warning",
        ],
        cwd=repo_root,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    print(f"  Local server starting (pid={proc.pid}) ...")

    # Wait — and verify the response contains gateway-specific fields
    for attempt in range(30):
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=2) as resp:
                body = json.loads(resp.read())
                if "tasks_pending" in body:
                    break
        except Exception:
            time.sleep(0.5)
    else:
        # Check stderr for bind errors
        try:
            _, err = proc.communicate(timeout=3)
            if err:
                print(f"  Server stderr:\n{err.decode()[:1000]}")
        except Exception:
            pass
        print("  FAILED: server health check did not return gateway fields")
        proc.kill()
        return None
    print("  Server is ready.\n")
    return proc


def seed_test_data() -> bool:
    """Call /api/admin/setup to publish test tasks."""
    try:
        req = urllib.request.Request(SETUP_URL, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            seed = json.loads(resp.read())
        print(f"  Seeded: {seed['tasks_published']} tasks, "
              f"user balance=${seed['user_balance']:.2f}")
        return seed["tasks_published"] > 0
    except Exception as exc:
        print(f"  FAILED: seed step — {exc}")
        return False


def print_env_banner() -> None:
    """Print a colourful configuration banner."""
    print("=" * 72)
    print("  AIMS E2E Full Flow Test")
    print(f"  Started:  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"  Gateway:  {GATEWAY_URL}")
    print(f"  Workers:  {NUM_WORKERS}")
    print(f"  Duration: {RUN_DURATION} s")
    if USE_PROXIES:
        print(f"  Proxies:  SOCKS5 on ports {PROXY_PORTS}")
    else:
        print("  Proxies:  none (direct connection)")
    print(f"  Signing:  HMAC-SHA256 (env fallback: "
          f"{'production' if 'AIMS_SIGNING_SECRET' in os.environ else 'local mock'})")
    print("=" * 72)


def print_results(
    results: list[dict],
    start_time: float,
    end_time: float,
) -> None:
    """Print a detailed summary table."""
    elapsed = end_time - start_time
    total_claimed = sum(r["claimed"] for r in results)
    total_submitted = sum(r["submitted"] for r in results)
    total_failed = sum(r["failed"] for r in results)

    print("\n" + "=" * 72)
    print("  E2E TEST RESULTS")
    print("=" * 72)
    print(f"\n  Duration:           {elapsed:.2f} s")
    print(f"  Workers:            {NUM_WORKERS}")
    print(f"  Tasks claimed:      {total_claimed}")
    print(f"  Tasks submitted:    {total_submitted}")
    print(f"  Tasks failed:       {total_failed}")
    print(f"  Throughput:         {total_submitted / max(elapsed, 0.01):.1f} tasks/s")
    print(f"  Avg per worker:     {total_submitted / max(NUM_WORKERS, 1):.1f} tasks")

    print(f"\n  {'Worker':<20s}  {'Egress IP':<20s}  {'Claimed':>8s}  {'Done':>6s}  {'Failed':>6s}")
    print(f"  {'─' * 64}")
    for r in sorted(results, key=lambda x: x["worker_id"]):
        print(f"  {r['worker_id']:<20s}  {r['egress_ip']:<20s}  "
              f"{r['claimed']:>8d}  {r['submitted']:>6d}  {r['failed']:>6d}")

    # Error summary
    all_errors = [e for r in results for e in r["errors"]]
    if all_errors:
        print(f"\n  ── Error Log ({len(all_errors)} total) ──")
        for err in all_errors[:20]:  # cap display
            print(f"    ⚠ {err}")
        if len(all_errors) > 20:
            print(f"    ... and {len(all_errors) - 20} more errors")

    # Fetch server health metrics
    try:
        import requests
        resp = requests.get(HEALTH_URL, timeout=10)
        if resp.status_code == 200:
            h = resp.json()
            print(f"\n  ── Server Health ──")
            print(f"    Pending:    {h.get('tasks_pending', '?')}")
            print(f"    Completed:  {h.get('tasks_completed', '?')}")
            print(f"    Succeeded:  {h.get('tasks_succeeded', '?')}")
            print(f"    Registered: {h.get('workers_registered', '?')}")
            print(f"    Active:     {h.get('workers_active', '?')}")
            print(f"    Treasury:   ${h.get('treasury_usdt', 0):.2f}")
    except Exception as exc:
        print(f"\n  Health check unavailable: {exc}")

    success_rate = (total_submitted / max(total_submitted + total_failed, 1)) * 100
    qual = "PASSED ✓" if success_rate > 80 else "DEGRADED ⚠" if success_rate > 0 else "FAILED ✗"
    print(f"\n  Success rate:       {success_rate:.1f}%")
    print(f"  Overall:            {qual}")
    print(f"{'=' * 72}\n")


def main() -> int:
    print_env_banner()

    # ── 1. Start server (if local) ─────────────────────────────────────
    server_proc = start_local_server()
    if GATEWAY_URL == f"http://127.0.0.1:{LOCAL_PORT}" and server_proc is None:
        return 1

    # ── 2. Seed test data (only for local) ─────────────────────────────
    if GATEWAY_URL == f"http://127.0.0.1:{LOCAL_PORT}":
        if not seed_test_data():
            if server_proc:
                server_proc.terminate()
                server_proc.wait(timeout=10)
            return 1
    else:
        print("  Skipping seed (production mode) — ensure tasks exist on gateway.")

    # ── 3. Assign proxies to workers ───────────────────────────────────
    worker_configs: list[tuple[str, tuple[str, str] | None]] = []
    for i in range(NUM_WORKERS):
        wid = f"e2e-worker-{i:02d}"
        proxy = _pick_proxy() if USE_PROXIES else None
        worker_configs.append((wid, proxy))

    # ── 4. Launch concurrent workers ──────────────────────────────────
    print(f"\n  Launching {NUM_WORKERS} workers for {RUN_DURATION}s ...\n")
    start_time = time.time()

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
        futures = {
            executor.submit(worker_loop, wid, proxy): wid
            for wid, proxy in worker_configs
        }
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                wid = futures[future]
                logger.error("[%s] worker crashed: %s", wid, exc)
                results.append({
                    "worker_id": wid,
                    "claimed": 0,
                    "submitted": 0,
                    "failed": 0,
                    "errors": [str(exc)],
                    "egress_ip": "crashed",
                })

    end_time = time.time()

    # ── 5. Print results ──────────────────────────────────────────────
    print_results(results, start_time, end_time)

    # ── 6. Cleanup ────────────────────────────────────────────────────
    # Drain server stderr to avoid PIPE deadlock
    if server_proc and server_proc.stderr:
        try:
            server_proc.stderr.read()
        except Exception:
            pass
    if server_proc:
        server_proc.terminate()
        try:
            server_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server_proc.kill()

    total_submitted = sum(r["submitted"] for r in results)
    return 0 if total_submitted > 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n  Interrupted by user.")
        sys.exit(130)
