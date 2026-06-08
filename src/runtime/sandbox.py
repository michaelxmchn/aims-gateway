"""Execution Sandbox — Layer 4.

Receives LLM-triggered tool calls, looks up the skill implementation,
executes it under try-except, validates output against the manifest's
output_schema, and returns an ExecutionReceipt.

Also hosts the **DePIN Worker Node** loop — a background daemon that
polls the Task Broker for work, executes skills, and settles escrow
to claim gas fees.
"""

from __future__ import annotations

import json
import logging
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from src.skills.manifest import SkillManifest

logger = logging.getLogger(__name__)


@dataclass
class ExecutionReceipt:
    """Immutable record of a single skill execution attempt."""

    skill_name: str
    status: str  # "SUCCESS" | "FAILED"
    error_message: str = ""
    compute_consumed: float = 0.0
    output: str = ""
    execution_time: float = 0.0
    """Wall-clock seconds measured via time.time() for dynamic billing."""


# ── Output validator ─────────────────────────────────────────────────────


def _build_output_validator(output_schema: Dict[str, Any]) -> Callable[[str], bool]:
    """Build a validator from JSON Schema to verify string output."""

    def validate(output: str) -> bool:
        schema_type = output_schema.get("type", "string")
        if schema_type == "object":
            try:
                data = json.loads(output)
                if "properties" in output_schema:
                    for prop_name, prop_schema in output_schema["properties"].items():
                        if prop_schema.get("required", False) and prop_name not in data:
                            logger.warning("Output validation: missing required field '%s'", prop_name)
                            return False
                return True
            except (json.JSONDecodeError, ValueError):
                return False
        elif schema_type == "string":
            return len(output.strip()) > 0
        elif schema_type == "array":
            try:
                data = json.loads(output)
                return isinstance(data, list)
            except (json.JSONDecodeError, ValueError):
                return False
        return True

    return validate


# ── WorkflowEngine ───────────────────────────────────────────────────────


class WorkflowEngine:
    """Executes skills with strict error handling and output verification.

    The executor_fn receives (manifest, arguments) and returns a string
    output. WorkflowEngine wraps it with try-except + schema validation.
    """

    def __init__(self, executor_fn: Callable[[SkillManifest, Dict[str, Any]], str]) -> None:
        self._executor_fn = executor_fn

    def execute(self, manifest: SkillManifest, arguments: Dict[str, Any]) -> ExecutionReceipt:
        """Execute a skill and return a verified receipt."""
        wall_start = time.time()
        start = time.perf_counter()
        skill_name = manifest.name

        try:
            output = self._executor_fn(manifest, arguments)
            compute_consumed = time.perf_counter() - start
            execution_time = time.time() - wall_start
        except Exception as exc:
            compute_consumed = time.perf_counter() - start
            execution_time = time.time() - wall_start
            logger.error("Skill '%s' raised exception: %s", skill_name, exc)
            return ExecutionReceipt(
                skill_name=skill_name,
                status="FAILED",
                error_message=f"{type(exc).__name__}: {exc}",
                compute_consumed=compute_consumed,
                execution_time=execution_time,
            )

        # Validate output against schema
        if manifest.output_schema is not None:
            validator = _build_output_validator(manifest.output_schema)
            if not validator(output):
                logger.warning(
                    "Skill '%s' output failed schema validation (consumed=%.3fs)",
                    skill_name, compute_consumed,
                )
                return ExecutionReceipt(
                    skill_name=skill_name,
                    status="FAILED",
                    error_message="Output failed schema validation",
                    compute_consumed=compute_consumed,
                )

        return ExecutionReceipt(
            skill_name=skill_name,
            status="SUCCESS",
            output=output,
            compute_consumed=compute_consumed,
            execution_time=execution_time,
        )


# ── Built-in skill implementations ──────────────────────────────────────


def _amazon_scraper_impl(arguments: Dict[str, Any]) -> str:
    """Simulate scraping Amazon product listings.

    In production, this would use requests + BeautifulSoup/Playwright.
    For MVP, returns realistic mock data to demonstrate the pipeline.
    """
    search_term = arguments.get("search_term", "unknown")
    max_results = min(int(arguments.get("max_results", 10)), 50)

    # Simulate variable network latency (0.5-2.5s)
    time.sleep(random.uniform(0.5, 2.5))

    mock_products = [
        {
            "title": f"{search_term.title()} Premium Edition",
            "asin": f"B0{chr(65+i)}3ZZ8ZZ",
            "price": round(29.99 + i * 15.0, 2),
            "currency": "USD",
            "rating": round(4.5 - (i * 0.15), 1),
            "review_count": 15000 - i * 1200,
            "seller": "Amazon.com",
            "prime_eligible": True,
            "sponsored": i == 0,
            "url": f"https://www.amazon.com/dp/B0{chr(65+i)}3ZZ8ZZ",
        }
        for i in range(min(max_results, 10))
    ]

    return json.dumps({
        "search_term": search_term,
        "total_found": len(mock_products),
        "products": mock_products,
    }, indent=2)


