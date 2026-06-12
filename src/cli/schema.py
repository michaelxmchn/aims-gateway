"""AIMS Config Schema — strict Pydantic models for aims.config.json.

Provides:
- MonetizationConfig with 2x3 matrix (function_type × billing_mode, incl. buyout)
- AIMSConfig with 7+ fields and file I/O helpers
- Circuit breaker: worker_collab + buyout is forbidden
- EIP-55 hex address validation via regex
- Semantic version enforcement
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class MonetizationConfig(BaseModel):
    """Monetization model for the skill — governs revenue splits.

    Revenue matrix::

                        pay_per_task     subscription       buyout
        worker_collab    70/25/5 (Q1)     95/0/5 (Q2)       ✖ 风控熔断
        direct_skill     95/0/5  (Q3)     95/0/5 (Q4)      95/0/5 (Q5)

    Platform Treasury always takes 5% across all validated quadrants.
    """

    function_type: Literal["worker_collab", "direct_skill"] = Field(
        ...,
        description="worker_collab = network worker nodes required; "
        "direct_skill = runs on user's local machine.",
    )
    billing_mode: Literal["pay_per_task", "subscription", "buyout"] = Field(
        ...,
        description="pay_per_task = metered per-execution; "
        "subscription = flat monthly fee with daily rate limits; "
        "buyout = perpetual/lifetime license (direct_skill only).",
    )
    rate_limit_per_day: int | None = Field(
        default=None,
        ge=1,
        le=1000000,
        description="Daily execution cap — MANDATORY when billing_mode is 'subscription'; "
        "must be None when billing_mode is 'buyout'.",
    )

    # ── Circuit breaker: worker_collab + buyout ──────────────────────────
    @model_validator(mode="after")
    def _circuit_breaker_worker_buyout(self) -> "MonetizationConfig":
        if self.function_type == "worker_collab" and self.billing_mode == "buyout":
            raise ValueError(
                "【风控熔断】Worker协作模式依赖网络算力清算，禁止采用买断制！"
            )
        return self

    # ── Subscription must have rate_limit_per_day ────────────────────────
    @model_validator(mode="after")
    def _subscription_must_have_rate_limit(self) -> "MonetizationConfig":
        if self.billing_mode == "subscription" and self.rate_limit_per_day is None:
            raise ValueError(
                "rate_limit_per_day is MANDATORY when billing_mode is 'subscription'."
            )
        return self

    # ── Buyout must NOT have rate_limit_per_day ──────────────────────────
    @model_validator(mode="after")
    def _buyout_forbids_rate_limit(self) -> "MonetizationConfig":
        if self.billing_mode == "buyout" and self.rate_limit_per_day is not None:
            raise ValueError(
                "rate_limit_per_day must be None when billing_mode is 'buyout'."
            )
        return self

    def quadrant_label(self) -> str:
        """Return the Q1–Q5 label for this config."""
        if self.function_type == "worker_collab" and self.billing_mode == "pay_per_task":
            return "Q1"
        if self.function_type == "worker_collab" and self.billing_mode == "subscription":
            return "Q2"
        if self.function_type == "direct_skill" and self.billing_mode == "pay_per_task":
            return "Q3"
        if self.function_type == "direct_skill" and self.billing_mode == "subscription":
            return "Q4"
        return "Q5"  # direct_skill + buyout

    def revenue_split(self) -> dict[str, float]:
        """Return the revenue split percentages as ``{developer, worker, platform}``.

        Q1 (worker_collab + pay_per_task):  70% Developer / 25% Worker / 5% Platform
        Q2–Q5:                              95% Developer /  0% Worker / 5% Platform
        """
        if self.function_type == "worker_collab" and self.billing_mode == "pay_per_task":
            return {"developer": 70.0, "worker": 25.0, "platform": 5.0}
        return {"developer": 95.0, "worker": 0.0, "platform": 5.0}


class AIMSConfig(BaseModel):
    """Canonical schema for ``aims.config.json`` — the single source of truth
    for a Skill contributor's project configuration.
    """

    skill_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z][a-zA-Z0-9_-]*$",
        description="Unique skill identifier (snake_case recommended).",
    )
    version: str = Field(
        ...,
        pattern=r"^([0-9]+)\.([0-9]+)\.([0-9]+)$",
        description="Semantic version — strictly N.N.N (e.g. 1.0.0, 0.3.1).",
    )
    developer_wallet: str = Field(
        ...,
        pattern=r"^0x[a-fA-F0-9]{40}$",
        min_length=42,
        max_length=42,
        description="EIP-55 checksummed Ethereum address (0x-prefixed, 42 hex chars).",
    )
    price_per_task_usdc: float = Field(
        ...,
        gt=0.0,
        le=1_000_000.0,
        description="USDC price charged per successful task execution. Must be > 0.",
    )
    monetization: MonetizationConfig = Field(
        ...,
        description="Monetization model — function_type + billing_mode + rate limits.",
    )
    entry_point: str = Field(
        default="main.py",
        min_length=1,
        max_length=256,
        description="Local entry-point script for development / testing.",
    )
    output_schema: dict[str, Any] = Field(
        ...,
        description="JSON Schema describing the skill's return value shape.",
    )
    gateway_url: str = Field(
        ...,
        pattern=r"^https?://",
        min_length=1,
        max_length=2048,
        description="Target settlement gateway URL (HTTP or HTTPS).",
    )
    enable_universal_free_trial: bool = Field(
        default=True,
        description="AIMS Protocol standard: every unique consumer wallet receives exactly "
        "ONE free execution per skill before billing kicks in.",
    )

    model_config = {"frozen": True}

    # ── Field validators ──────────────────────────────────────────────────

    @field_validator("output_schema")
    @classmethod
    def _output_schema_must_have_type(cls, v: dict[str, Any]) -> dict[str, Any]:
        if "type" not in v:
            raise ValueError("output_schema must have a top-level 'type' field (JSON Schema)")
        return v

    @field_validator("enable_universal_free_trial")
    @classmethod
    def _free_trial_must_be_enabled(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError(
                "enable_universal_free_trial must be True — it is a hardcoded "
                "AIMS Protocol standard for all skills."
            )
        return v

    # ── File I/O ──────────────────────────────────────────────────────────

    @classmethod
    def from_json_file(cls, path: str | Path) -> AIMSConfig:
        """Load and validate ``aims.config.json`` from *path*.

        Raises:
            FileNotFoundError: the file does not exist.
            json.JSONDecodeError: the file is not valid JSON.
            pydantic.ValidationError: the content does not match the schema.
        """
        p = Path(path)
        raw = p.read_text(encoding="utf-8")
        data: dict[str, Any] = json.loads(raw)
        return cls.model_validate(data)

    def to_json_file(self, path: str | Path, *, indent: int = 2) -> None:
        """Serialize to *path* as pretty-printed JSON."""
        p = Path(path)
        p.write_text(self.model_dump_json(indent=indent), encoding="utf-8")
