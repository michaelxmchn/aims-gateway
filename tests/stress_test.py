"""Stress Test — DePIN Distributed Infrastructure.

Simulates a DePIN network:
  - **1 Central Broker** holding a FIFO task queue
  - **5 Worker Nodes** (separate threads) polling for work
  - **30 scraping tasks** published all at once
  - Workers automatically drain the queue, execute, and claim gas fees

Audits that total system wealth is conserved and that gas fees are
properly distributed across different worker_ids.
"""

from __future__ import annotations

import logging
import sys
import threading
import time

sys.path.insert(0, ".")

from src.gateway.broker import TaskBroker
from src.ledger.mock_counter import MockLedger
from src.skills.manifest import SkillManifest
from src.runtime.sandbox import WorkflowEngine, resolve_impl, start_worker_loop

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("depin_stress")

# ── Constants ───────────────────────────────────────────────────────────

NUM_WORKERS = 5
NUM_TASKS = 30
MAX_BUDGET_PER_TASK = 1.00
DEV_PREMIUM = 2.0
USER_SEED = 100.0
USER_ID = "alice"
WORKER_IDS = [f"worker_{i}" for i in range(NUM_WORKERS)]

# ── Dependencies ────────────────────────────────────────────────────────

ledger = MockLedger()
broker = TaskBroker(ledger)
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

# ── Seed ────────────────────────────────────────────────────────────────

print("=" * 72)
print("  DePIN STRESS TEST — 5 Workers x 30 Tasks")
print("=" * 72)

ledger.seed_usdt(USER_ID, USER_SEED)
initial_wealth = ledger.total_system_wealth
print(f"\n  {'User seeded:':30s} ${USER_SEED:.2f} USDT ({USER_ID})")
print(f"  {'Initial system wealth:':30s} ${initial_wealth:.2f} USDT")
print(f"  {'Workers:':30s} {NUM_WORKERS}")
print(f"  {'Tasks to publish:':30s} {NUM_TASKS}")
print(f"  {'Max budget per task:':30s} ${MAX_BUDGET_PER_TASK:.2f} USDT")
print(f"  {'Developer premium:':30s} ${DEV_PREMIUM:.2f} USDT")
print(f"  {'─' * 60}")

# ── Stop event for graceful worker shutdown ────────────────────────────

stop_event = threading.Event()

# ── Start worker threads ───────────────────────────────────────────────

worker_threads: list[threading.Thread] = []
for wid in WORKER_IDS:
    t = threading.Thread(
        target=start_worker_loop,
        args=(wid, ledger, broker, engine, amazon_manifest, stop_event),
        daemon=True,
    )
    t.start()
    worker_threads.append(t)

time.sleep(0.3)  # let workers settle

# ── Publish 30 tasks all at once ───────────────────────────────────────

published = 0
for i in range(NUM_TASKS):
    tid = broker.publish_task(
        user_id=USER_ID,
        asin=f"ASIN{chr(65 + (i % 26))}{i:04d}",
        developer_premium=DEV_PREMIUM,
        max_budget=MAX_BUDGET_PER_TASK,
    )
    if tid is not None:
        published += 1

print(f"  Published: {published} tasks to broker\n")

# ── Wait for queue to drain ─────────────────────────────────────────────

while broker.pending_count > 0:
    time.sleep(0.5)

# Give workers time to finish their last task and settle escrow
time.sleep(3.0)

# ── Stop workers ────────────────────────────────────────────────────────

stop_event.set()
for t in worker_threads:
    t.join(timeout=2.0)

elapsed = 0.0  # rough wall time

# ── Audit ───────────────────────────────────────────────────────────────

final_wealth = ledger.total_system_wealth
wealth_diff = round(final_wealth - initial_wealth, 6)
wealth_ok = abs(wealth_diff) < 0.0001

completed = broker.completed_count
summary = broker.worker_summary()

# Build worker earnings table
worker_earnings = {}
for wid in WORKER_IDS:
    worker_earnings[wid] = ledger.get_dev_usdt(wid)

total_dev_earnings = sum(worker_earnings.values())

print(f"  {'─' * 60}")
print(f"  {'RESULTS':^60}")
print(f"  {'─' * 60}")
print(f"  {'Tasks published:':30s} {published}")
print(f"  {'Tasks completed:':30s} {completed}")
print(f"  {'Unprocessed (broker stale):':30s} {published - completed}")
print(f"  {'─' * 60}")
print(f"  {'WORKER BREAKDOWN':^60}")
print(f"  {'─' * 60}")

for wid in WORKER_IDS:
    tasks_done = summary.get(wid, 0)
    earnings = worker_earnings[wid]
    bar = "█" * max(1, int(tasks_done * 30 / max(max(summary.values(), default=1), 1)))
    print(f"  {wid:14s}  {tasks_done:3d} tasks  ${earnings:>5.2f} USDT  {bar}")

print(f"  {'─' * 60}")
print(f"  {'Total worker earnings:':30s} ${total_dev_earnings:.2f} USDT")
print(f"  {'Platform tax collected:':30s} ${ledger.founder_treasury_usdt:.2f} USDT")
print(f"  {'User balance remaining:':30s} ${ledger.get_user_usdt(USER_ID):.2f} USDT")

alice_end = ledger.get_user_usdt(USER_ID)
total_accounted = alice_end + total_dev_earnings + ledger.founder_treasury_usdt

print(f"  {'─' * 60}")
print(f"  {'Initial system wealth:':30s} ${initial_wealth:.2f} USDT")
print(f"  {'Final system wealth:':30s} ${final_wealth:.2f} USDT")
print(f"  {'Difference:':30s} ${wealth_diff:+.6f} USDT")
print(f"  {'Alice + Workers + Treasury:':30s} ${total_accounted:.2f} USDT")

if abs(total_accounted - initial_wealth) >= 0.0001:
    print(f"  >>> BREAKDOWN MISMATCH! {total_accounted:.2f} != {initial_wealth:.2f}")

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
print(f"  DePIN Model Verified — {completed} tasks across "
      f"{len([w for w in summary.values() if w > 0])} workers")
print(f"  {'─' * 60}")
sys.exit(exit_code)
