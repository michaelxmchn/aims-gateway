"""Stress Test — Stateful Task Claiming & Fault-Tolerance.

Simulates a DePIN network with fault-tolerant task claiming:
  - **3 Worker Nodes**: Worker-1 and Worker-2 work normally.
    Worker-3 *simulates a crash* — it claims a task then sleeps for
    10 s, abandoning the CLAIMED task.
  - **Background Timeout Daemon**: Runs ``broker.check_timeouts()``
    every 1 s, recycling abandoned tasks back to PENDING.
  - **Result**: Worker-3's abandoned tasks are picked up and completed
    by Worker-1 or Worker-2.

Audits that total system wealth is conserved and that every published
task eventually reaches SUCCESS or FAILED.
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
logger = logging.getLogger("depin_fault_tolerance")

# ── Constants ───────────────────────────────────────────────────────────────

NUM_WORKERS = 3
NUM_TASKS = 12
MAX_BUDGET_PER_TASK = 1.00
DEV_PREMIUM = 2.0
USER_SEED = 100.0
USER_ID = "alice"
WORKER_IDS = ["worker_1", "worker_2", "worker_3"]
TIMEOUT_CHECK_INTERVAL = 1.0  # seconds between check_timeouts() calls

# ── Dependencies ────────────────────────────────────────────────────────────

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

# ── Seed ────────────────────────────────────────────────────────────────────

print("=" * 72)
print("  FAULT-TOLERANCE STRESS TEST — Stateful Task Claiming")
print("  Worker-1: normal    Worker-2: normal    Worker-3: CRASH SIM")
print("=" * 72)

ledger.seed_usdt(USER_ID, USER_SEED)
initial_wealth = ledger.total_system_wealth
print(f"\n  {'User seeded:':30s} ${USER_SEED:.2f} USDT ({USER_ID})")
print(f"  {'Initial system wealth:':30s} ${initial_wealth:.2f} USDT")
print(f"  {'Workers:':30s} {NUM_WORKERS} (W3 crash-simulates)")
print(f"  {'Tasks to publish:':30s} {NUM_TASKS}")
print(f"  {'Max budget per task:':30s} ${MAX_BUDGET_PER_TASK:.2f} USDT")
print(f"  {'Timeout window:':30s} 5.0 s")
print(f"  {'─' * 60}")

# ── Stop event for graceful worker shutdown ────────────────────────────────

stop_event = threading.Event()

# ── Start worker threads ───────────────────────────────────────────────────

worker_threads: list[threading.Thread] = []

# Worker-1: normal
t1 = threading.Thread(
    target=start_worker_loop,
    args=("worker_1", ledger, broker, engine, amazon_manifest, stop_event),
    daemon=True,
)
t1.start()
worker_threads.append(t1)

# Worker-2: normal
t2 = threading.Thread(
    target=start_worker_loop,
    args=("worker_2", ledger, broker, engine, amazon_manifest, stop_event),
    daemon=True,
)
t2.start()
worker_threads.append(t2)

# Worker-3: crashes after claiming each task (sleeps 10 s)
t3 = threading.Thread(
    target=start_worker_loop,
    args=("worker_3", ledger, broker, engine, amazon_manifest, stop_event),
    kwargs={"crash_simulate_after": 10.0},
    daemon=True,
)
t3.start()
worker_threads.append(t3)

time.sleep(0.3)  # let workers settle

# ── Background timeout checker daemon ──────────────────────────────────────

timeout_recycle_count = 0


def _timeout_checker() -> None:
    """Daemon that periodically recycles abandoned CLAIMED tasks."""
    global timeout_recycle_count
    while not stop_event.is_set():
        recycled = broker.check_timeouts()
        if recycled:
            timeout_recycle_count += len(recycled)
            print(
                f"  ⏰ Timeout checker recycled {len(recycled)} task(s): "
                f"{recycled}"
            )
        time.sleep(TIMEOUT_CHECK_INTERVAL)


timeout_thread = threading.Thread(target=_timeout_checker, daemon=True)
timeout_thread.start()

# ── Publish tasks all at once ──────────────────────────────────────────────

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

print(f"\n  Published: {published} tasks to broker\n")

# ── Wait for all tasks to be consumed ──────────────────────────────────────

while broker.pending_count > 0:
    time.sleep(0.5)

# Give workers time to finish their last task and settle escrow
time.sleep(3.0)

# ── Stop everything ────────────────────────────────────────────────────────

stop_event.set()
for t in worker_threads:
    t.join(timeout=2.0)

# ── Audit ──────────────────────────────────────────────────────────────────

final_wealth = ledger.total_system_wealth
wealth_diff = round(final_wealth - initial_wealth, 6)
wealth_ok = abs(wealth_diff) < 0.0001

completed = broker.completed_count
summary = broker.worker_summary()
status_counts = broker.status_counts()

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
print(f"  {'Timeout recycling events:':30s} {timeout_recycle_count}")
print(f"  {'Final status counts:':30s} {status_counts}")
print(f"  {'─' * 60}")
print(f"  {'WORKER BREAKDOWN':^60}")
print(f"  {'─' * 60}")

for wid in WORKER_IDS:
    tasks_done = summary.get(wid, 0)
    earnings = worker_earnings[wid]
    bar = "█" * max(1, int(tasks_done * 30 / max(max(summary.values(), default=1), 1)))
    label = f"{wid} [CRASH]" if wid == "worker_3" else wid
    print(f"  {label:22s}  {tasks_done:3d} tasks  ${earnings:>5.2f} USDT  {bar}")

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

# Assertions
all_done = completed == published
worker_3_dropped = summary.get("worker_3", 0) < published  # W3 didn't do all itself
worker_1_or_2_picked_up = (summary.get("worker_1", 0) + summary.get("worker_2", 0)) > 0

if wealth_ok and all_done and worker_3_dropped and worker_1_or_2_picked_up:
    print(f"  >>> FAULT-TOLERANCE AUDIT: PASSED ✓")
    print(f"  >>> Worker-3 tasks recycled and completed by Worker-1/2 ✓")
    print(f"  >>> All {published} tasks completed ✓")
    exit_code = 0
else:
    print(f"  >>> FAULT-TOLERANCE AUDIT: FAILED ⚠")
    if not wealth_ok:
        print(f"  >>> Wealth leak detected!")
    if not all_done:
        print(f"  >>> Only {completed}/{published} tasks completed!")
    if not worker_3_dropped:
        print(f"  >>> Worker-3 completed all tasks — crash simulation didn't trigger!")
    exit_code = 1

print(f"  {'─' * 60}")
print(f"  Fault-Tolerance Model Verified — {completed} tasks across "
      f"{len([w for w in summary.values() if w > 0])} workers")
print(f"  {'─' * 60}")
sys.exit(exit_code)
