"""Stress Test — High-Concurrency Ledger Audit.

Simulates 10 concurrent users x 5 rapid-fire skill calls = 50
transactions hammering the MockLedger simultaneously. Asserts that
no USDT is created or destroyed — total system wealth must be
identical before and after the chaos.
"""

from __future__ import annotations

import logging
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, ".")

from src.ledger.mock_counter import MockLedger
from src.skills.manifest import SkillManifest
from src.runtime.sandbox import WorkflowEngine, resolve_impl

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("stress_test")

# ── Constants ───────────────────────────────────────────────────────────

NUM_USERS = 10
ITERATIONS_PER_USER = 5
MAX_BUDGET_PER_CALL = 1.00
DEV_PREMIUM = 2.0
INITIAL_SEED_PER_USER = 20.0
DEV_ID = "dev_alice"

# ── Build shared dependencies ──────────────────────────────────────────

ledger = MockLedger()
engine = WorkflowEngine(resolve_impl)

amazon_manifest = SkillManifest(
    name="amazon_scraper",
    description="Scrape Amazon listings",
    input_schema={"type": "object", "properties": {}, "required": []},
    output_schema={"type": "object", "properties": {}, "required": []},
    version="1.0.0",
    author="aims_seed",
    price_points=DEV_PREMIUM,
    tags=["scraping"],
)

# ── Seed users ──────────────────────────────────────────────────────────

print("=" * 72)
print("  STRESS TEST — Concurrent Ledger Audit")
print("=" * 72)
print(f"\n  Seeding {NUM_USERS} users with ${INITIAL_SEED_PER_USER:.2f} USDT each ...")
for i in range(NUM_USERS):
    ledger.seed_usdt(f"user_{i:04d}", INITIAL_SEED_PER_USER)
    ledger.seed_usdt(DEV_ID, 0.0)  # ensure dev address exists in balances

initial_wealth = ledger.total_system_wealth
print(f"  Initial total system wealth: ${initial_wealth:.2f} USDT\n")

# ── Shared counters (thread-safe via list append + final sum) ──────────

_stats_lock = __import__("threading").Lock()
stats = {"success": 0, "failure": 0, "escrow_denied": 0, "total_tax": 0.0}


def user_workflow(uid: str, iteration: int) -> dict:
    """Single user iteration: hold -> execute -> release."""
    result = {"success": False, "tax": 0.0}

    # Each call gets its own random extra jitter for chaotic timing
    extra_jitter = random.uniform(0.0, 0.3)

    hold = ledger.create_escrow_hold(uid, MAX_BUDGET_PER_CALL)
    if hold is None:
        with _stats_lock:
            stats["escrow_denied"] += 1
        return result

    # Execute with extra thread-level jitter
    time.sleep(extra_jitter)
    receipt = engine.execute(amazon_manifest, {"search_term": "stress test", "max_results": 1})

    detail = ledger.release_escrow_dynamic(
        hold.escrow_id,
        user_id=uid,
        developer_id=DEV_ID,
        execution_time=receipt.execution_time,
        developer_premium=DEV_PREMIUM,
        success=receipt.status == "SUCCESS",
    )

    if detail is not None and detail.outcome == "COMPLETED":
        result["success"] = True
        result["tax"] = detail.platform_tax
        with _stats_lock:
            stats["success"] += 1
            stats["total_tax"] += detail.platform_tax
    elif detail is not None and detail.outcome == "REFUNDED":
        with _stats_lock:
            stats["failure"] += 1
    else:
        with _stats_lock:
            stats["failure"] += 1

    return result


# ── Fire 50 concurrent transactions ────────────────────────────────────

print(f"  Launching {NUM_USERS} concurrent users x {ITERATIONS_PER_USER} calls ...")
print(f"  Total transactions: {NUM_USERS * ITERATIONS_PER_USER}")
print(f"  { '-' * 60 }")

wall_start = time.time()

with ThreadPoolExecutor(max_workers=NUM_USERS) as executor:
    futures = []
    for u in range(NUM_USERS):
        uid = f"user_{u:04d}"
        for i in range(ITERATIONS_PER_USER):
            futures.append(executor.submit(user_workflow, uid, i))

    # Wait for all to complete
    done = 0
    for f in as_completed(futures):
        done += 1
    elapsed = time.time() - wall_start

print(f"  All {done} transactions completed in {elapsed:.2f}s")

# ── Audit ───────────────────────────────────────────────────────────────

final_wealth = ledger.total_system_wealth
wealth_diff = round(final_wealth - initial_wealth, 6)
wealth_ok = abs(wealth_diff) < 0.0001

print(f"\n  {'─' * 60}")
print(f"  {'RESULTS':^60}")
print(f"  {'─' * 60}")
print(f"  {'Total transactions:':32s} {done}")
print(f"  {'Successful clearings:':32s} {stats['success']}")
print(f"  {'Failed (refunded):':32s} {stats['failure']}")
print(f"  {'Escrow denied (insufficient):':32s} {stats['escrow_denied']}")
print(f"  {'Total platform tax collected:':32s} ${stats['total_tax']:.4f} USDT")
print(f"  {'Elapsed time:':32s} {elapsed:.2f}s")
print(f"  {'─' * 60}")
print(f"  {'Initial system wealth:':32s} ${initial_wealth:.2f} USDT")
print(f"  {'Final system wealth:':32s} ${final_wealth:.2f} USDT")
print(f"  {'Difference:':32s} ${wealth_diff:+.6f} USDT")
print(f"  {'─' * 60}")

if wealth_ok:
    print(f"  >>> WEALTH AUDIT: PASSED ✓  (no tokens lost or created)")
    exit_code = 0
else:
    print(f"  >>> WEALTH AUDIT: FAILED ⚠  LEDGER DEFICIT/LEAK DETECTED!")
    print(f"  >>> Initial=${initial_wealth:.2f}  Final=${final_wealth:.2f}  "
          f"Diff=${wealth_diff:.6f}")
    exit_code = 1

print(f"  {'─' * 60}")
sys.exit(exit_code)
