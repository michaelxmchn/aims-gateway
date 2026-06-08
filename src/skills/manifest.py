"""Skill Manifest Standard — Layer 1.

Defines the Pydantic model for skill.json, enforcing strict alignment with
the LLM Tool Calling format (name / description / input_schema).

Every skill published to the AIMS market must carry a valid SkillManifest.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class SkillManifest(BaseModel):
    """The canonical metadata for an AIMS Skill.

    Maps directly to the LLM Tool/Function Calling interface:
      - name        → function name
      - description → function description
      - input_schema → function parameters (JSON Schema)
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z][a-zA-Z0-9_-]*$",
        description="Unique skill name (snake_case recommended). "
        "Serves as the function name in LLM tool calls.",
    )
    description: str = Field(
        ...,
        min_length=1,
        max_length=1024,
        description="What this skill does. Passed verbatim as the tool description "
        "so the LLM can decide when to invoke this skill.",
    )
    input_schema: Dict[str, Any] = Field(
        ...,
        description="JSON Schema (draft 2020-12) describing the expected parameters. "
        "Maps directly to `input_schema` in Anthropic tool definitions "
        "and `parameters` in OpenAI tool definitions.",
    )
    output_schema: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional JSON Schema describing the return value shape. "
        "Used by WorkflowEngine to verify execution output.",
    )
    version: str = Field(
        default="1.0.0",
        pattern=r"^\d+\.\d+\.\d+$",
        description="Semantic version of this skill.",
    )
    author: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Creator's identifier (on-chain address or handle).",
    )
    price_points: int = Field(
        default=0,
        ge=0,
        description="Points charged per execution. 0 = free.",
    )
    staked_points: float = Field(
        default=0.0,
        ge=0.0,
        description="Points staked by the developer for cold-start promotion. "
        "Used in priority scoring: Priority = Frequency + (Staked * 10). "
        "Slashed by 2.0 on each failed execution.",
    )
    frozen_until: float = Field(
        default=0.0,
        description="Unix timestamp before which this skill is frozen (jailed). "
        "Set when staked_points <= 0 or 3 consecutive failures occur. "
        "0.0 means not frozen.",
    )
    tags: List[str] = Field(
        default_factory=list,
        description="Categorisation tags for marketplace search and domain matching.",
    )

    @field_validator("input_schema")
    @classmethod
    def input_schema_must_be_valid_json_schema(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Basic structural check: every schema must declare a type at the top level."""
        if "type" not in v:
            raise ValueError("input_schema must have a top-level 'type' field (JSON Schema)")
        return v

    def is_frozen(self, now: float | None = None) -> bool:
        """Check if this skill is currently in cool-down jail."""
        import time
        return self.frozen_until > (now or time.time())


# ── Tool-definition adapters ──────────────────────────────────────────────

def to_anthropic_tool_def(manifest: SkillManifest) -> Dict[str, Any]:
    """Convert a SkillManifest to an Anthropic ToolUnion-compatible dict."""
    return {
        "name": manifest.name,
        "description": manifest.description,
        "input_schema": manifest.input_schema,
    }


def to_openai_tool_def(manifest: SkillManifest) -> Dict[str, Any]:
    """Convert a SkillManifest to an OpenAI Tool-compatible dict."""
    return {
        "type": "function",
        "function": {
            "name": manifest.name,
            "description": manifest.description,
            "parameters": manifest.input_schema,
        },
    }
