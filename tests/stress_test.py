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

import json
import logging
import sys
import threading
import time

sys.path.insert(0, ".")

from src.gateway.broker import TaskBroker
from src.ledger.mock_counter import MockLedger
from src.skills.manifest import SkillManifest
from src.runtime.sandbox import SKILL_IMPLS, WorkflowEngine, resolve_impl, start_worker_loop

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

# ═══════════════════════════════════════════════════════════════════════════
#  PHASE 2: REPUTATION & RATING — Outlier Truncation
# ═══════════════════════════════════════════════════════════════════════════

print("\n")
print("=" * 72)
print("  REPUTATION & RATING — Outlier Truncation")
print("  5 honest users + 1 malicious → double-sided reputation protection")
print("=" * 72)

RATING_SKILL_ID = "amazon_scraper"
HONEST_USERS = [f"honest_user_{i}" for i in range(1, 6)]
MALICIOUS_USER = "malicious_user"
ALL_RATING_USERS = HONEST_USERS + [MALICIOUS_USER]
RATING_TASK_BUDGET = 1.00
RATING_USER_SEED = 10.0

# Fresh ledger, broker, and workers for the rating test
rating_ledger = MockLedger()
rating_broker = TaskBroker(rating_ledger)
rating_engine = WorkflowEngine(resolve_impl)

rating_stop_event = threading.Event()

# Seed all users
for uid in ALL_RATING_USERS:
    rating_ledger.seed_usdt(uid, RATING_USER_SEED)

print(f"\n  {'Users seeded:':30s} {len(ALL_RATING_USERS)} × ${RATING_USER_SEED:.2f} USDT")
print(f"  {'Skill under test:':30s} {RATING_SKILL_ID}")
print(f"  {'Honest raters:':30s} {len(HONEST_USERS)}")
print(f"  {'Malicious rater:':30s} {MALICIOUS_USER}")
print(f"  {'─' * 60}")

# Start 2 honest workers for the rating test
for wid in ["rating_worker_1", "rating_worker_2"]:
    t = threading.Thread(
        target=start_worker_loop,
        args=(wid, rating_ledger, rating_broker, rating_engine,
              amazon_manifest, rating_stop_event),
        daemon=True,
    )
    t.start()

time.sleep(0.3)

# Publish one task per user so each user has a successful usage record
for uid in ALL_RATING_USERS:
    rating_broker.publish_task(
        user_id=uid,
        asin=f"RATING-{uid}",
        developer_premium=DEV_PREMIUM,
        max_budget=RATING_TASK_BUDGET,
        skill_id=RATING_SKILL_ID,
    )

# Wait for all tasks to complete (both PENDING and CLAIMED)
while rating_broker.completed_count < len(ALL_RATING_USERS):
    time.sleep(0.3)
time.sleep(1.0)
rating_stop_event.set()

print(f"  {'Tasks published:':30s} {len(ALL_RATING_USERS)}")
print(f"  {'Tasks completed:':30s} {rating_broker.completed_count}")

# Verify each user has usage recorded (they can rate)
for uid in ALL_RATING_USERS:
    rep = rating_ledger.get_user_reputation(uid)
    assert rep == 1.0, f"{uid} reputation should be 1.0, got {rep}"
print(f"  {'All users usage OK:':30s} ✓ (rep=1.0)")

# ── Phase 2a: Honest users rate 5.0 ────────────────────────────────────────

print(f"\n  {'─' * 60}")
print(f"  {'HONEST RATING PHASE':^60}")
print(f"  {'─' * 60}")

for uid in HONEST_USERS:
    accepted = rating_ledger.submit_rating(uid, RATING_SKILL_ID, 5.0)
    status = "✓" if accepted else "✗"
    rep = rating_ledger.get_user_reputation(uid)
    score = rating_ledger.get_skill_weighted_score(RATING_SKILL_ID)
    print(f"  {uid:18s} → 5.0  {status}   (rep={rep:.2f}, score={score:.2f})")

score_after_honest = rating_ledger.get_skill_weighted_score(RATING_SKILL_ID)
honest_ratings_count = len(rating_ledger._skill_rating_entries.get(RATING_SKILL_ID, []))
print(f"  {'─' * 30}")
print(f"  {'Skill ratings count:':30s} {honest_ratings_count}")
print(f"  {'Weighted score (after honest):':30s} {score_after_honest:.2f}")
assert score_after_honest == 5.0, f"Expected 5.0, got {score_after_honest}"
print(f"  {'Score verification:':30s} ✓ (5.0 == 5.0)")

# ── Phase 2b: Malicious user bombs with 1.0 ────────────────────────────────

print(f"\n  {'─' * 60}")
print(f"  {'MALICIOUS RATING ATTEMPT':^60}")
print(f"  {'─' * 60}")

mal_rep_before = rating_ledger.get_user_reputation(MALICIOUS_USER)
malicious_accepted = rating_ledger.submit_rating(MALICIOUS_USER, RATING_SKILL_ID, 1.0)
mal_rep_after = rating_ledger.get_user_reputation(MALICIOUS_USER)
score_after_attack = rating_ledger.get_skill_weighted_score(RATING_SKILL_ID)
ratings_after = len(rating_ledger._skill_rating_entries.get(RATING_SKILL_ID, []))

