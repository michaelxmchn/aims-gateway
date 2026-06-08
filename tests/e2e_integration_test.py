#!/usr/bin/env python3
"""
tests/e2e_integration_test.py — AIMS Grand Finale E2E Integration Test.

Orchestrates every mechanism into one flawless flow:

  1. Account Abstraction — identity map + Stripe fiat on-ramp
  2. Developer & Multi-Tier Skill Registration
  3. Worker Hive Staking (3 workers, $5 each)
  4. Fault Tolerance — Worker-3 claims then times out → strike
  5. Proof-of-Result Slashing — Worker-1 corrupts 3 tasks → $1 slash to treasury
  6. Perfect Execution — Worker-2 (Tier-2, 2.5x, 4.0s) → itemised settlement
  7. Wealth Conservation Audit
  8. Ephemeral Dashboard — HTML generation with full history
"""

from __future__ import annotations

import json
import logging
import sys
import time

sys.path.insert(0, ".")

from src.gateway.broker import TaskBroker
from src.ledger.mock_counter import MockLedger, BASE_GAS_RATE, TIER_MULTIPLIERS
from src.skills.manifest import SkillManifest
from src.runtime.sandbox import SKILL_IMPLS, WorkflowEngine, resolve_impl

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("e2e")


def print_sep(title: str, char: str = "=") -> None:
    print(f"\n{char * 72}")
    print(f"  {title}")
    print(f"{char * 72}")


