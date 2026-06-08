"""Gateway Router — Layer 3 (Lightweight Context Provider).

Strict Top-3 filtering pipeline:

  1. Detect intent domain from user prompt (keyword matching)
  2. Load all skills, EXCLUDE those in cool-down jail (frozen_until > now)
  3. Score each by Priority = Usage_Frequency + (Staked_Points × 10)
  4. Filter by domain tag match (if domain keywords exist)
  5. Sort descending, keep ONLY top 3
  6. Extract rules.md from each → concatenate into LLM context string
  7. Return tool definitions for native function calling

Rules: discard non-matching, low-priority, and jailed skills before
the LLM ever sees them — saves token costs and prevents distraction.
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
    total_candidates: int = 0   # How many skills were considered
    filtered_out: int = 0       # How many were discarded (jail/domain/rank)
    error: Optional[str] = None


class GatewayRouter:
    """Lightweight context provider — strict top-3 filtering, no LLM invocation.

    Usage:
        router = GatewayRouter(registry)
        result = router.route("scrape Amazon for wireless headphones")
        # result.context   → concatenated rules.md for the LLM's system prompt
        # result.tool_defs → tool definitions for LLM function calling
        # result.skill_names → which skills made the cut
    """

    MAX_SKILLS: int = 3
    """Hard limit: never inject more than this many skills into context."""

    def __init__(self, registry: SkillRegistry) -> None:
        self._registry = registry

    # ── public API ──────────────────────────────────────────────────────

    def route(self, prompt: str) -> RouteResult:
        """Route a prompt through the strict top-3 filtering pipeline."""
        result = RouteResult(prompt=prompt)
        domain = detect_domain(prompt)
        result.domain = domain

        # Step 1 — Get top-N (scored, filtered, sorted, jailed excluded)
        top_skills = self._registry.get_top_rules(prompt, limit=self.MAX_SKILLS)
        all_manifests = self._registry.get_all_manifests()

        result.total_candidates = len(all_manifests)
        result.filtered_out = max(0, result.total_candidates - len(top_skills))

        if not top_skills:
            result.error = "No matching skills available."
            logger.warning(
                "No skills matched prompt='%s' domain='%s' "
                "(total=%d, filtered=%d)",
                prompt, domain, result.total_candidates, result.filtered_out,
            )
            return result

        # Step 2 — Build context from ONLY the top 3
        result.skill_names = [s["name"] for s in top_skills]
        result.tool_defs = [s["tool_def"] for s in top_skills]
        result.context = self._build_context(top_skills)

        logger.info(
            "Routed prompt → domain='%s' "
            "top=%s (kept=%d, discarded=%d/%d, jailed=auto-excluded)",
            domain,
            result.skill_names,
            len(top_skills),
            result.filtered_out,
            result.total_candidates,
        )
        return result

    # ── internal helpers ───────────────────────────────────────────────

    @staticmethod
    def _build_context(top_skills: List[Dict[str, Any]]) -> str:
        """Concatenate rules.md from top-N skills into a single context string.

        Each skill's rules.md is placed under its own heading so the LLM
        can clearly distinguish which rules belong to which capability.
        """
        parts: List[str] = []
        parts.append("# Available Skills\n")

        for skill in top_skills:
            parts.append("---")
            parts.append(f"## Skill: {skill['name']}")
            parts.append(f"> {skill['description']}")
            parts.append("")
            if skill["rules_md"]:
                parts.append(skill["rules_md"])
            parts.append("")

        return "\n".join(parts)
