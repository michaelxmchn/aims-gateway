"""WorkflowEngine — Layer 4 execution sandbox with automated verification.

Wraps every skill execution in a strict try-except block and validates
the output against the skill's output_schema (if declared). Returns an
ExecutionReceipt so the caller (MockLedger / GatewayRouter) can decide
settlement without human intervention.

This is the "Automated Verification" side of the Non-Custodial Escrow.
"""

from __future__ import annotations

import time
import logging
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from pydantic import BaseModel, ValidationError, create_model

from src.skills.manifest import SkillManifest

logger = logging.getLogger(__name__)


@dataclass
class ExecutionReceipt:
    """Immutable record of a single skill execution attempt."""

    skill_name: str
    status: str  # "SUCCESS" | "FAILED"
    error_message: str = ""
    compute_consumed: float = 0.0  # seconds (wall-clock)
    output: str = ""


# ── dynamic Pydantic validator from JSON Schema ──────────────────────────


def _build_output_validator(output_schema: Dict[str, Any]) -> Callable[[str], bool]:
    """Build a Pydantic model from a JSON Schema to validate string output.

    For MVP we check that the output is valid JSON (if the schema expects
    an object) or simply non-empty (for string type). Returns True if valid.
    """

    def validate(output: str) -> bool:
        import json
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

    Usage:
        engine = WorkflowEngine(executor_fn)
        receipt = engine.execute(manifest, {"source_code": "..."})
        # receipt.status == "SUCCESS" | "FAILED"
    """

    def __init__(self, executor_fn: Callable[[SkillManifest, Dict[str, Any]], str]) -> None:
        self._executor_fn = executor_fn

    def execute(self, manifest: SkillManifest, arguments: Dict[str, Any]) -> ExecutionReceipt:
        """Execute a skill and return a verified receipt.

        Steps:
          1. Try executing the skill code
          2. If exception → FAILED with error_message
          3. Validate output against output_schema (if declared)
          4. Return receipt with status, error, compute_consumed
        """
        start = time.perf_counter()
        skill_name = manifest.name

        try:
            output = self._executor_fn(manifest, arguments)
            compute_consumed = time.perf_counter() - start
        except Exception as exc:
            compute_consumed = time.perf_counter() - start
            logger.error("Skill '%s' raised exception: %s", skill_name, exc)
            return ExecutionReceipt(
                skill_name=skill_name,
                status="FAILED",
                error_message=f"{type(exc).__name__}: {exc}",
                compute_consumed=compute_consumed,
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
        )
