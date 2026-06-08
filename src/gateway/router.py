"""Gateway Router — Layer 3.

The universal entry point of AIMS. Receives a user's natural-language prompt,
detects the intent domain, filters the top-3 highest-priority skills,
injects ONLY those into the LLM's tools parameter, lets the model natively
select and chain skills, executes them under verified escrow, and returns
the aggregated result.

Flow:
  1. Detect intent domain from prompt (keyword matching)
  2. Rank skills by Priority_Score = Frequency + (Staked × 10)
  3. Inject only top-3 matching skill manifests as LLM tools
  4. LLM selects tools via native function calling
  5. Freeze points (MockLedger)
  6. Execute via WorkflowEngine (try-except + output validation)
  7. Settle: SUCCESS → transfer | FAILED → refund + slash
  8. Track consecutive failures → jail if >=3
  9. Return result
"""

from __future__ import annotations

import logging
import types
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol

from src.skills.manifest import SkillManifest
from src.skills.registry import SkillRegistry, detect_domain
from src.runtime.sandbox import WorkflowEngine, ExecutionReceipt
from src.ledger.mock_counter import MockLedger

logger = logging.getLogger(__name__)


# ── types ──────────────────────────────────────────────────────────────────


class RouteError(Exception):
    """Raised when routing fails irrecoverably."""


@dataclass
class RouteResult:
    """The outcome of routing a user prompt through the gateway."""

    prompt: str
    domain: str = ""
    skill_calls: List["SkillCall"] = field(default_factory=list)
    final_output: str = ""
    error: Optional[str] = None


@dataclass
class SkillCall:
    """A single skill invocation selected by the LLM."""

    skill_name: str
    arguments: Dict[str, Any]
    receipt: Optional[ExecutionReceipt] = None
    error: Optional[str] = None


# ── LLM Provider Protocol ─────────────────────────────────────────────────


class LLMProvider(Protocol):
    """Protocol that any LLM client must satisfy for use with GatewayRouter."""

    def invoke(
        self,
        prompt: str,
        tools: List[Dict[str, Any]],
    ) -> Any:
        ...

    def parse_calls(self, response: Any) -> List[SkillCall]:
        ...

    def compose_final_output(self, response: Any) -> str:
        ...


class AnthropicProvider:
    """Adapter for the Anthropic Python SDK (Claude)."""

    def __init__(
        self,
        client: Any,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 4096,
    ) -> None:
        self._client = client
        self._model = model
        self._max_tokens = max_tokens

    def invoke(self, prompt: str, tools: List[Dict[str, Any]]) -> Any:
        return self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            tools=tools,
            messages=[{"role": "user", "content": prompt}],
        )

    def parse_calls(self, response: Any) -> List[SkillCall]:
        calls: List[SkillCall] = []
        for block in response.content:
            if block.type == "tool_use":
                calls.append(SkillCall(skill_name=block.name, arguments=dict(block.input)))
        return calls

    def compose_final_output(self, response: Any) -> str:
        texts = [b.text for b in response.content if getattr(b, "type", None) == "text"]
        return "\n".join(texts)


# ── Mock provider (standalone / demo mode) ────────────────────────────────


class _MockContent(types.SimpleNamespace):
    def __init__(self, name: str, **kwargs):
        self.type = "tool_use"
        self.name = name
        self.input = kwargs if kwargs else {"mock": "arg"}


class MockLLMProvider:
    """Standalone mock LLM for demo/testing. Always calls the first available tool."""

    def invoke(self, prompt: str, tools: List[Dict[str, Any]]) -> Any:
        if not tools:
            return _MockProviderResponse([])
        # Simulate LLM calling the first available tool
        return _MockProviderResponse([t["name"] for t in tools[:1]])

    def parse_calls(self, response: Any) -> List[SkillCall]:
        return [SkillCall(skill_name=name, arguments={}) for name in response._tool_names]

    def compose_final_output(self, response: Any) -> str:
        return "Mock LLM chose tool(s): " + ", ".join(response._tool_names)


class _MockProviderResponse:
    """Duck-typed mock of an Anthropic message response."""

    def __init__(self, tool_names: List[str]):
        self._tool_names = tool_names
        self.content = [_MockContent(n) for n in tool_names]


# ── Gateway Router ────────────────────────────────────────────────────────

SkillExecutor = Callable[[SkillManifest, Dict[str, Any]], str]


