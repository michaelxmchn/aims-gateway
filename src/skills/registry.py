"""Skill Registry — Layer 2.

Loads SkillManifests from the local manifests directory and provides
tool-definition injection for the Gateway Router.

The registry is the single source of truth for "what skills are available"
during a session. It reads from `skills/manifests/*.json`, validates each
against SkillManifest, and caches them in memory.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.skills.manifest import SkillManifest, to_anthropic_tool_def, to_openai_tool_def

logger = logging.getLogger(__name__)

MANIFESTS_DIR = Path(__file__).resolve().parent / "manifests"


class RegistryError(Exception):
    """Raised when a registry operation fails."""


class SkillRegistry:
    """Loads, validates, and serves SkillManifests."""

    def __init__(self, manifests_dir: Path = MANIFESTS_DIR) -> None:
        self._manifests_dir = manifests_dir
        self._cache: Optional[Dict[str, SkillManifest]] = None

    # ── public API ──────────────────────────────────────────────────────

    def load_all(self) -> Dict[str, SkillManifest]:
        """Load and validate all skill.json files from the manifests directory.

        Results are cached in memory for the lifetime of this instance.
        Call ``reload()`` to refresh after files change.
        """
        if self._cache is not None:
            return self._cache

        if not self._manifests_dir.is_dir():
            logger.warning("Manifests directory does not exist: %s", self._manifests_dir)
            self._cache = {}
            return self._cache

        manifests: Dict[str, SkillManifest] = {}
        errors: List[str] = []

        for path in sorted(self._manifests_dir.glob("*.json")):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                manifest = SkillManifest.validate(raw)
                if manifest.name in manifests:
                    errors.append(
                        f"Duplicate skill name '{manifest.name}' in {path.name} "
                        f"(already loaded from {manifests[manifest.name].name})"
                    )
                manifests[manifest.name] = manifest
            except Exception as exc:
                errors.append(f"{path.name}: {exc}")

        if errors:
            logger.warning("Skill manifest loading completed with %d error(s): %s", len(errors), errors)

        self._cache = manifests
        logger.info("Loaded %d skill manifest(s) from %s", len(manifests), self._manifests_dir)
        return manifests

    def reload(self) -> None:
        """Clear the cache and reload on next access."""
        self._cache = None

    def get(self, name: str) -> Optional[SkillManifest]:
        """Look up a single manifest by name. Returns None if not found."""
        return self.load_all().get(name)

    def get_all_manifests(self) -> List[SkillManifest]:
        """Return all manifests as a list."""
        return list(self.load_all().values())

    # ── LLM tool-definition adapters ────────────────────────────────────

    def to_anthropic_tools(self) -> List[Dict[str, Any]]:
        """Convert all loaded manifests to Anthropic ToolUnion format.

        Used directly as the ``tools`` parameter in anthropic.types.MessageParam.
        """
        return [to_anthropic_tool_def(m) for m in self.load_all().values()]

    def to_openai_tools(self) -> List[Dict[str, Any]]:
        """Convert all loaded manifests to OpenAI Tool format.

        Used directly as the ``tools`` parameter in openai.chat.completions.
        """
        return [to_openai_tool_def(m) for m in self.load_all().values()]

    # ── counts & health ─────────────────────────────────────────────────

    @property
    def count(self) -> int:
        return len(self.load_all())

    def health_report(self) -> Dict[str, Any]:
        """Return a diagnostic summary of the registry state."""
        manifests = self.load_all()
        return {
            "status": "healthy" if manifests else "empty",
            "manifest_count": len(manifests),
            "manifest_names": sorted(manifests.keys()),
            "manifests_dir": str(self._manifests_dir),
        }
