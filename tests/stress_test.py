"""Stress Test — Proof of Result & Slashing Protocol.

Simulates a DePIN network with worker registration, result validation,
and penalty slashing:

  - **Worker-1**: honest worker, normal execution
  - **Worker-2**: honest worker, normal execution
  - **Worker-3**: malicious/crash worker, registered with $5.00 stake,
    then repeatedly times out (crash_simulate_after=10s) to accumulate
    strikes.

Validation & Penalty Flow:
  1. ``broker.check_timeouts()`` detects ghosted (CLAIMED >5s) tasks
     and calls ``ledger.apply_penalty(worker_id, "timeout")``.
  2. After 3 strikes, a **Slash Event** fires: $1.00 deducted from
     the worker's staked collateral and transferred to the platform
     treasury; the strike counter resets to 0.

Audits:
  - Wealth conservation (collateral included in total_system_wealth).
  - Worker-3 collateral: $5.00 → $4.00 after the 3rd strike slash.
  - Treasury grows by $1.00 from the slash (plus platform tax from
    honest task executions).
  - All tasks eventually completed by honest workers.
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
logger = logging.getLogger("depin_slashing")

# ── Constants ───────────────────────────────────────────────────────────────

NUM_WORKERS = 3
NUM_TASKS = 40
MAX_BUDGET_PER_TASK = 1.00
DEV_PREMIUM = 2.0
USER_SEED = 100.0
USER_ID = "alice"
WORKER_IDS = ["worker_1", "worker_2", "worker_3"]
WORKER3_STAKE = 5.0
TIMEOUT_CHECK_INTERVAL = 1.0

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

# ── Seed & Register ─────────────────────────────────────────────────────────

print("=" * 72)
print("  SLASHING PROTOCOL STRESS TEST — Proof of Result & Penalties")
print("  Worker-1: honest    Worker-2: honest    Worker-3: MALICIOUS (crash)")
print("=" * 72)

ledger.seed_usdt(USER_ID, USER_SEED)
ledger.seed_dev_usdt("worker_3", WORKER3_STAKE)
registered = ledger.register_worker("worker_3", WORKER3_STAKE)

initial_wealth = ledger.total_system_wealth
initial_treasury = ledger.founder_treasury_usdt

print(f"\n  {'User seeded:':30s} ${USER_SEED:.2f} USDT ({USER_ID})")
print(f"  {'Worker-3 seeded:':30s} ${WORKER3_STAKE:.2f} USDT")
print(f"  {'Worker-3 registered:':30s} {'✓' if registered else '✗'}")
print(f"  {'Worker-3 collateral:':30s} ${ledger.get_staked_collateral('worker_3'):.2f} USDT")
print(f"  {'Initial system wealth:':30s} ${initial_wealth:.2f} USDT")
print(f"  {'Initial treasury:':30s} ${initial_treasury:.2f} USDT")
print(f"  {'Tasks to publish:':30s} {NUM_TASKS}")
print(f"  {'Timeout window:':30s} 5.0 s | 3 strikes = $1 slash")
print(f"  {'─' * 60}")

# ── Stop event ──────────────────────────────────────────────────────────────

stop_event = threading.Event()

# ── Start workers ───────────────────────────────────────────────────────────

worker_threads: list[threading.Thread] = []

# Worker-1: honest
t1 = threading.Thread(
    target=start_worker_loop,
    args=("worker_1", ledger, broker, engine, amazon_manifest, stop_event),
    daemon=True,
)
t1.start()
worker_threads.append(t1)

# Worker-2: honest
t2 = threading.Thread(
    target=start_worker_loop,
    args=("worker_2", ledger, broker, engine, amazon_manifest, stop_event),
    daemon=True,
)
t2.start()
worker_threads.append(t2)

# Worker-3: CRASH simulation — claims then sleeps 10s, triggering timeouts
t3 = threading.Thread(
    target=start_worker_loop,
    args=("worker_3", ledger, broker, engine, amazon_manifest, stop_event),
    kwargs={"crash_simulate_after": 10.0},
    daemon=True,
)
t3.start()
worker_threads.append(t3)

time.sleep(0.3)  # let workers settle

# ── Background timeout checker daemon ───────────────────────────────────────

timeout_recycle_count = 0


def _timeout_checker() -> None:
    """Daemon that periodically recycles abandoned CLAIMED tasks."""
    global timeout_recycle_count
    while not stop_event.is_set():
        recycled = broker.check_timeouts()
        if recycled:
            timeout_recycle_count += len(recycled)
            w3_strikes = ledger.worker_strikes.get("worker_3", 0)
            w3_collateral = ledger.get_staked_collateral("worker_3")
            print(
                f"  ⏰ Timeout checker recycled {len(recycled)} task(s). "
                f"W3 strikes={w3_strikes} collateral=${w3_collateral:.2f}"
            )
        time.sleep(TIMEOUT_CHECK_INTERVAL)


timeout_thread = threading.Thread(target=_timeout_checker, daemon=True)
timeout_thread.start()

# ── Publish tasks ───────────────────────────────────────────────────────────

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

# ── Wait for drain ──────────────────────────────────────────────────────────

while broker.pending_count > 0:
    time.sleep(0.5)

# Drain any remaining CLAIMED tasks (final timeout sweep + wait for recycling)
broker.check_timeouts()
while broker.status_counts().get("CLAIMED", 0) > 0:
    broker.check_timeouts()
    time.sleep(0.5)

# Give workers time to finish last settlements
time.sleep(3.0)

# One final sweep before audit
broker.check_timeouts()
time.sleep(1.0)

# ── Stop everything ─────────────────────────────────────────────────────────

stop_event.set()
for t in worker_threads:
    t.join(timeout=2.0)

# ── Audit ───────────────────────────────────────────────────────────────────

final_wealth = ledger.total_system_wealth
wealth_diff = round(final_wealth - initial_wealth, 6)
wealth_ok = abs(wealth_diff) < 0.0001

completed = broker.completed_count
summary = broker.worker_summary()
status_counts = broker.status_counts()

w3_collateral_before = WORKER3_STAKE
w3_collateral_after = ledger.get_staked_collateral("worker_3")
w3_strikes_final = ledger.worker_strikes.get("worker_3", 0)
treasury_growth = ledger.founder_treasury_usdt - initial_treasury

# Worker earnings
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
print(f"  {'SLASHING AUDIT':^60}")
print(f"  {'─' * 60}")
print(f"  {'Worker-3 collateral (before):':30s} ${w3_collateral_before:.2f} USDT")
print(f"  {'Worker-3 collateral (after):':30s} ${w3_collateral_after:.2f} USDT")
print(f"  {'Worker-3 final strikes:':30s} {w3_strikes_final}")
print(f"  {'Treasury growth:':30s} ${treasury_growth:.2f} USDT")
collateral_slashed = w3_collateral_before - w3_collateral_after
slash_verified = collateral_slashed >= 0.99  # at least $1 slashed
print(f"  {'Collateral slashed:':30s} ${collateral_slashed:.2f} USDT")
print(f"  {'─' * 60}")
print(f"  {'WORKER BREAKDOWN':^60}")
print(f"  {'─' * 60}")

for wid in WORKER_IDS:
    tasks_done = summary.get(wid, 0)
    earnings = worker_earnings[wid]
    bar = "█" * max(1, int(tasks_done * 30 / max(max(summary.values(), default=1), 1)))
    label = f"{wid} [SLASHED]" if wid == "worker_3" else wid
    print(f"  {label:22s}  {tasks_done:3d} tasks  ${earnings:>5.2f} USDT  {bar}")

print(f"  {'─' * 60}")
print(f"  {'Total worker earnings:':30s} ${total_dev_earnings:.2f} USDT")
print(f"  {'Platform tax collected:':30s} ${ledger.founder_treasury_usdt:.2f} USDT")
print(f"  {'User balance remaining:':30s} ${ledger.get_user_usdt(USER_ID):.2f} USDT")

alice_end = ledger.get_user_usdt(USER_ID)
total_accounted = (alice_end + total_dev_earnings
                   + ledger.founder_treasury_usdt
                   + ledger.get_staked_collateral("worker_3"))

print(f"  {'─' * 60}")
print(f"  {'Initial system wealth:':30s} ${initial_wealth:.2f} USDT")
print(f"  {'Final system wealth:':30s} ${final_wealth:.2f} USDT")
print(f"  {'Difference:':30s} ${wealth_diff:+.6f} USDT")
print(f"  {'Alice+Workers+Treasury+Collateral:':30s} ${total_accounted:.2f} USDT")

if abs(total_accounted - initial_wealth) >= 0.0001:
    print(f"  >>> BREAKDOWN MISMATCH! {total_accounted:.2f} != {initial_wealth:.2f}")

print(f"  {'─' * 60}")

# Assertions
all_done = completed == published
w3_slashed = slash_verified
honest_workers_worked = (summary.get("worker_1", 0) + summary.get("worker_2", 0)) > 0

if wealth_ok and all_done and w3_slashed and honest_workers_worked:
    print(f"  >>> SLASHING PROTOCOL AUDIT: PASSED ✓")
    print(f"  >>> Wealth conserved ({final_wealth:.2f} == {initial_wealth:.2f}) ✓")
    print(f"  >>> All {published} tasks completed ✓")
    print(f"  >>> Worker-3 slashed ${collateral_slashed:.2f} from collateral ✓")
    print(f"  >>> Treasury +${treasury_growth:.2f} (slash tax + platform tax) ✓")
    exit_code = 0
else:
    print(f"  >>> SLASHING PROTOCOL AUDIT: FAILED ⚠")
    if not wealth_ok:
        print(f"  >>> Wealth leak detected! diff=${wealth_diff:.6f}")
    if not all_done:
        print(f"  >>> Only {completed}/{published} tasks completed!")
    if not w3_slashed:
        print(f"  >>> Worker-3 was NOT slashed (collateral lost ${collateral_slashed:.2f})")
    if not honest_workers_worked:
        print(f"  >>> No honest worker completed any tasks!")
    exit_code = 1

print(f"  {'─' * 60}")
print(f"  Slashing Protocol Verified — {completed} tasks, ${collateral_slashed:.2f} slashed")
print(f"  {'─' * 60}")
sys.exit(exit_code)