def main() -> int:
    # ═══════════════════════════════════════════════════════════════════════
    #  1. SETUP ECOSYSTEM & ACCOUNT ABSTRACTION
    # ═══════════════════════════════════════════════════════════════════════
    print_sep("PHASE 1 — Ecosystem Setup & Account Abstraction")

    from src.chain.settlement import ChainSettlement

    ledger = MockLedger()
    broker = TaskBroker(ledger)
    chain = ChainSettlement("http://localhost")
    engine = WorkflowEngine(resolve_impl)

    # Register Web2 user → Web3 wallet via identity map
    email = "merchant_mike@gmail.com"
    identity = chain.register_identity(email, wallet_address="0xMerchantMikeBase")
    print(f"  Identity registered: {identity.email} → {identity.wallet_address}")

    # Fiat on-ramp simulation (Stripe payment)
    webhook_event = chain.simulate_stripe_webhook(email, 50.0, ledger)
    print(f"  Stripe webhook: {webhook_event['type']}  (id={webhook_event['id']})")
    print(f"  Wallet funded:  ${ledger.get_user_usdt(email):.2f} USDT")
    assert ledger.get_user_usdt(email) == 50.0
    assert chain.resolve_wallet(email) == "0xMerchantMikeBase"

    # ═══════════════════════════════════════════════════════════════════════
    #  2. DEVELOPER & MULTI-TIER SKILL
    # ═══════════════════════════════════════════════════════════════════════
    print_sep("PHASE 2 — Developer Registration & Tier-2 Skill Publishing")

    DEV_PREMIUM = 0.02
    ledger.seed_dev_usdt("developer_1", 100.00)
    print(f"  Developer seeded: developer_1 +$100.00 USDT")

    # Tier-2 output schema: requires posted_url + status
    OUTPUT_SCHEMA = {
        "type": "object",
        "required": ["posted_url", "status"],
        "properties": {
            "posted_url": {"type": "string"},
            "status": {"type": "string"},
        },
    }

    skill_manifest = SkillManifest(
        name="social_media_booster",
        description="Tier-2 social media automation skill",
        input_schema={
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Content to post"},
            },
            "required": ["content"],
        },
        output_schema=OUTPUT_SCHEMA,
        version="2.0.0",
        author="developer_1",
        price_points=2,
        tags=["social", "automation", "tier-2"],
    )

    # Register implementation
    def _social_media_booster_impl(arguments: dict) -> str:
        """Tier-2 impl: 4.0s execution, valid output."""
        time.sleep(4.0)
        return json.dumps({
            "posted_url": "https://twitter.com/status/123456",
            "status": "published",
        })

    SKILL_IMPLS["social_media_booster"] = _social_media_booster_impl
    print(f"  Skill published: {skill_manifest.name} v{skill_manifest.version}")
    print(f"  Output schema: required={OUTPUT_SCHEMA['required']}")
    print(f"  Developer premium: ${DEV_PREMIUM:.2f} USDT")

    # ═══════════════════════════════════════════════════════════════════════
    #  3. WORKER HIVE STAKING
    # ═══════════════════════════════════════════════════════════════════════
    print_sep("PHASE 3 — Worker Hive Staking (3 Workers × $5)")

    WORKER_IDS = ["worker_1", "worker_2", "worker_3"]
    STAKE_AMOUNT = 5.0
    WORKER_SEED = 10.0

    for wid in WORKER_IDS:
        ledger.seed_dev_usdt(wid, WORKER_SEED)
        ok = ledger.register_worker(wid, STAKE_AMOUNT)
        coll = ledger.get_staked_collateral(wid)
        bal = ledger.get_dev_usdt(wid)
        assert ok, f"{wid} registration failed"
        print(f"  {wid:12s}  balance=${bal:.2f}  staked=${coll:.2f}  total=${bal + coll:.2f}")

    MAX_BUDGET = 3.0

    # Capture total system wealth AFTER all seeding but BEFORE any transactions
    initial_wealth = ledger.total_system_wealth
    print(f"\n  Total seeded wealth: ${initial_wealth:.2f} USDT")
    assert abs(initial_wealth - 180.00) < 0.01, \
        f"Expected $180.00 initial wealth, got ${initial_wealth:.2f}"

    # ═══════════════════════════════════════════════════════════════════════
    #  4. FAULT TOLERANCE — Worker-3 Outage
    # ═══════════════════════════════════════════════════════════════════════
    print_sep("PHASE 4 — Fault Tolerance (Worker-3 Timeout + Strike)")

    # Publish Task A
    task_a = broker.publish_task(
        user_id=email,
        asin="SOCIAL-001",
        developer_premium=DEV_PREMIUM,
        max_budget=MAX_BUDGET,
        skill_id="social_media_booster",
        compute_tier=2,
    )
    assert task_a is not None
    print(f"  Published: {task_a} (PENDING)")

    # Worker-3 claims Task A then goes offline
    claimed_a = broker.claim_task("worker_3")
    assert claimed_a is not None
    assert claimed_a["worker_id"] == "worker_3"
    print(f"  Worker-3 claimed: {claimed_a['task_id']} → CLAIMED")

    # Simulate Worker-3 crash — sleep past 5s CLAIM_TIMEOUT
    time.sleep(6.0)

    # Timeout checker recycles the abandoned task
    recycled = broker.check_timeouts()
    w3_strikes = ledger.worker_strikes.get("worker_3", 0)
    print(f"  check_timeouts() recycled: {len(recycled)} task(s)")
    print(f"  Worker-3 strikes: {w3_strikes}")
    assert len(recycled) >= 1, "Task should have been recycled"
    assert w3_strikes == 1, "Worker-3 should have 1 strike for timeout"

    # Verify task is back to PENDING
    counts = broker.status_counts()
    assert counts.get("PENDING", 0) >= 1
    print(f"  Status counts: {counts}")

    # ═══════════════════════════════════════════════════════════════════════
    #  5. PROOF-OF-RESULT CHEATING — Worker-1 Slashing
    # ═══════════════════════════════════════════════════════════════════════
    print_sep("PHASE 5 — Proof-of-Result Cheating (Worker-1 Slashing)")

    # Worker-1 claims the recycled Task A
    claimed_recycled = broker.claim_task("worker_1")
    assert claimed_recycled is not None
    escrow_a = claimed_recycled["escrow_hold"]
    print(f"  Worker-1 claimed recycled: {claimed_recycled['task_id']}")

    # Execute but corrupt the output
    receipt_a = engine.execute(skill_manifest, {"content": "post this!"})
    assert receipt_a.status == "SUCCESS"  # engine-level output_schema passes

    corrupt_a = {"status": "done"}  # missing posted_url!
    valid = broker.validate_result_generic(corrupt_a, OUTPUT_SCHEMA, "worker_1")
    assert not valid, "Corrupt output should fail validation"
    w1_strikes = ledger.worker_strikes.get("worker_1", 0)
    print(f"  Worker-1 corrupt → validation FAILED  (strikes={w1_strikes})")

    # Settle as FAILED (refund to user)
    detail = ledger.release_escrow_dynamic(
        escrow_a.escrow_id,
        user_id=claimed_recycled["user_id"],
        developer_id="worker_1",
        execution_time=receipt_a.execution_time,
        skill_meta={"compute_tier": 2, "developer_premium": DEV_PREMIUM,
                     "skill_id": "social_media_booster"},
        success=False,
    )
    assert detail is not None
    assert detail.outcome == "REFUNDED"
    broker.complete_task(claimed_recycled["task_id"], "FAILED", detail)

    # Publish 2 more tasks for Worker-1 to corrupt (need 3 total strikes)
    for i in range(2):
        tid = broker.publish_task(
            user_id=email,
            asin=f"CORRUPT-{i:03d}",
            developer_premium=DEV_PREMIUM,
            max_budget=MAX_BUDGET,
            skill_id="social_media_booster",
            compute_tier=2,
        )
        claimed = broker.claim_task("worker_1")
        assert claimed is not None

        receipt = engine.execute(skill_manifest, {"content": "spam"})
        assert receipt.status == "SUCCESS"

        corrupt = {"posted_url": ""}  # empty string, should fail minimum or required
        valid = broker.validate_result_generic(corrupt, OUTPUT_SCHEMA, "worker_1")
        assert not valid

        detail = ledger.release_escrow_dynamic(
            claimed["escrow_hold"].escrow_id,
            user_id=claimed["user_id"],
            developer_id="worker_1",
            execution_time=receipt.execution_time,
            skill_meta={"compute_tier": 2, "developer_premium": DEV_PREMIUM,
                         "skill_id": "social_media_booster"},
            success=False,
        )
        broker.complete_task(claimed["task_id"], "FAILED", detail)

        strikes = ledger.worker_strikes.get("worker_1", 0)
        coll = ledger.get_staked_collateral("worker_1")
        print(f"  Worker-1 corrupt #{i + 1} → FAILED  (strikes={strikes}, collateral=${coll:.2f})")

    w1_collateral = ledger.get_staked_collateral("worker_1")
    w1_final_strikes = ledger.worker_strikes.get("worker_1", 0)
    print(f"\n  Worker-1 final collateral: ${w1_collateral:.2f}")
    print(f"  Worker-1 final strikes:    {w1_final_strikes}")
    # After 3 corruptions → strike 3 triggers slash → $1 loss → reset strikes to 0
    assert w1_collateral == STAKE_AMOUNT - 1.0, (
        f"Expected ${STAKE_AMOUNT - 1:.2f} collateral, got ${w1_collateral:.2f}"
    )
    assert w1_final_strikes == 0, "Strikes should reset to 0 after slash"
    print(f"  ✓ Slashing verified: $1.00 deducted → treasury")

    # ═══════════════════════════════════════════════════════════════════════
    #  6. PERFECT EXECUTION — Worker-2 Multi-Tier Settlement
    # ═══════════════════════════════════════════════════════════════════════
    print_sep("PHASE 6 — Perfect Execution & Multi-Tier Settlement (Worker-2)")

    task_b = broker.publish_task(
        user_id=email,
        asin="PERFECT-001",
        developer_premium=DEV_PREMIUM,
        max_budget=MAX_BUDGET,
        skill_id="social_media_booster",
        compute_tier=2,
    )
    assert task_b is not None

    claimed_b = broker.claim_task("worker_2")
    assert claimed_b is not None
    escrow_b = claimed_b["escrow_hold"]

    receipt_b = engine.execute(skill_manifest, {"content": "Hello world!"})
    assert receipt_b.status == "SUCCESS"

    output_b = json.loads(receipt_b.output)
    valid_b = broker.validate_result_generic(output_b, OUTPUT_SCHEMA, "worker_2")
    assert valid_b, "Perfect output should pass validation"

    exec_time = receipt_b.execution_time
    tier_mult = TIER_MULTIPLIERS[2]  # 2.5
    expected_gas = round(exec_time * BASE_GAS_RATE * tier_mult, 4)

    detail_b = ledger.release_escrow_dynamic(
        escrow_b.escrow_id,
        user_id=claimed_b["user_id"],
        developer_id="worker_2",
        execution_time=exec_time,
        skill_meta={"compute_tier": 2, "developer_premium": DEV_PREMIUM,
                     "skill_id": "social_media_booster"},
        success=True,
    )
    assert detail_b is not None
    assert detail_b.outcome == "COMPLETED"
    broker.complete_task(claimed_b["task_id"], "SUCCESS", detail_b)

    print(f"  Worker-2 execution time:      {exec_time:.2f}s")
    print(f"  Tier multiplier:              {tier_mult:.1f}x")
    print(f"  ┌─ Billing Receipt ────────────────────────────────┐")
    print(f"  │ {'Gas cost (rate×tier×time):':32s} ${detail_b.gas_cost:.4f} USDT  │")
    print(f"  │ {'Developer premium:':32s} ${detail_b.developer_premium:.2f} USDT      │")
    print(f"  │ {'Total cost:':32s} ${detail_b.total_cost:.2f} USDT      │")
    print(f"  │ {'Platform tax (1%):':32s} ${detail_b.platform_tax:.4f} USDT  │")
    print(f"  │ {'Developer payout:':32s} ${detail_b.developer_payout:.4f} USDT  │")
    print(f"  │ {'Unused refund (→ user):':32s} ${detail_b.unused_refund:.2f} USDT      │")
    print(f"  └──────────────────────────────────────────────────┘")

    # Verify gas calculation
    gas_ok = abs(detail_b.gas_cost - expected_gas) < 0.02
    assert gas_ok, f"Gas mismatch: expected ~${expected_gas:.4f}, got ${detail_b.gas_cost:.4f}"
    print(f"  ✓ Gas: ${detail_b.gas_cost:.4f} ≈ expected ${expected_gas:.4f}")

    # Verify platform tax
    expected_tax = round(detail_b.total_cost * 0.01, 2)
    assert abs(detail_b.platform_tax - expected_tax) < 0.001
    print(f"  ✓ Platform tax: ${detail_b.platform_tax:.4f}")

    # Verify 99/1 split
    dev_share = detail_b.developer_payout
    tax_share = detail_b.platform_tax
    total_distributed = round(dev_share + tax_share, 4)
    assert abs(total_distributed - detail_b.total_cost) < 0.001, \
        f"Distribution mismatch: {dev_share} + {tax_share} != {detail_b.total_cost}"
    print(f"  ✓ 99/1 distribution verified: ${dev_share:.4f} + ${tax_share:.4f} = ${total_distributed:.4f}")

    # ═══════════════════════════════════════════════════════════════════════
    #  7. WEALTH CONSERVATION AUDIT
    # ═══════════════════════════════════════════════════════════════════════
    print_sep("PHASE 7 — Wealth Conservation Audit")

    final_wealth = ledger.total_system_wealth
    wealth_diff = round(final_wealth - initial_wealth, 6)

    user_bal = ledger.get_user_usdt(email)
    dev_bal = ledger.get_dev_usdt("developer_1")
    w1_bal = ledger.get_dev_usdt("worker_1")
    w2_bal = ledger.get_dev_usdt("worker_2")
    w3_bal = ledger.get_dev_usdt("worker_3")
    w1_coll = ledger.get_staked_collateral("worker_1")
    w2_coll = ledger.get_staked_collateral("worker_2")
    w3_coll = ledger.get_staked_collateral("worker_3")
    treasury = ledger.founder_treasury_usdt

    accounted = round(user_bal + dev_bal + w1_bal + w2_bal + w3_bal
                      + w1_coll + w2_coll + w3_coll + treasury, 4)

    print(f"  {'Component':30s}  {'Balance':>10s}")
    print(f"  {'─' * 42}")
    print(f"  {f'User ({email}):':30s}  ${user_bal:>8.2f}")
    print(f"  {'Developer (developer_1):':30s}  ${dev_bal:>8.2f}")
    print(f"  {'Worker-1 (available):':30s}  ${w1_bal:>8.2f}")
    print(f"  {'Worker-2 (available):':30s}  ${w2_bal:>8.2f}")
    print(f"  {'Worker-3 (available):':30s}  ${w3_bal:>8.2f}")
    print(f"  {'Worker-1 (staked):':30s}  ${w1_coll:>8.2f}")
    print(f"  {'Worker-2 (staked):':30s}  ${w2_coll:>8.2f}")
    print(f"  {'Worker-3 (staked):':30s}  ${w3_coll:>8.2f}")
    print(f"  {'Platform treasury:':30s}  ${treasury:>8.2f}")
    print(f"  {'─' * 42}")
    print(f"  {'Accounted total:':30s}  ${accounted:>8.2f}")
    print(f"  {'Initial wealth:':30s}  ${initial_wealth:>8.2f}")
    print(f"  {'Difference:':30s}  ${wealth_diff:>+8.6f}")

    # Verify wealth conservation
    totals_match = abs(accounted - initial_wealth) < 0.01
    wealth_ok = abs(wealth_diff) < 0.0001

    assert totals_match, \
        f"WEALTH LEAK! Accounted ${accounted:.2f} ≠ Initial ${initial_wealth:.2f}"

    print(f"\n  >>> WEALTH AUDIT: {'PASSED ✓' if wealth_ok else 'FAILED ⚠'}")
    print(f"  >>> Funds conserved: ${initial_wealth:.2f} → ${final_wealth:.2f} "
          f"({'+' if wealth_diff >= 0 else ''}${wealth_diff:.6f})")
    print(f"  >>> Platform treasury: ${treasury:.4f} "
          f"($1.00 slash + ${treasury - 1.00:.4f} tax)")

    # ═══════════════════════════════════════════════════════════════════════
    #  8. EPHEMERAL DASHBOARD
    # ═══════════════════════════════════════════════════════════════════════
    print_sep("PHASE 8 — Ephemeral Dashboard (Tailwind + Chart.js)")

    from src.skills.dashboard_skill import generate_dashboard

    dashboard_result = generate_dashboard(ledger=ledger, broker=broker)

    assert dashboard_result["status"] == "SUCCESS", \
        f"Dashboard generation failed: {dashboard_result}"

    import os
    html_path = os.path.expanduser("~/.aims/dashboard.html")
    assert os.path.exists(html_path), f"Dashboard HTML not found at {html_path}"
    html_size = os.path.getsize(html_path)

    # Verify key HTML elements
    with open(html_path, "r") as f:
        html_content = f.read()

    assert "tailwind" in html_content.lower(), "Missing Tailwind CSS"
    assert "chart.js" in html_content.lower() or "chart" in html_content.lower(), "Missing Chart.js"
    assert "worker" in html_content.lower(), "Missing worker data"
    assert "slash" in html_content.lower(), "Missing slashing log"
    assert "alice" in html_content, "Missing seed user data in dashboard"

    print(f"  Dashboard HTML: {html_path}")
    print(f"  File size:      {html_size:,} bytes")
    print(f"  Tailwind CSS:   {'✓' if 'tailwind' in html_content.lower() else '✗'}")
    print(f"  Chart.js:       {'✓' if 'chart' in html_content.lower() else '✗'}")
    print(f"  Slashing logs:  {'✓' if 'slash' in html_content.lower() else '✗'}")
    print(f"  Worker data:    {'✓' if 'worker' in html_content.lower() else '✗'}")
    print(f"  Status:         ✓ Dashboard generated and verified")

    # ═══════════════════════════════════════════════════════════════════════
    #  FINAL SUMMARY
    # ═══════════════════════════════════════════════════════════════════════
    print_sep("AIMS NETWORK — GRAND FINALE RESULTS", "=")

    checks = [
        ("Account Abstraction", identity.wallet_address == "0xMerchantMikeBase"),
        ("Stripe On-Ramp", ledger.get_user_usdt(email) > 0),
        ("Worker Staking (3 × $5)", ledger.get_staked_collateral("worker_2") == 5.0 and ledger.get_staked_collateral("worker_3") == 5.0),
        ("Fault Tolerance (W3 timeout)", w3_strikes == 1),
        ("Slashing (W1 -$1)", w1_collateral == 4.0),
        ("Schema Validation (corrupt rejected)", not valid),
        ("Perfect Execution (W2)", detail_b.outcome == "COMPLETED"),
        ("Tier-2 Billing (2.5x)", gas_ok),
        ("99/1 Tax Split", abs(total_distributed - detail_b.total_cost) < 0.001),
        ("Wealth Conservation", wealth_ok),
        ("Dashboard Generation", os.path.exists(html_path)),
    ]

    passed = sum(1 for _, ok in checks if ok)
    total_checks = len(checks)

    print(f"\n  {'Check':40s}  {'Result':>8s}")
    print(f"  {'─' * 50}")
    for name, ok in checks:
        print(f"  {name:40s}  {'✓ PASS' if ok else '✗ FAIL':>8s}")

    print(f"\n  {'─' * 50}")
    print(f"  {'TOTAL':40s}  {passed:>2d}/{total_checks}")
    print(f"\n{'=' * 72}")
    if passed == total_checks:
        print(f"  >>> AIMS NETWORK: 100% ARCHITECTURAL & GAME-THEORETIC CLOSURE ✓")
        print(f"  >>> All {total_checks} mechanisms verified end-to-end")
    else:
        print(f"  >>> AIMS NETWORK: {passed}/{total_checks} checks passed ⚠")
    print(f"{'=' * 72}\n")

    return 0 if passed == total_checks else 1


if __name__ == "__main__":
    sys.exit(main())
