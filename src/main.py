"""AIMS — Assembly Root (Layer 7).

Document-Driven Architecture Demo:
  1. Skills loaded from subdirectories (manifest.json + rules.md)
  2. GatewayRouter injects Markdown rules as LLM context
  3. Tool definitions provided for native function calling
  4. Sandbox executes skill implementations on tool trigger

Run as: python3 -m src.main
"""

from __future__ import annotations

import json
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger("src.skills.registry").setLevel(logging.WARNING)
logging.getLogger("src.ledger.mock_counter").setLevel(logging.INFO)

logger = logging.getLogger("aims")


def print_sep(title: str) -> None:
    print(f"\n─── {title} ─{'─' * (58 - len(title))}")


def main() -> None:
    from src.skills.registry import SkillRegistry
    from src.gateway.router import GatewayRouter
    from src.runtime.sandbox import WorkflowEngine, resolve_impl

    # ── Wire modules ──────────────────────────────────────────────────────
    registry = SkillRegistry()
    router = GatewayRouter(registry)
    engine = WorkflowEngine(resolve_impl)

    print()
    print("=" * 70)
    print("  AIMS — Document-Driven Architecture Demo")
    print("=" * 70)

    # ── 1. Skill Discovery ────────────────────────────────────────────────
    print_sep("1. Skill Discovery (from subdirectories)")
    all_skills = registry.get_all_manifests()
    for m in all_skills:
        has_rules = "✓" if registry.get_rules(m.name) else "✗"
        bd = registry.get_priority_breakdown(m.name)
        print(f"  [{has_rules}] {m.name:24s}  v{m.version:6s}  "
              f"price={m.price_points}  staked={bd['staked_points']:.0f}  "
              f"tags={m.tags}")
    print(f"\n  Total: {len(all_skills)} skills loaded from manifests/")

    # ── 2. Context Injection (Document-Driven) ───────────────────────────
    print_sep("2. Context Injection — rules.md into LLM")

    prompts = [
        "Scrape Amazon for wireless noise cancelling headphones competitor data",
        "Audit this Solidity contract for reentrancy: contract Foo { function bar() public { msg.sender.call{value: 1}(''); } }",
        "Analyze the sales data CSV and give me a full report",
    ]

    for prompt in prompts:
        result = router.route(prompt)

        # Show the injected context (first 500 chars)
        context_preview = result.context[:600]
        if len(result.context) > 600:
            context_preview += "\n  … (truncated)"

        print(f"\n  Prompt: \"{prompt[:60]}...\"")
        print(f"  Domain: {result.domain}")
        print(f"  Candidates: {result.total_candidates}  |  "
              f"Discarded: {result.filtered_out}  |  "
              f"Injected: {len(result.skill_names)} (max 3)")
        print(f"  Skills injected: {result.skill_names}")
        print(f"  Context preview:\n{context_preview}")
        print()

    # ── 3. Tool Definitions (for LLM function calling) ──────────────────
    print_sep("3. Tool Definitions (LLM Function Calling)")
    tools = registry.to_anthropic_tools()
    for t in tools:
        print(f"  Tool: {t['name']}")
        print(f"    Description: {t['description'][:80]}...")
        props = t['input_schema'].get('properties', {})
        print(f"    Parameters: {', '.join(props.keys())}")
        print()

    # ── 4. Sandbox Execution — amazon_scraper ────────────────────────────
    print_sep("4. Sandbox Execution — amazon_scraper")

    amazon_m = registry.get("amazon_scraper")
    if amazon_m:
        print("  Executing amazon_scraper with search_term='wireless headphones'...")
        receipt = engine.execute(amazon_m, {"search_term": "wireless headphones", "max_results": 3})

        if receipt.status == "SUCCESS":
            data = json.loads(receipt.output)
            print(f"  Status: ✓ SUCCESS ({receipt.compute_consumed:.2f}s)")
            print(f"  Products found: {data['total_found']}")
            for p in data['products']:
                print(f"    • {p['title'][:55]:55s}  ${p['price']:>6.2f}  "
                      f"★{p['rating']}  ({p['review_count']:,} reviews)")
        else:
            print(f"  Status: ✗ FAILED — {receipt.error_message}")

    # ── 5. Sandbox Execution — code_security_audit ──────────────────────
    print_sep("5. Sandbox Execution — code_security_audit")

    security_m = registry.get("code_security_audit")
    if security_m:
        source = "contract Foo { function bar() public { msg.sender.call{value: 1}(''); } }"
        print("  Analyzing Solidity contract for vulnerabilities...")
        receipt = engine.execute(security_m, {"source_code": source, "contract_name": "Foo"})
        if receipt.status == "SUCCESS":
            print(f"  Status: ✓ SUCCESS ({receipt.compute_consumed:.2f}s)")
            print(f"  Report preview:\n{receipt.output[:400]}...")
        else:
            print(f"  Status: ✗ FAILED — {receipt.error_message}")

    # ── 6. Cool-Down Jail Demo ─────────────────────────────────────────
    print_sep("6. Cool-Down Jail — 3 Strikes")

    jail_skill = "buggy_skill"
    for attempt in range(1, 4):
        jail_info = registry.record_execution(jail_skill, success=False, slashed=2.0)
        bd = registry.get_priority_breakdown(jail_skill)
        jail_flag = " 🚫 JAILED!" if jail_info.get("jailed") else ""
        print(f"  Strike {attempt}: staked={bd['staked_points']:.1f}  "
              f"failures={jail_info['consecutive_failures']}{jail_flag}")

    # Verify jail
    active = [m.name for m in registry.get_all_manifests()]
    assert jail_skill not in active, f"BUG: {jail_skill} should be frozen!"
    print(f"  ✓ '{jail_skill}' filtered out — {len(active)} active skills remain")

    # ── 7. Dynamic Billing (Gas-Based) ────────────────────────────────────
    print_sep("7. Dynamic Billing — Gas Meter & Itemised Receipt")

    from src.ledger.mock_counter import MockLedger, BASE_GAS_RATE

    ledger = MockLedger()
    ledger.seed_usdt("alice", 100.00)
    print(f"\n  {'Alice initial:':28s} ${ledger.get_user_usdt('alice'):>7.2f} USDT")

    amazon_m = registry.get("amazon_scraper")
    assert amazon_m is not None
    dev_premium = float(amazon_m.price_points)
    max_budget = 1.00

    print(f"  {'Skill:':28s} amazon_scraper")
    print(f"  {'Developer premium:':28s} ${dev_premium:.2f} USDT")
    print(f"  {'Max budget (escrow hold):':28s} ${max_budget:.2f} USDT")
    print(f"  {'Gas rate:':28s} ${BASE_GAS_RATE:.2f} USDT/s")

    # ── Scenario A: SUCCESS → dynamic billing ─────────────────────
    hold = ledger.create_escrow_hold("alice", max_budget)
    assert hold is not None
    print(f"\n  ═══ SCENARIO A: SUCCESS ═══")
    print(f"  {'Escrow hold:':28s} {hold.escrow_id}  (${hold.max_budget:.2f} frozen)")
    print(f"  {'Alice after hold:':28s} ${ledger.get_user_usdt('alice'):>7.2f} USDT")

    receipt = engine.execute(amazon_m, {"search_term": "wireless headphones", "max_results": 3})
    assert receipt.status == "SUCCESS"

    detail = ledger.release_escrow_dynamic(
        hold.escrow_id,
        user_id="alice",
        developer_id="dev_alice",
        execution_time=receipt.execution_time,
        skill_meta={"compute_tier": 1, "developer_premium": dev_premium, "skill_id": "amazon_scraper"},
        success=True,
    )
    assert detail is not None

    print(f"  {'Execution time:':28s} {detail.execution_time:.2f}s")
    print(f"  {'┌─ Billing Receipt ─────────────────────┐'}")
    print(f"  │ {'Gas cost':22s} ${detail.gas_cost:>6.4f} USDT  │")
    print(f"  │ {'Developer premium':22s} ${detail.developer_premium:>6.2f} USDT   │")
    print(f"  │ {'Total cost':22s} ${detail.total_cost:>6.2f} USDT   │")
    print(f"  │ {'Platform tax (1%)':22s} ${detail.platform_tax:>6.2f} USDT   │")
    print(f"  │ {'Dev payout (99%)':22s} ${detail.developer_payout:>6.2f} USDT   │")
    print(f"  ├──────────────────────────────────────────┤")
    print(f"  │ {'Unused refund → alice':22s} ${detail.unused_refund:>6.2f} USDT   │")
    print(f"  └──────────────────────────────────────────┘")

    # ── Scenario B: FAILED → 100% refund ─────────────────────────
    hold2 = ledger.create_escrow_hold("alice", 0.50)
    assert hold2 is not None
    print(f"\n  ═══ SCENARIO B: FAILED ═══")
    print(f"  {'Escrow hold:':28s} {hold2.escrow_id}  (${hold2.max_budget:.2f} frozen)")
    print(f"  {'Alice after hold:':28s} ${ledger.get_user_usdt('alice'):>7.2f} USDT")

    detail2 = ledger.release_escrow_dynamic(
        hold2.escrow_id,
        user_id="alice",
        developer_id="dev_alice",
        execution_time=0.0,
        skill_meta={"compute_tier": 1, "developer_premium": 0.0, "skill_id": ""},
        success=False,
    )
    assert detail2 is not None

    print(f"  {'Outcome:':28s} {detail2.outcome} — 100% back")
    print(f"  {'Refund:':28s} ${detail2.unused_refund:>6.2f} USDT → alice")
    print(f"  {'Alice after refund:':28s} ${ledger.get_user_usdt('alice'):>7.2f} USDT")

    # ── Final audit ───────────────────────────────────────────────
    alice_end = ledger.get_user_usdt("alice")
    dev_end = ledger.get_dev_usdt("dev_alice")
    treasury = ledger.founder_treasury_usdt
    total = alice_end + dev_end + treasury
    print(f"\n  ── Final Balance Sheet ──")
    print(f"  {'Alice:':28s} ${alice_end:>7.2f} USDT")
    print(f"  {'Developer (dev_alice):':28s} ${dev_end:>7.2f} USDT")
    print(f"  {'Founder Treasury:':28s} ${treasury:>7.2f} USDT")
    print(f"  {'Total in system:':28s} ${total:>7.2f} USDT  "
          f"{'✓' if abs(total - 100.00) < 0.01 else '✗ MISSING!'}")

    # ── 8. Health Report ────────────────────────────────────────────────
    print_sep("8. Registry Health Report")
    report = registry.health_report()
    print(f"  Status: {report['status']}")
    print(f"  Active skills: {report['manifest_count']}")
    print(f"  With rules.md: {report['skills_with_rules']}")
    print(f"  Frozen: {report['frozen_skills']}")
    for m in registry.get_all_manifests():
        has_rules = "✓" if registry.get_rules(m.name) else "✗"
        bd = registry.get_priority_breakdown(m.name)
        print(f"    [{has_rules}] {m.name:24s}  freq={bd['usage_frequency']}  "
              f"staked={bd['staked_points']:.1f}")

    print()
    print("=" * 70)
    print("  Document-Driven Architecture ✓  All systems operational.")
    print("=" * 70)
    print()


if __name__ == "__main__":
    main()
