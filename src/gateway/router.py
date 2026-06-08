"""Gateway Router — Layer 3 (Lightweight Context Provider).

No longer handles LLM invocation or complex AI parsing. Instead:

  1. Detect intent domain from user prompt
  2. Rank & filter relevant skills by priority score
  3. Return their rules.md as an injectable context string
  4. Return their tool definitions for LLM function calling

The calling AI client injects the context into its own LLM, which reads
the markdown rules natively and decides which skill tools to invoke.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.skills.registry import SkillRegistry, detect_domain

logger = logging.getLogger(__name__)


@dataclass
class RouteResult:
    """The outcome of routing a user prompt through the gateway."""

    prompt: str
    domain: str = ""
    context: str = ""           # Injected markdown context (rules.md)
    skill_names: List[str] = field(default_factory=list)
    tool_defs: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None


class GatewayRouter:
    """Lightweight context provider — filters skills, returns rules + tool defs.

    Usage:
        router = GatewayRouter(registry)
        result = router.route("scrape Amazon for wireless headphones")
        # result.context  → rules.md content to inject into LLM
        # result.tool_defs → tool definitions for LLM function calling
    """

    def __init__(self, registry: SkillRegistry) -> None:
        self._registry = registry

    # ── public API ──────────────────────────────────────────────────────

    def build_context(self, prompt: str, limit: int = 3) -> str:
        """Filter top-N skills and return their rules.md as a single context string.

        This string is designed to be injected into the LLM's system prompt
        or user message so the AI natively reads and understands the rules.
        """
        top_skills = self._registry.get_top_rules(prompt, limit=limit)
        if not top_skills:
            return ""

        parts: List[str] = []
        parts.append("# Available Skills\n")

        for skill in top_skills:
            parts.append(f"---")
            parts.append(f"## Skill: {skill['name']}")
            parts.append(f"> {skill['description']}")
            parts.append("")
            if skill["rules_md"]:
                parts.append(skill["rules_md"])
            parts.append("")

        return "\n".join(parts)

    def route(self, prompt: str, limit: int = 3) -> RouteResult:
        """Route a prompt — detect domain, filter skills, return context + tools."""
        result = RouteResult(prompt=prompt)
        domain = detect_domain(prompt)
        result.domain = domain

        top_skills = self._registry.get_top_rules(prompt, limit=limit)
        if not top_skills:
            result.error = "No matching skills available."
            return result

        result.skill_names = [s["name"] for s in top_skills]
        result.tool_defs = [s["tool_def"] for s in top_skills]
        result.context = self.build_context(prompt, limit=limit)

        logger.info(
            "Routed prompt → domain='%s' matched=%s",
            domain, result.skill_names,
        )
        return result