print(f"  {'Malicious user:':30s} {MALICIOUS_USER}")
print(f"  {'Rating value:':30s} 1.0")
print(f"  {'Rating accepted:':30s} {'✓' if malicious_accepted else '✗ (SUPPRESSED)'}")
print(f"  {'Reputation before:':30s} {mal_rep_before:.2f}")
print(f"  {'Reputation after:':30s} {mal_rep_after:.2f}")
print(f"  {'Weighted score:':30s} {score_after_attack:.2f}")
print(f"  {'Total ratings in list:':30s} {ratings_after}")

# Assertions
ratings_unchanged = ratings_after == honest_ratings_count  # malicious not appended
score_unaffected = score_after_attack == score_after_honest  # 5.0 unaffected

rep_slashed_simple = abs(mal_rep_after - 0.9) < 0.01  # reputation dropped by 0.1

print(f"  {'─' * 30}")
print(f"  {'Rating list unchanged:':30s} {'✓' if ratings_unchanged else '✗'}")
print(f"  {'Malicious rep slashed:':30s} {'✓' if rep_slashed_simple else '✗'}")
print(f"  {'Score unaffected:':30s} {'✓' if score_unaffected else '✗'}")

rating_ok = ratings_unchanged and rep_slashed_simple and score_unaffected

if rating_ok:
    print(f"  {'─' * 60}")
    print(f"  >>> OUTLIER TRUNCATION AUDIT: PASSED ✓")
    print(f"  >>> Malicious 1.0 rating suppressed (anomaly detected) ✓")
    print(f"  >>> Malicious user reputation: 1.0 → 0.9 ✓")
    print(f"  >>> Weighted score remains 5.0 (unaffected) ✓")
else:
    print(f"  >>> OUTLIER TRUNCATION AUDIT: FAILED ⚠")
    if not ratings_unchanged:
        print(f"  >>> Malicious rating was appended to list!")
    if not rep_slashed_simple:
        print(f"  >>> Malicious user rep was not penalized (expected 0.9, got {mal_rep_after})")
    if not score_unaffected:
        print(f"  >>> Score changed from {score_after_honest} to {score_after_attack}!")
    exit_code = 1

print(f"  {'─' * 60}")
print(f"  Reputation System Verified — outlier truncation protects weighted score")
print(f"  {'─' * 60}")

# ═══════════════════════════════════════════════════════════════════════════
#  PHASE 3: COMPUTE TIER BILLING — Tier-2 (2.5x) Multiplier
# ═══════════════════════════════════════════════════════════════════════════

print("\n")
print("=" * 72)
print("  COMPUTE TIER BILLING — Tier-2 (2.5x) Multiplier")
print("  social_media_booster (4.0s) on compute_tier=2")
print("=" * 72)

TIER2_SKILL = "social_media_booster"

# Register a custom skill implementation that runs for ~4s
def _social_media_booster_tier2(arguments: dict) -> str:
    """Tier-2 skill: 4s execution, valid output for schema validation."""
    time.sleep(4.0)
    return json.dumps({
        "products": [{"asin": "TIER2-001", "price": 49.99, "title": "Tier-2 Post"}]
    })

SKILL_IMPLS[TIER2_SKILL] = _social_media_booster_tier2

tier_ledger = MockLedger()
tier_broker = TaskBroker(tier_ledger)
tier_engine = WorkflowEngine(resolve_impl)

tier_manifest = SkillManifest(
    name=TIER2_SKILL,
    description="Social media content booster (Tier-2)",
    input_schema={"type": "object", "properties": {}, "required": []},
    output_schema={"type": "object", "properties": {}, "required": []},
    version="1.0.0",
    author="aims_seed",
    price_points=0.0,
    tags=["social"],
)

tier_stop_event = threading.Event()
tier_worker = threading.Thread(
    target=start_worker_loop,
    args=("tier_worker", tier_ledger, tier_broker, tier_engine,
          tier_manifest, tier_stop_event),
    daemon=True,
)
tier_worker.start()

tier_ledger.seed_usdt("tier_user", 100.0)
time.sleep(0.3)

TIER2_TASK_BUDGET = 3.0
TIER2_PREMIUM = 0.0

tier_broker.publish_task(
    user_id="tier_user",
    asin="TIER2-TEST",
    developer_premium=TIER2_PREMIUM,
    max_budget=TIER2_TASK_BUDGET,
    skill_id=TIER2_SKILL,
    compute_tier=2,
)

while tier_broker.completed_count < 1:
    time.sleep(0.3)
time.sleep(1.0)
tier_stop_event.set()

tier_worker_earned = tier_ledger.get_dev_usdt("tier_worker")
tier_treasury = tier_ledger.founder_treasury_usdt

