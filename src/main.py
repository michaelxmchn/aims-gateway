"""AIMS — Assembly Root (Layer 7).

Full lifecycle demo: priority scoring, escrow settlement, and cool-down jail.
Run as: python3 -m src.main
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger("src.skills.registry").setLevel(logging.WARNING)
logging.getLogger("src.ledger.mock_counter").setLevel(logging.WARNING)

logger = logging.getLogger("aims")


def mock_skill_executor(manifest: "SkillManifest", arguments: Dict[str, Any]) -> str:
    """Mock executor — buggy_skill always fails, others succeed."""
    if manifest.name == "buggy_skill":
        raise RuntimeError("Intentional failure for testing cooldown jail")
    return (
        f"Executed '{manifest.name}' successfully.\n"
        f"Input: {json.dumps(arguments, indent=2)}"
    )


def print_sep(title: str) -> None:
    print(f"\n─── {title} ─{'─' * (58 - len(title))}")


def main() -> None:
    from src.skills.manifest import SkillManifest
    from src.skills.registry import SkillRegistry
    from src.gateway.router import GatewayRouter
    from src.runtime.sandbox import WorkflowEngine
    from src.ledger.mock_counter import MockLedger

    # ── Wire modules ──────────────────────────────────────────────────────
    registry = SkillRegistry()
    ledger = MockLedger()
    ledger.seed_balance("alice", 100.0)

    workflow_engine = WorkflowEngine(mock_skill_executor)
    router = GatewayRouter(
        registry=registry,
        ledger=ledger,
        executor=mock_skill_executor,
        workflow_engine=workflow_engine,
        mock_user="alice",
        mock_developer="aims_seed",
    )

    print()
    print("=" * 70)
    print("  AIMS v0.1.0 — Full Lifecycle Demo")
    print("=" * 70)

    # ── 1. Priority Score Breakdown ───────────────────────────────────────
    print_sep("1. Priority Score Breakdown")
    for m in registry.get_all_manifests():
        bd = registry.get_priority_breakdown(m.name)
        print(
            f"  {bd['skill']:24s}  score={bd['priority_score']:5.1f}  "
            f"(freq={bd['usage_frequency']}, staked={bd['staked_points']})"
        )

    # ── 2. Intent Detection & Tool Injection ──────────────────────────────
    print_sep("2. Intent Detection & Tool Injection")
    for prompt in [
        "Show me git log from v1.0 to v2.0",
        "Audit this Solidity contract for reentrancy",
        "Analyze this CSV data file",
    ]:
        tools = router.parse_intent_to_workflow(prompt)
        from src.skills.registry import detect_domain
        domain = detect_domain(prompt)
        print(f"  Prompt: {prompt}")
        print(f"  Domain: {domain}  →  Tools: {[t['name'] for t in tools]}")
        print()

    # ── 3. Successful Escrow Settlement via Router ────────────────────────
    print_sep("3. Successful Escrow (git_changelog)")
    result = router.route("Show me git log from v1.0 to v2.0")
    print(f"  Domain: {result.domain}")
    for call in result.skill_calls:
        s = "SUCCESS" if call.receipt and call.receipt.status == "SUCCESS" else "FAILED"
        print(f"  Skill: {call.skill_name} → {s}")
    print(f"  Balance check...")
    print(f"  alice balance: {ledger.get_user_balance('alice')} pts (was 100.0)")
    print(f"  aims_seed balance: {ledger.get_dev_balance('aims_seed')} pts")

    # ── 4. Failed Execution via WorkflowEngine ────────────────────────────
    print_sep("4. WorkflowEngine — Failed Execution")
    buggy = registry.get("buggy_skill")
    if buggy:
        receipt = workflow_engine.execute(buggy, {})
        print(f"  Skill: {receipt.skill_name}")
        print(f"  Status: {receipt.status}")
        print(f"  Error: {receipt.error_message}")
        print(f"  Compute: {receipt.compute_consumed:.4f}s")
    else:
        print("  buggy_skill not found in active manifests")
        print("  (demonstrating filtered state from earlier runs)")

    # ── 5. Cool-Down Jail (3 consecutive failures) ───────────────────────
    print_sep("5. Cool-Down Jail — 3 Strikes")
    jail_skill = "buggy_skill"
    for attempt in range(1, 4):
        print(f"\n  Attempt {attempt}: failing {jail_skill}...")
        jail_info = registry.record_execution(jail_skill, success=False, slashed=2.0)
        bd = registry.get_priority_breakdown(jail_skill)
        print(f"    Staked: {bd['staked_points']:.1f}")
        print(f"    Failures: {jail_info['consecutive_failures']}")
        if jail_info.get("jailed"):
            print(
                f"    🚫 JAILED for {jail_info['jail_duration_hours']} hours "
                f"(staked={bd['staked_points']:.1f}, failures=3)"
            )

    # ── 6. Jail Verification ─────────────────────────────────────────────
    print_sep("6. Jail Verification")
    all_manifests = registry.get_all_manifests()
    names = [m.name for m in all_manifests]
    print(f"  Active skills after jail: {names}")
    assert jail_skill not in names, f"BUG: {jail_skill} should be frozen!"
    print(f"  ✓ '{jail_skill}' correctly filtered by load_all()")
    load_count = len(names)

    # Verify the router workflow excludes the jailed skill
    print()
    print(f"  Router top-3 for general prompt:")
    top3 = [m.name for m in registry.get_top_for_domain("run a general task", limit=3)]
    print(f"  {top3}")
    assert jail_skill not in top3, f"BUG: {jail_skill} still in top-3!"
    print(f"  ✓ '{jail_skill}' excluded from top-3 ranking")

    # ── 7. Final Registry State ──────────────────────────────────────────
    print_sep("7. Final Registry State")
    report = registry.health_report()
    print(f"  Status: {report['status']}")
    print(f"  Active manifests: {report['manifest_count']}")
    for m in registry.get_all_manifests():
        bd = registry.get_priority_breakdown(m.name)
        print(f"    {m.name:24s}  freq={bd['usage_frequency']}  staked={bd['staked_points']:.1f}")

    print()
    print("=" * 70)
    print(f"  All {load_count} active skills verified. Jail mechanism OK.")
    print("=" * 70)
    print()


if __name__ == "__main__":
    main()