class GatewayRouter:
    """Universal entry point for AIMS with intent-aware filtering and escrow.

    Usage:
        registry = SkillRegistry()
        ledger = MockLedger()
        router = GatewayRouter(registry, ledger, executor_fn)
        result = router.route("audit this contract for reentrancy")
        print(result.final_output)
    """

    def __init__(
        self,
        registry: SkillRegistry,
        ledger: MockLedger,
        executor: SkillExecutor,
        workflow_engine: Optional[WorkflowEngine] = None,
        llm_provider: Optional[LLMProvider] = None,
        mock_user: str = "alice",
        mock_developer: str = "aims_seed",
    ) -> None:
        self._registry = registry
        self._ledger = ledger
        self._workflow_engine = workflow_engine or WorkflowEngine(executor)
        self._llm_provider = llm_provider
        self._mock_user = mock_user
        self._mock_developer = mock_developer

    # ── public API ──────────────────────────────────────────────────────

    def parse_intent_to_workflow(self, prompt: str) -> List[Dict[str, Any]]:
        """Detect intent, filter top-3 skills, return tool definitions.

        Priority_Score = Usage_Frequency + (Staked_Points × 10)
        """
        all_manifests = self._registry.get_all_manifests()
        logger.info("=== Priority Score Breakdown ===")
        for m in all_manifests:
            bd = self._registry.get_priority_breakdown(m.name)
            logger.info(
                "  %s: score=%.1f (freq=%d, staked=%.1f)",
                bd["skill"], bd["priority_score"],
                bd["usage_frequency"], bd["staked_points"],
            )

        top_3 = self._registry.get_top_for_domain(prompt, limit=3)
        logger.info("Injecting top %d skills: %s", len(top_3), [m.name for m in top_3])
        return self._registry.to_anthropic_tools(top_3)

    def route(self, prompt: str) -> RouteResult:
        """Route a user prompt through the full AIMS pipeline with escrow."""
        result = RouteResult(prompt=prompt)
        domain = detect_domain(prompt)
        result.domain = domain

        # Step 1 — Get top-3 tool definitions
        tool_defs = self.parse_intent_to_workflow(prompt)
        if not tool_defs:
            result.error = "No matching skills available."
            return result

        # Step 2 — Resolve provider (fall back to mock for standalone)
        provider = self._llm_provider or MockLLMProvider()

        # Step 3 — LLM selects tools
        response = provider.invoke(prompt, tool_defs)
        skill_calls = provider.parse_calls(response)
        if not skill_calls:
            result.final_output = provider.compose_final_output(response)
            return result

        # Step 4–8 — Execute each skill under escrow
        for call in skill_calls:
            manifest = self._registry.get(call.skill_name)
            if manifest is None:
                call.error = f"Skill '{call.skill_name}' not found (frozen or missing)"
                result.skill_calls.append(call)
                continue

            # 4a — Freeze points
            freeze = self._ledger.freeze_points(
                user=self._mock_user,
                developer=self._mock_developer,
                skill_name=manifest.name,
                points=manifest.price_points,
            )
            if freeze is None and manifest.price_points > 0:
                call.error = f"Insufficient balance for {manifest.name}"
                result.skill_calls.append(call)
                continue

            # 4b — Execute with verification
            receipt = self._workflow_engine.execute(manifest, call.arguments)
            call.receipt = receipt

            # 4c — Settle based on receipt
            if freeze:
                staked = manifest.staked_points
                self._ledger.settle_transaction(freeze.freeze_id, receipt, dev_staked_points=staked)

            # 4d — Track in registry (scoring + jail)
            success = receipt.status == "SUCCESS"
            slashed = 2.0 if not success else 0.0
            jail_event = self._registry.record_execution(manifest.name, success, slashed=slashed)

            if jail_event.get("jailed"):
                logger.warning(
                    "🚫 SKILL '%s' SENT TO COOL-DOWN JAIL for %d hours! "
                    "(consecutive_failures=%d)",
                    manifest.name,
                    jail_event["jail_duration_hours"],
                    jail_event["consecutive_failures"],
                )

            if not success:
                call.error = receipt.error_message

            result.skill_calls.append(call)

        # Step 5 — Compose output
        outputs = [f"[Domain: {domain}]"]
        for call in result.skill_calls:
            if call.error:
                outputs.append(f"[{call.skill_name}] FAILED: {call.error}")
            elif call.receipt:
                outputs.append(
                    f"[{call.skill_name}] SUCCESS ({call.receipt.compute_consumed:.3f}s)\n{call.receipt.output}"
                )
            else:
                outputs.append(f"[{call.skill_name}] No receipt")

        result.final_output = "\n\n---\n\n".join(outputs)
        return result
