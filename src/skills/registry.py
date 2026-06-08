"""Skill Registry — Layer 2.

Loads SkillManifests from the local manifests directory, provides
tool-definition injection, priority scoring, domain-based filtering,
consecutive-failure tracking, and cool-down jail management.

Extensions:
  - Priority_Score = Usage_Frequency + (Staked_Points × 10)
  - Cold-start promotion via staked_points
  - 3 consecutive failures → 24h jail (frozen_until)
  - Frozen skills excluded from load_all()
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.skills.manifest import SkillManifest, to_anthropic_tool_def, to_openai_tool_def

logger = logging.getLogger(__name__)

MANIFESTS_DIR = Path(__file__).resolve().parent / "manifests"


class RegistryError(Exception):
    """Raised when a registry operation fails."""


# ── keyword-based domain detection (MVP) ────────────────────────────────

DOMAIN_KEYWORDS: Dict[str, List[str]] = {
    "security": ["security", "audit", "vulnerability", "exploit", "hack", "solidity"],
    "git": ["git", "commit", "changelog", "log", "history", "repo", "branch"],
    "code": ["code", "generate", "review", "refactor", "implement", "function"],
    "data": ["data", "analysis", "query", "csv", "json", "database", "sql"],
    "devops": ["deploy", "ci", "cd", "docker", "kubernetes", "infra"],
    "writing": ["write", "article", "doc", "readme", "blog", "email"],
    "general": [],
}

# Register all tags as default - the catch-all domain


def detect_domain(prompt: str) -> str:
    """Classify a user prompt into a domain using simple keyword matching."""
    lower = prompt.lower()
    best_domain = "general"
    best_count = 0
    for domain, keywords in DOMAIN_KEYWORDS.items():
        if not keywords:
            continue
        count = sum(1 for kw in keywords if kw in lower)
        if count > best_count:
            best_count = count
            best_domain = domain
    return best_domain


# ── SkillRegistry ────────────────────────────────────────────────────────


class SkillRegistry:
    """Loads, validates, scores, and serves SkillManifests."""

    def __init__(self, manifests_dir: Path = MANIFESTS_DIR) -> None:
        self._manifests_dir = manifests_dir
        self._cache: Optional[Dict[str, SkillManifest]] = None

        # Runtime tracking (not persisted — resets on restart)
        self._usage_frequency: Dict[str, int] = {}
        self._consecutive_failures: Dict[str, int] = {}
        self._staked_points_override: Dict[str, float] = {}

    # ── loading (with frozen-skill filtering) ────────────────────────────

    def load_all(self) -> Dict[str, SkillManifest]:
        """Load manifests, excluding frozen skills (frozen_until > now)."""
        if self._cache is not None:
            return self._cache

        if not self._manifests_dir.is_dir():
            logger.warning("Manifests directory does not exist: %s", self._manifests_dir)
            self._cache = {}
            return self._cache

        raw_manifests: Dict[str, SkillManifest] = {}
        errors: List[str] = []
        now = time.time()

        for path in sorted(self._manifests_dir.glob("*.json")):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                # Apply runtime overrides before validation
                name = raw.get("name", "")
                if name in self._staked_points_override:
                    raw["staked_points"] = self._staked_points_override[name]
                if name in self._frozen_overrides:
                    raw["frozen_until"] = self._frozen_overrides[name]

                manifest = SkillManifest.model_validate(raw)
                if manifest.name in raw_manifests:
                    errors.append(f"Duplicate skill name '{manifest.name}' in {path.name}")
                raw_manifests[manifest.name] = manifest
            except Exception as exc:
                errors.append(f"{path.name}: {exc}")

        # Filter out frozen skills
        manifests: Dict[str, SkillManifest] = {}
        for name, m in raw_manifests.items():
            if m.is_frozen(now):
                logger.info("Skipping frozen skill '%s' (frozen_until=%s)", name, m.frozen_until)
                continue
            manifests[name] = m

        if errors:
            logger.warning("Loading completed with %d error(s)", len(errors))

        self._cache = manifests
        logger.info("Loaded %d skill(s) (%d frozen skipped)", len(manifests),
                     len(raw_manifests) - len(manifests))
        return manifests

    def reload(self) -> None:
        """Clear the cache and reload on next access."""
        self._cache = None

    def get(self, name: str) -> Optional[SkillManifest]:
        return self.load_all().get(name)

    def get_all_manifests(self) -> List[SkillManifest]:
        return list(self.load_all().values())

    # ── frozen-skills overrides (used during jail events) ─────────────────

    _frozen_overrides: Dict[str, float] = {}

    def _set_frozen(self, skill_name: str, until: float) -> None:
        self._frozen_overrides[skill_name] = until
        self.reload()

    # ── priority scoring ─────────────────────────────────────────────────

    def get_priority_score(self, name: str) -> float:
        """Priority_Score = Usage_Frequency + (Staked_Points × 10)."""
        freq = self._usage_frequency.get(name, 0)
        manifest = self.get(name)  # This may return None if frozen
        if manifest is None:
            # Try raw manifest for score calculation even if frozen
            pass
        staked = 0.0
        if name in self._staked_points_override:
            staked = self._staked_points_override[name]
        elif manifest is not None:
            staked = manifest.staked_points
        score = float(freq) + (staked * 10.0)
        return score

    def get_priority_breakdown(self, name: str) -> Dict[str, Any]:
        """Return a detailed breakdown of the priority score for logging."""
        freq = self._usage_frequency.get(name, 0)
        staked = 0.0
        if name in self._staked_points_override:
            staked = self._staked_points_override[name]
        else:
            m = self.get(name)
            if m:
                staked = m.staked_points
        score = float(freq) + (staked * 10.0)
        return {
            "skill": name,
            "usage_frequency": freq,
            "staked_points": staked,
            "priority_score": score,
        }

    # ── domain-based filtering & top-N selection ─────────────────────────

    def get_top_for_domain(self, prompt: str, limit: int = 3) -> List[SkillManifest]:
        """Detect intent domain, filter matching skills, sort by priority, return top N."""
        domain = detect_domain(prompt)
        manifests = self.load_all()

        # Score all skills
        scored: List[Tuple[float, SkillManifest]] = []
        for name, manifest in manifests.items():
            score = self.get_priority_score(name)
            scored.append((score, manifest))

        # Sort descending by score
        scored.sort(key=lambda x: -x[0])

        logger.info("Domain detected: '%s' — ranked %d skill(s)", domain, len(scored))
        for score, m in scored:
            logger.info("  priority %.1f | freq=%d | staked=%.1f | %s",
                        score, self._usage_frequency.get(m.name, 0),
                        self._staked_points_override.get(m.name, m.staked_points),
                        m.name)

        # Apply domain filter on tags
        domain_keywords = DOMAIN_KEYWORDS.get(domain, [])
        if domain_keywords:
            domain_filtered = [
                (s, m) for s, m in scored
                if any(kw in m.tags for kw in domain_keywords)
            ]
            # If domain filter yields nothing, fall back to all scored
            if domain_filtered:
                scored = domain_filtered

        top = [m for _, m in scored[:limit]]
        logger.info("Top %d for domain '%s': %s", limit, domain, [m.name for m in top])
        return top

    # ── execution tracking ───────────────────────────────────────────────

    def record_execution(self, skill_name: str, success: bool, slashed: float = 0.0) -> Dict[str, Any]:
        """Record a skill execution outcome and return any jail event info.

        Returns a dict with keys:
          - consecutive_failures: int
          - jailed: bool (True if sent to cool-down jail)
          - jail_duration_hours: int (24 if jailed)
        """
        self._usage_frequency[skill_name] = self._usage_frequency.get(skill_name, 0) + 1

        event: Dict[str, Any] = {"consecutive_failures": 0, "jailed": False, "jail_duration_hours": 0}

        if success:
            self._consecutive_failures[skill_name] = 0
            return event

        # Failure tracking
        fails = self._consecutive_failures.get(skill_name, 0) + 1
        self._consecutive_failures[skill_name] = fails

        # Apply staked_points slash from ledger
        if skill_name in self._staked_points_override:
            self._staked_points_override[skill_name] = max(0.0, self._staked_points_override[skill_name] - slashed)
        else:
            m = self.get(skill_name)
            if m:
                self._staked_points_override[skill_name] = max(0.0, m.staked_points - slashed)

        current_staked = self._staked_points_override.get(skill_name, 0.0)

        event["consecutive_failures"] = fails

        # Jail trigger: staked_points <= 0 OR >= 3 consecutive failures
        if current_staked <= 0.0 or fails >= 3:
            jail_until = time.time() + 86400  # 24 hours
            self._set_frozen(skill_name, jail_until)
            event["jailed"] = True
            event["jail_duration_hours"] = 24
            logger.warning(
                "JAILED skill '%s' for 24h (staked=%.1f, consecutive_failures=%d)",
                skill_name, current_staked, fails,
            )

        return event

    # ── LLM tool-definition adapters ────────────────────────────────────

    def to_anthropic_tools(self, manifests: Optional[List[SkillManifest]] = None) -> List[Dict[str, Any]]:
        targets = manifests if manifests is not None else list(self.load_all().values())
        return [to_anthropic_tool_def(m) for m in targets]

    def to_openai_tools(self, manifests: Optional[List[SkillManifest]] = None) -> List[Dict[str, Any]]:
        targets = manifests if manifests is not None else list(self.load_all().values())
        return [to_openai_tool_def(m) for m in targets]

    # ── counts & health ─────────────────────────────────────────────────

    @property
    def count(self) -> int:
        return len(self.load_all())

    def health_report(self) -> Dict[str, Any]:
        manifests = self.load_all()
        return {
            "status": "healthy" if manifests else "empty",
            "manifest_count": len(manifests),
            "manifest_names": sorted(manifests.keys()),
            "manifests_dir": str(self._manifests_dir),
            "frozen_skills": sorted(self._frozen_overrides.keys()),
        }