def _git_changelog_impl(arguments: Dict[str, Any]) -> str:
    """Generate a changelog from git history."""
    repo_path = arguments.get("repo_path", ".")
    from_ref = arguments.get("from_ref", "")
    to_ref = arguments.get("to_ref", "HEAD")

    import subprocess
    try:
        log_cmd = ["git", "log", f"{from_ref}..{to_ref}", "--oneline", "--no-merges"]
        result = subprocess.run(
            log_cmd,
            capture_output=True, text=True, timeout=15,
            cwd=repo_path,
        )
        if result.returncode != 0:
            return f"Error: {result.stderr.strip()}"
        commits = result.stdout.strip()
        if not commits:
            return f"No changes between {from_ref} and {to_ref}."

        lines = commits.split("\n")
        changelog = f"# Changelog ({from_ref} → {to_ref})\n\n"
        sections = {"feat": "Features", "fix": "Bug Fixes", "other": "Maintenance"}
        grouped = {v: [] for v in sections.values()}

        for line in lines:
            for prefix, section in sections.items():
                if line.startswith(prefix):
                    grouped[section].append(line)
                    break
            else:
                grouped["Maintenance"].append(line)

        for section, items in grouped.items():
            if items:
                changelog += f"## {section}\n"
                for item in items:
                    changelog += f"- {item}\n"
                changelog += "\n"

        return changelog
    except FileNotFoundError:
        return "Error: git not found in PATH. Is git installed?"
    except subprocess.TimeoutExpired:
        return "Error: git log timed out (large range)."


def _code_security_audit_impl(arguments: Dict[str, Any]) -> str:
    """Analyze Solidity source code for vulnerabilities."""
    source = arguments.get("source_code", "")
    contract = arguments.get("contract_name", "Unknown")

    findings = []
    if "msg.sender.call" in source and "require(" not in source.split("msg.sender.call")[-1][:200]:
        findings.append({
            "severity": "CRITICAL",
            "title": "Potential Reentrancy Vulnerability",
            "lines": "12-15",
            "description": "External call to msg.sender without reentrancy guard. "
                           "An attacker can re-enter the function before state updates.",
            "recommendation": "Use ReentrancyGuard from OpenZeppelin or apply "
                              "the checks-effects-interactions pattern."
        })
    if "tx.origin" in source:
        findings.append({
            "severity": "HIGH",
            "title": "Use of tx.origin for Authentication",
            "lines": "8",
            "description": "tx.origin is deprecated and can be exploited in "
                           "man-in-the-middle attacks via intermediary contracts.",
            "recommendation": "Use msg.sender instead of tx.origin."
        })

    report = f"# Security Audit Report: {contract}\n\n"
    report += "## Summary\n"
    report += f"- **Files analyzed**: 1\n"
    report += f"- **Total issues**: {len(findings)}\n"
    report += f"- **Critical**: {sum(1 for f in findings if f['severity'] == 'CRITICAL')}\n"
    report += f"- **High**: {sum(1 for f in findings if f['severity'] == 'HIGH')}\n\n"

    if findings:
        report += "## Findings\n\n"
        for f in findings:
            report += f"### [{f['severity']}] {f['title']}\n"
            report += f"- **Lines**: {f['lines']}\n"
            report += f"- **Description**: {f['description']}\n"
            report += f"- **Recommendation**: {f['recommendation']}\n\n"

    report += "## Conclusion\n"
    if not findings:
        report += "No significant vulnerabilities detected in this analysis.\n"
    else:
        report += "Issues found. Review and address the findings above.\n"

    return report


# ── Skill Implementations Registry ──────────────────────────────────────

SKILL_IMPLS: Dict[str, Callable[[Dict[str, Any]], str]] = {
    "amazon_scraper": _amazon_scraper_impl,
    "git_changelog": _git_changelog_impl,
    "code_security_audit": _code_security_audit_impl,
}


