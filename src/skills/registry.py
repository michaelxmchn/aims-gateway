"""Skill Registry — Layer 2.

Loads SkillManifests from subdirectories under skills/manifests/.
Each skill lives in its own subdirectory containing:
  - manifest.json   — metadata (Pydantic model)
  - rules.md        — Document-Driven rule file (injected into LLM context)

Provides priority scoring, domain-based filtering, consecutive-failure
tracking, and cool-down jail management.
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
    "data": ["data", "analysis", "query", "csv", "json", "database", "sql", "scrape", "scraping"],
    "devops": ["deploy", "ci", "cd", "docker", "kubernetes", "infra"],
    "writing": ["write", "article", "doc", "readme", "blog", "email"],
    "general": [],
}


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
    """Loads, validates, scores, and serves SkillManifests from subdirectories."""

    def __init__(self, manifests_dir: Path = MANIFESTS_DIR) -> None:
        self._manifests_dir = manifests_dir
        self._cache: Optional[Dict[str, SkillManifest]] = None
        self._rules_cache: Dict[str, str] = {}
        self._skill_dirs: Dict[str, Path] = {}

        # Runtime tracking (not persisted — resets on restart)
        self._usage_frequency: Dict[str, int] = {}
        self._consecutive_failures: Dict[str, int] = {}
        self._staked_points_override: Dict[str, float] = {}

    # ── loading (with frozen-skill filtering) ────────────────────────────

    def load_all(self) -> Dict[str, SkillManifest]:
        """Load manifests from subdirectories, excluding frozen skills."""
        if self._cache is not None:
            return self._cache

        if not self._manifests_dir.is_dir():
            logger.warning("Manifests directory does not exist: %s", self._manifests_dir)
            self._cache = {}
            return self._cache

        raw_manifests: Dict[str, SkillManifest] = {}
        errors: List[str] = []
        now = time.time()

        # Iterate subdirectories — each subdirectory = one skill
        for skill_dir in sorted(self._manifests_dir.iterdir()):
            if not skill_dir.is_dir() or skill_dir.name.startswith("."):
                continue

            manifest_path = skill_dir / "manifest.json"
            if not manifest_path.exists():
                logger.warning("Skipping '%s': no manifest.json found", skill_dir.name)
                continue

            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    raw = json.load(f)

                name = raw.get("name", "")
                if name in self._staked_points_override:
                    raw["staked_points"] = self._staked_points_override[name]
                if name in self._frozen_overrides:
                    raw["frozen_until"] = self._frozen_overrides[name]

                manifest = SkillManifest.model_validate(raw)
                if manifest.name in raw_manifests:
                    errors.append(f"Duplicate skill name '{manifest.name}' in {skill_dir.name}")

                raw_manifests[manifest.name] = manifest
                self._skill_dirs[manifest.name] = skill_dir

                # Load rules.md if it exists
                rules_path = skill_dir / "rules.md"
                if rules_path.exists():
                    self._rules_cache[manifest.name] = rules_path.read_text(encoding="utf-8")

            except Exception as exc:
                errors.append(f"{skill_dir.name}: {exc}")

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
        logger.info(
            "Loaded %d skill(s) (%d frozen skipped, %d with rules.md)",
            len(manifests),
            len(raw_manifests) - len(manifests),
            len(self._rules_cache),
        )
        return manifests

    def reload(self) -> None:
        """Clear the cache and reload on next access."""
        self._cache = None

    def get(self, name: str) -> Optional[SkillManifest]:
        return self.load_all().get(name)

    def get_all_manifests(self) -> List[SkillManifest]:
        return list(self.load_all().values())

    # ── rules.md access ──────────────────────────────────────────────────

    def get_rules(self, name: str) -> Optional[str]:
        """Return the rules.md content for a skill, or None if not found."""
        self.load_all()  # Ensure cache is populated
        return self._rules_cache.get(name)

    def get_top_rules(self, prompt: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Get the top-N matching skills with their rules and tool definitions.

        Returns a list of dicts: [{name, description, rules_md, tool_def}, ...]
        """
        top = self.get_top_for_domain(prompt, limit=limit)
        result = []
        for m in top:
            rules = self.get_rules(m.name) or ""
            result.append({
                "name": m.name,
                "description": m.description,
                "rules_md": rules,
                "tool_def": to_anthropic_tool_def(m),
            })
        return result

    # ── frozen-skills overrides (used during jail events) ─────────────────

    _frozen_overrides: Dict[str, float] = {}

    def _set_frozen(self, skill_name: str, until: float) -> None:
        self._frozen_overrides[skill_name] = until
        self.reload()

    # ── priority scoring ─────────────────────────────────────────────────

    def get_priority_score(self, name: str) -> float:
        """Priority_Score = Usage_Frequency + (Staked_Points × 10)."""
        freq = self._usage_frequency.get(name, 0)
        manifest = self.get(name)
        staked = 0.0
        if name in self._staked_points_override:
            staked = self._staked_points_override[name]
        elif manifest is not None:
            staked = manifest.staked_points
        return float(freq) + (staked * 10.0)

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
        return {
            "skill": name,
            "usage_frequency": freq,
            "staked_points": staked,
            "priority_score": float(freq) + (staked * 10.0),
        }

    # ── domain-based filtering & top-N selection ─────────────────────────

    def get_top_for_domain(self, prompt: str, limit: int = 3) -> List[SkillManifest]:
        """Detect intent domain, filter matching skills, sort by priority, return top N."""
        domain = detect_domain(prompt)
        manifests = self.load_all()

        scored: List[Tuple[float, SkillManifest]] = []
        for name, manifest in manifests.items():
            score = self.get_priority_score(name)
            scored.append((score, manifest))

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
            if domain_filtered:
                scored = domain_filtered

        top = [m for _, m in scored[:limit]]
        logger.info("Top %d for domain '%s': %s", limit, domain, [m.name for m in top])
        return top

    # ── execution tracking ───────────────────────────────────────────────

    def record_execution(self, skill_name: str, success: bool, slashed: float = 0.0) -> Dict[str, Any]:
        """Record a skill execution outcome and return any jail event info."""
        self._usage_frequency[skill_name] = self._usage_frequency.get(skill_name, 0) + 1

        event: Dict[str, Any] = {"consecutive_failures": 0, "jailed": False, "jail_duration_hours": 0}

        if success:
            self._consecutive_failures[skill_name] = 0
            return event

        fails = self._consecutive_failures.get(skill_name, 0) + 1
        self._consecutive_failures[skill_name] = fails

        if skill_name in self._staked_points_override:
            self._staked_points_override[skill_name] = max(0.0, self._staked_points_override[skill_name] - slashed)
        else:
            m = self.get(skill_name)
            if m:
                self._staked_points_override[skill_name] = max(0.0, m.staked_points - slashed)

        current_staked = self._staked_points_override.get(skill_name, 0.0)
        event["consecutive_failures"] = fails

        if current_staked <= 0.0 or fails >= 3:
            jail_until = time.time() + 86400
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

    # ── Dynamic skill installation (from SkillStore) ────────────────────

    def install_skill(self, skill_id: str, manifest_dict: dict, impl_path: str | None = None) -> None:
        """Register a dynamically uploaded skill so it's served by the registry.

        *manifest_dict* is the raw manifest JSON (already validated).
        *impl_path* is the absolute path to ``logic.py`` on disk, if available.
        """
        from src.skills.manifest import SkillManifest
        manifest = SkillManifest.model_validate(manifest_dict)
        if self._cache is None:
            self._cache = {}
        self._cache[skill_id] = manifest
        self._skill_dirs[skill_id] = Path(impl_path).parent if impl_path else self._manifests_dir
        logger.info("INSTALLED dynamic skill '%s' v%s", skill_id, manifest.version)

    def get_impl_path(self, skill_id: str) -> str | None:
        """Return the path to the skill's implementation directory, or ``None``."""
        d = self._skill_dirs.get(skill_id)
        return str(d) if d else None

    # ── counts & health ─────────────────────────────────────────────────

    @property
    def count(self) -> int:
        return len(self.load_all())

    def health_report(self) -> Dict[str, Any]:
        manifests = self.load_all()
        skills_with_rules = sum(1 for name in manifests if self.get_rules(name) is not None)
        return {
            "status": "healthy" if manifests else "empty",
            "manifest_count": len(manifests),
            "manifest_names": sorted(manifests.keys()),
            "skills_with_rules": skills_with_rules,
            "manifests_dir": str(self._manifests_dir),
            "frozen_skills": sorted(self._frozen_overrides.keys()),
        }
