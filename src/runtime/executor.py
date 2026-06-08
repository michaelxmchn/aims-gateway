"""Skill Runtime — Layer 4.

Executes a single Skill in the local environment (trust mode for MVP).
Records the execution to the Append-only Log.
"""

from __future__ import annotations

import time
import logging
from typing import Any, Dict, Optional

from src.skills.manifest import SkillManifest
from src.ledger.log import AppendOnlyLog, ExecutionRecord

logger = logging.getLogger(__name__)


class SkillRuntime:
    """Local skill execution sandbox (trust mode — MVP)."""

    def __init__(self, ledger: Optional[AppendOnlyLog] = None) -> None:
        self._ledger = ledger or AppendOnlyLog()

    def execute(self, manifest: SkillManifest, arguments: Dict[str, Any]) -> str:
        start = time.perf_counter()

        try:
            result = self._run_skill(manifest, arguments)
            duration_ms = (time.perf_counter() - start) * 1000
            self._record(manifest, arguments, result, duration_ms, status="success")
            return result
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            self._record(manifest, arguments, str(exc), duration_ms, status="error")
            raise

    def _run_skill(self, manifest: SkillManifest, arguments: Dict[str, Any]) -> str:
        """Dispatch to the skill's implementation.

        In MVP, skills are implemented as simple Python callables
        registered in a skill_impls map. Future versions will support
        WASM/docker-based sandboxed execution.
        """
        impl = SKILL_IMPLS.get(manifest.name)
        if impl is None:
            # Fallback: return the manifest + args as context for the
            # calling AI client to handle (the client's own LLM
            # implements the skill logic).
            return _fallback_impl(manifest, arguments)
        return impl(arguments)

    def _record(
        self,
        manifest: SkillManifest,
        arguments: Dict[str, Any],
        output: str,
        duration_ms: float,
        status: str,
    ) -> None:
        import hashlib, json

        record = ExecutionRecord(
            skill_id=manifest.name,
            input_hash=hashlib.sha256(json.dumps(arguments, sort_keys=True).encode()).hexdigest(),
            output_hash=hashlib.sha256(output.encode()).hexdigest(),
            duration_ms=duration_ms,
            status=status,
            points_delta=manifest.price_points,
        )
        self._ledger.append(record)


# ── built-in skill implementations (seed skills) ──────────────────────────


def _fallback_impl(manifest: SkillManifest, arguments: Dict[str, Any]) -> str:
    """Default no-op: describe what the skill would do.

    Real implementations are injected by the AI client that hosts AIMS.
    """
    import json
    return (
        f"[{manifest.name}] Skill loaded. Input: {json.dumps(arguments, indent=2)}\n"
        f"To implement this skill, register a handler in SKILL_IMPLS."
    )


SKILL_IMPLS: Dict[str, Any] = {}
"""Registry of local skill implementations.

Add entries like::

    def audit_code(args): ...
    SKILL_IMPLS["code_security_audit"] = audit_code
"""