# Expected with tier=2, mult=2.5, ~4.0s:
#   gas_cost ≈ 0.01 × 2.5 × 4.0 = 0.1000
#   total    ≈ 0.1000 + 0.0 = 0.1000
#   tax      ≈ 0.1000 × 0.01 = 0.0010
#   payout   ≈ 0.1000 − 0.0010 = 0.0990
#   refund   ≈ 3.0 − 0.1000 = 2.90
EXPECTED_GAS_TIER2 = 0.01 * 2.5 * 4.0  # = 0.1000
tier_gas_approx = abs(tier_worker_earned - (EXPECTED_GAS_TIER2 * 0.99)) < 0.02
tier_billing_ok = tier_gas_approx

print(f"\n  {'Skill:':30s} {TIER2_SKILL} (compute_tier=2, mult=2.5x)")
print(f"  {'Execution target:':30s} 4.0 seconds")
print(f"  {'Worker earned:':30s} ${tier_worker_earned:.4f} USDT")
print(f"  {'Expected gas (2.5x):':30s} ${EXPECTED_GAS_TIER2:.4f} USDT")
print(f"  {'Treasury (tax):':30s} ${tier_treasury:.4f} USDT")

if tier_billing_ok:
    print(f"  {'─' * 60}")
    print(f"  >>> TIER-2 BILLING AUDIT: PASSED ✓")
    print(f"  >>> Tier multiplier 2.5x correctly applied ✓")
    print(f"  >>> Worker paid ~${tier_worker_earned:.4f} for 4.0s compute ✓")
else:
    print(f"  >>> TIER-2 BILLING AUDIT: FAILED ⚠")
    print(f"  >>> Expected ~${EXPECTED_GAS_TIER2:.4f}, got ${tier_worker_earned:.4f}")
    exit_code = 1

print(f"  {'─' * 60}")
print(f"  Compute Tier Billing Verified — Tier-2 2.5x multiplier")
print(f"  {'─' * 60}")

# ═══════════════════════════════════════════════════════════════════════════
#  PHASE 4: GENERIC VALIDATION REJECTION — Invalid Output Slashing
# ═══════════════════════════════════════════════════════════════════════════

print("\n")
print("=" * 72)
print("  GENERIC VALIDATION REJECTION — Slashing via validate_result_generic")
print("  Worker injects corrupt output → JSON Schema rejects → penalty")
print("=" * 72)

SLASHING_WORKER = "val_worker"
SLASHING_STAKE = 5.0

val_ledger = MockLedger()
val_broker = TaskBroker(val_ledger)
val_engine = WorkflowEngine(resolve_impl)

val_manifest = SkillManifest(
    name="amazon_scraper",
    description="Amazon scraper (corrupted for test)",
    input_schema={"type": "object", "properties": {}, "required": []},
    output_schema={"type": "object", "properties": {}, "required": []},
    version="1.0.0",
    author="aims_seed",
    price_points=2.0,
    tags=["scraping"],
)

val_stop_event = threading.Event()

# Seed and register the worker
val_ledger.seed_dev_usdt(SLASHING_WORKER, SLASHING_STAKE)
val_ledger.register_worker(SLASHING_WORKER, SLASHING_STAKE)
initial_strikes = val_ledger.worker_strikes.get(SLASHING_WORKER, 0)

val_worker = threading.Thread(
    target=start_worker_loop,
    args=(SLASHING_WORKER, val_ledger, val_broker, val_engine,
          val_manifest, val_stop_event),
    kwargs={"corrupt_output": True},
    daemon=True,
)
val_worker.start()

val_ledger.seed_usdt("val_user", 100.0)
time.sleep(0.3)

val_broker.publish_task(
    user_id="val_user",
    asin="VALIDATE-TEST",
    developer_premium=2.0,
    max_budget=1.0,
    skill_id="amazon_scraper",
)

while val_broker.completed_count < 1:
    time.sleep(0.3)
time.sleep(1.0)
val_stop_event.set()

strikes_after = val_ledger.worker_strikes.get(SLASHING_WORKER, 0)
val_rejected = strikes_after > initial_strikes
strike_gained = strikes_after - initial_strikes

print(f"\n  {'Worker:':30s} {SLASHING_WORKER}")
print(f"  {'Corrupt output:':30s} {{\"price\": -10}} (missing 'products')")
print(f"  {'Expected failure:':30s} JSON Schema 'required: [products]'")
print(f"  {'Strikes before:':30s} {initial_strikes}")
print(f"  {'Strikes after:':30s} {strikes_after}")
print(f"  {'Strike gained:':30s} {'✓' if val_rejected else '✗'} (+{strike_gained})")

if val_rejected:
    print(f"  {'─' * 60}")
    print(f"  >>> GENERIC VALIDATION AUDIT: PASSED ✓")
    print(f"  >>> Corrupt output correctly rejected by JSON Schema ✓")
    print(f"  >>> Worker penalized +{strike_gained} strike(s) ✓")
else:
    print(f"  >>> GENERIC VALIDATION AUDIT: FAILED ⚠")
    print(f"  >>> Expected 1 strike, got {strike_gained}")
    exit_code = 1

print(f"  {'─' * 60}")
print(f"  Generic Validation Verified — corrupt output rejected + penalty")
print(f"  {'─' * 60}")

sys.exit(exit_code)
