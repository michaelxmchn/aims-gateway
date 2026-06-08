"""Gateway Router — Layer 3.

The universal entry point of AIMS. Receives a user's natural-language prompt,
dynamically injects all available Skill manifests into the LLM's tools parameter,
lets the model natively select and chain skills, executes them, and returns the
aggregated result.

Flow:
  1. Load manifests from SkillRegistry
  2. Convert to LLM tool definitions (inject into `tools` param)
  3. Send prompt + tools to the LLM
  4. Parse tool_use / function_call responses
  5. Execute each called skill via SkillRuntime
  6. (Optional) feed results back to LLM for multi-turn chaining
  7. Return final result to user
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol, Union

from src.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)


# ── types ──────────────────────────────────────────────────────────────────


class RouteError(Exception):
    """Raised when routing fails irrecoverably."""


@dataclass
class RouteResult:
    """The outcome of routing a user prompt through the gateway."""

    prompt: str
    skill_calls: List["SkillCall"] = field(default_factory=list)
    final_output: str = ""
    error: Optional[str] = None


@dataclass
class SkillCall:
    """A single skill invocation selected by the LLM."""

    skill_name: str
    arguments: Dict[str, Any]
    result: Optional[str] = None
    error: Optional[str] = None
    duration_ms: float = 0.0


# ── provider adapters ─────────────────────────────────────────────────────


class LLMProvider(Protocol):
    """Protocol that any LLM client must satisfy for use with GatewayRouter."""

    def invoke(
        self,
        prompt: str,
        tools: List[Dict[str, Any]],
    ) -> Any:
        """Send a prompt + tool definitions and return the model response."""
        ...

    def parse_calls(self, response: Any) -> List[SkillCall]:
        """Extract tool calls from the raw model response.

        Returns a list of SkillCall with skill_name + arguments filled in.
        """
        ...

    def compose_final_output(self, response: Any) -> str:
        """Extract the final text output from the raw model response."""
        ...


# ── built-in adapter: Anthropic SDK ───────────────────────────────────────


class AnthropicProvider:
    """Adapter for the Anthropic Python SDK (Claude)."""

    def __init__(
        self,
        client: Any,  # anthropic.Anthropic
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 4096,
    ) -> None:
        self._client = client
        self._model = model
        self._max_tokens = max_tokens

    def invoke(
        self,
        prompt: str,
        tools: List[Dict[str, Any]],
    ) -> Any:
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
                calls.append(SkillCall(
                    skill_name=block.name,
                    arguments=dict(block.input),
                ))
        return calls

    def compose_final_output(self, response: Any) -> str:
        texts = [b.text for b in response.content if getattr(b, "type", None) == "text"]
        return "\n".join(texts)


# ── Gateway Router ────────────────────────────────────────────────────────

import logging
SkillExecutor = Callable[[str, Dict[str, Any]], str]


class GatewayRouter:
    """Universal entry point for AIMS.

    Usage::

        registry = SkillRegistry()
        router = GatewayRouter(registry=registry, executor=my_executor)
        result = router.route("帮我审计这个合约有没有重入漏洞")
        print(result.final_output)
    """

    def __init__(
        self,
        registry: SkillRegistry,
        executor: SkillExecutor,
        llm_provider: Optional[LLMProvider] = None,
    ) -> None:
        self._registry = registry
        self._executor = executor
        self._llm_provider = llm_provider

    # ── public API ──────────────────────────────────────────────────────

    def route(self, prompt: str) -> RouteResult:
        """Route a user prompt through the AIMS pipeline.

        1. Injects available skill manifests into the LLM
        2. LLM selects zero or more skills to call
        3. Executes each skill locally
        4. Returns the aggregated result
        """
        result = RouteResult(prompt=prompt)
        manifests = self._registry.load_all()

        if not manifests:
            result.error = "No skills available. Try creating a skill first."
            return result

        # Step 1 — Inject manifests as tool definitions
        tool_defs = self._registry.to_anthropic_tools()

        if not tool_defs:
            result.error = "No valid tool definitions could be generated from available manifests."
            return result

        # Step 1a — Resolve the provider
        provider = self._llm_provider
        if provider is None:
            provider = self._resolve_provider()

        # Step 2 — Let the LLM decide which skills to invoke
        try:
            response = provider.invoke(prompt, tool_defs)
        except Exception as exc:
            result.error = f"LLM invocation failed: {exc}"
            return result

        # Step 3 — Parse tool calls
        skill_calls = provider.parse_calls(response)
        if not skill_calls:
            # LLM chose not to use any tool — return text response directly
            result.final_output = provider.compose_final_output(response)
            return result

        # Step 4 — Execute each called skill in order (serial DAG)
        for call in skill_calls:
            manifest = self._registry.get(call.skill_name)
            if manifest is None:
                call.error = f"Skill '{call.skill_name}' not found in registry"
                result.skill_calls.append(call)
                continue

            try:
                output = self._executor(manifest, call.arguments)
                call.result = output
            except Exception as exc:
                call.error = str(exc)

            result.skill_calls.append(call)

        # Step 5 — Compose final output
        outputs = []
        for call in result.skill_calls:
            if call.error:
                outputs.append(f"[{call.skill_name}] ERROR: {call.error}")
            else:
                outputs.append(f"[{call.skill_name}]\n{call.result}")

        result.final_output = "\n\n---\n\n".join(outputs)
        return result

    # ── internal ─────────────────────────────────────────────────────────

    def _resolve_provider(self) -> LLMProvider:
        """Auto-detect or default to a provider.

        In production the user's AI client (Claude Code / Cursor / Codex)
        supplies its own LLM — this fallback is for standalone testing.
        """
        raise RouteError(
            "No LLM provider configured. "
            "When running inside an AI client (Claude Code, Cursor, etc.), "
            "the client's native tool-calling machinery handles injection directly. "
            "Pass an explicit provider for standalone use."
        )