def resolve_impl(manifest: SkillManifest, arguments: Dict[str, Any]) -> str:
    """Resolve and execute a skill implementation.

    Looks up SKILL_IMPLS by manifest.name. If not found, returns
    a descriptive fallback that the AI can use for context.
    """
    impl = SKILL_IMPLS.get(manifest.name)
    if impl is None:
        return (
            f"[{manifest.name}] No local implementation registered.\n"
            f"Input: {json.dumps(arguments, indent=2)}\n"
            f"The AI client should implement this skill's logic per its rules.md."
        )
    return impl(arguments)


# ── DePIN Worker Node ────────────────────────────────────────────────────


def start_worker_loop(
    worker_id: str,
    ledger: "MockLedger",
    broker: "TaskBroker",
    engine: WorkflowEngine,
    manifest: SkillManifest,
    stop_event: threading.Event,
    crash_simulate_after: Optional[float] = None,
    corrupt_output: bool = False,
) -> None:
    """Background worker daemon — claims tasks and settles escrow.

    Runs in an infinite loop (until *stop_event* is set):
      1. Claim a task via ``broker.claim_task(worker_id)``.
      2. Execute the skill via ``engine.execute()``.
      3. **Proof-of-Result** — parse output and validate via
         ``broker.validate_task_result()``. If the result is invalid,
         mark the task as FAILED.
      4. Call ``ledger.release_escrow_dynamic()`` to claim gas fees
         to this worker's ``worker_id`` balance.
      5. Call ``broker.complete_task()`` with the final status.

    If *crash_simulate_after* is set, the worker will sleep that many
    seconds *after* claiming the task (simulating an abrupt drop-off)
    so the broker's timeout recovery can recycle the abandoned task.

    If *corrupt_output* is ``True``, the worker replaces the engine
    output with ``{"price": -10}`` to trigger validation failure.
    """
    from src.gateway.broker import TaskBroker
    from src.ledger.mock_counter import MockLedger

    logger.info("Worker '%s' online — claiming tasks ...", worker_id)

    while not stop_event.is_set():
        task_dict = broker.claim_task(worker_id)
        if task_dict is None:
            time.sleep(0.5)
            continue

        task_id = task_dict["task_id"]
        asin = task_dict["asin"]
        premium = task_dict["developer_premium"]
        escrow_hold = task_dict["escrow_hold"]

        logger.info(
            "WORKER %s claimed %s (asin=%s, premium=$%.2f)",
            worker_id, task_id, asin, premium,
        )

        # ── Simulate worker crash (abandon the task) ──────────────
        if crash_simulate_after is not None and crash_simulate_after >= 0:
            logger.warning(
                "WORKER %s CRASH SIMULATION — sleeping %.1fs before execution",
                worker_id, crash_simulate_after,
            )
            time.sleep(crash_simulate_after)
            # Task is still CLAIMED — broker.check_timeouts() will recycle it

        receipt = engine.execute(
            manifest,
            {"search_term": asin, "max_results": 1},
        )

        # ── Corrupt output (for penalty testing) ──────────────────
        if corrupt_output and receipt.status == "SUCCESS":
            receipt = ExecutionReceipt(
                skill_name=receipt.skill_name,
                status="SUCCESS",
                output='{"price": -10}',
                compute_consumed=receipt.compute_consumed,
                execution_time=receipt.execution_time,
            )

        # ── Proof-of-Result validation ────────────────────────────
        result_status = receipt.status
        if result_status == "SUCCESS":
            try:
                parsed = json.loads(receipt.output)
                # Extract the first product from the products array
                # for validation (asin + price live on each product)
                products = parsed.get("products", []) if isinstance(parsed, dict) else []
                sample = products[0] if products else {}
                if not broker.validate_task_result(task_id, sample):
                    result_status = "FAILED"
            except (json.JSONDecodeError, TypeError, IndexError) as exc:
                logger.warning(
                    "WORKER %s unparseable output for %s: %s",
                    worker_id, task_id, exc,
                )
                result_status = "FAILED"

        detail = ledger.release_escrow_dynamic(
            escrow_hold.escrow_id,
            user_id=task_dict["user_id"],
            developer_id=worker_id,
            execution_time=receipt.execution_time,
            developer_premium=premium,
            success=result_status == "SUCCESS",
            skill_id=task_dict.get("skill_id", ""),
        )

        if detail is not None:
            broker.complete_task(task_id, result_status, detail)
            logger.info(
                "WORKER %s completed %s — earned $%.2f USDT  "
                "[gas=$%.4f  premium=$%.2f]  status=%s",
                worker_id, task_id, detail.developer_payout,
                detail.gas_cost, detail.developer_premium,
                result_status,
            )

    logger.info("Worker '%s' shutting down.", worker_id)
