"""AI Judge arbitration engine — LLM-as-a-Judge for task output quality.

Scores worker-submitted output 0-100 via LLM evaluation.  Score >= 80
triggers on-chain settlement (``settleTask``); score < 80 triggers refund
(``refundTask``) with SSE red alert broadcast.

Usage::

    judge = JudgeEngine(
        contract_client=_contract,
        gateway_private_key=AIMS_GATEWAY_PRIVATE_KEY,
        on_refund_alert=broadcast_settlement,
    )
    verdict = judge.score(task_input, task_output, skill_id)
    if verdict.passed:
        commerce.charge_and_settle(...)  # normal settlement
    else:
        judge.refund_on_chain(task_id, user, amount, verdict.reason)
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ── Constants ─────────────────────────────────────────────────────────────────

JUDGE_PASS_THRESHOLD: int = 80
"""Minimum score for a task to pass arbitration (≥80 = settle, <80 = refund)."""

JUDGE_SYSTEM_PROMPT: str = (
    "You are an AI Judge on the AIMS Network. Your role is to evaluate the "
    "quality of worker-submitted task outputs. Score 0-100 based on:\n"
    "- Correctness (0-40): Does the output correctly address the task input?\n"
    "- Completeness (0-30): Are all required fields present and meaningful?\n"
    "- Quality (0-30): Is the output well-structured, coherent, and useful?\n\n"
    "Respond ONLY with a JSON object: {\"score\": <int 0-100>, \"reason\": \"<brief explanation>\"}"
)

JUDGE_DETERMINISTIC_THRESHOLD: int = 60
"""Default score when no LLM is available (cautious — fail unless clearly valid)."""


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class JudgeVerdict:
    """Result of a judge evaluation."""

    score: int = 0
    """Quality score 0-100."""

    passed: bool = False
    """``True`` if ``score >= JUDGE_PASS_THRESHOLD``."""

    reason: str = ""
    """Human-readable reasoning for the score."""

    raw_llm_response: str = ""
    """Raw LLM response text (for audit trail)."""

    latency_ms: float = 0.0
    """Time taken for the LLM call, in milliseconds."""


# ── JudgeEngine ───────────────────────────────────────────────────────────────


class JudgeEngine:
    """AI Judge that scores task output quality and executes on-chain verdicts.

    Uses an OpenAI-compatible chat-completion API for scoring.  Falls back
    to a deterministic heuristic when no API key is configured.

    Parameters
    ----------
    contract_client:
        Settlement contract client (``SettlementContractClient`` instance).
        Required for ``refund_on_chain()``.
    gateway_private_key:
        Gateway EOA private key for signing refund transactions.
    on_refund_alert:
        Optional callback (e.g. ``broadcast_settlement``) called when a
        refund is executed.  Receives a dict with the refund event details.
    api_key:
        OpenAI API key.  Falls back to ``OPENAI_API_KEY`` env var.
    model:
        OpenAI model name (default ``gpt-4o-mini``).
    """

    DEFAULT_MODEL = "gpt-4o-mini"

    def __init__(
        self,
        contract_client: Any = None,
        gateway_private_key: str = "",
        on_refund_alert: Optional[callable] = None,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
    ) -> None:
        self._contract = contract_client
        self._gateway_private_key = gateway_private_key
        self._on_refund_alert = on_refund_alert
        self._api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self._model = model
        self._client = None

        if self._api_key:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=self._api_key)
                logger.info("JudgeEngine: using OpenAI model=%s", self._model)
            except ImportError:
                logger.warning(
                    "JudgeEngine: openai package not installed — "
                    "falling back to deterministic scoring"
                )
        else:
            logger.info("JudgeEngine: no OPENAI_API_KEY — using deterministic fallback")

    # ── Public API ─────────────────────────────────────────────────────────

    def score(
        self,
        task_input: dict[str, Any],
        task_output: dict[str, Any],
        skill_id: str,
        output_schema: Optional[dict[str, Any]] = None,
    ) -> JudgeVerdict:
        """Score task output quality 0-100.

        Uses LLM when available, otherwise falls back to deterministic
        heuristics.

        Parameters
        ----------
        task_input:
            The original input parameters passed to the skill.
        task_output:
            The result dict produced by the worker.
        skill_id:
            Skill identifier (for context in the LLM prompt).
        output_schema:
            Optional JSON Schema for the expected output — used by the
            deterministic fallback for structural validation.

        Returns
        -------
        JudgeVerdict
            With ``score`` (0-100), ``passed`` (``score >= 80``), and
            ``reason`` for audit.
        """
        start = time.time()

        if self._client is not None:
            verdict = self._score_via_llm(task_input, task_output, skill_id, output_schema)
        else:
            verdict = self._score_deterministic(task_output, output_schema)

        verdict.latency_ms = (time.time() - start) * 1000
        return verdict

    def refund_on_chain(
        self,
        task_id: str,
        user_address: str,
        amount: int,
        reason: str = "AI Judge: quality below threshold",
    ) -> dict[str, Any]:
        """Execute an on-chain refund via the settlement contract.

        The gateway signs and submits ``refundTask``, then broadcasts an
        SSE red-alert event through the ``on_refund_alert`` callback.

        Returns
        -------
        dict
            Result with ``status`` ("REFUNDED" or "FAILED"), ``task_id``,
            and ``error`` (if any).
        """
        result: dict[str, Any] = {
            "status": "FAILED",
            "task_id": task_id,
            "user_address": user_address,
            "amount": amount,
            "reason": reason,
            "error": "",
        }

        if self._contract is None:
            result["error"] = "No contract client configured"
            logger.error("refund_on_chain: %s", result["error"])
            return result

        try:
            from eth_utils import keccak
            task_id_bytes = keccak(text=task_id)
            self._contract.refund_task(
                task_id=task_id_bytes,
                user=user_address,
                amount=amount,
                reason=reason,
            )
            result["status"] = "REFUNDED"
            logger.info(
                "REFUND task=%s user=%s amount=%d reason=%s",
                task_id, user_address, amount, reason,
            )

            # SSE red alert broadcast
            if self._on_refund_alert is not None:
                self._on_refund_alert({
                    "action": "refund",
                    "task_id": task_id,
                    "user": user_address,
                    "amount": amount,
                    "reason": reason,
                    "ts": time.time(),
                    "severity": "ALERT",
                })

        except Exception as exc:
            result["error"] = str(exc)
            logger.error("refund_on_chain failed: %s", exc)

        return result

    # ── LLM scoring ───────────────────────────────────────────────────────

    def _build_judge_prompt(
        self,
        task_input: dict[str, Any],
        task_output: dict[str, Any],
        skill_id: str,
        output_schema: Optional[dict[str, Any]] = None,
    ) -> str:
        """Construct the user message for the LLM judge."""
        parts = [
            f"## Task Input\n```json\n{json.dumps(task_input, indent=2, default=str)}\n```",
            f"## Skill ID\n{skill_id}",
        ]
        if output_schema:
            parts.append(
                f"## Expected Output Schema\n```json\n{json.dumps(output_schema, indent=2)}\n```"
            )
        parts.append(
            f"## Worker Output\n```json\n{json.dumps(task_output, indent=2, default=str)}\n```"
        )
        parts.append(
            "\nEvaluate the Worker Output. Return ONLY a JSON object: "
            '{"score": <int 0-100>, "reason": "<brief explanation>"}'
        )
        return "\n\n".join(parts)

    def _score_via_llm(
        self,
        task_input: dict[str, Any],
        task_output: dict[str, Any],
        skill_id: str,
        output_schema: Optional[dict[str, Any]] = None,
    ) -> JudgeVerdict:
        """Score via OpenAI chat completion."""
        prompt = self._build_judge_prompt(task_input, task_output, skill_id, output_schema)

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=256,
            )
            raw = response.choices[0].message.content or ""
        except Exception as exc:
            logger.error("JudgeEngine LLM call failed: %s", exc)
            return JudgeVerdict(
                score=JUDGE_DETERMINISTIC_THRESHOLD,
                passed=JUDGE_DETERMINISTIC_THRESHOLD >= JUDGE_PASS_THRESHOLD,
                reason=f"LLM call failed: {exc}",
                raw_llm_response="",
            )

        # Parse JSON response
        try:
            # Strip markdown code fences if present
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1]
                cleaned = cleaned.rsplit("```", 1)[0]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()
            data = json.loads(cleaned)
            score = int(data.get("score", JUDGE_DETERMINISTIC_THRESHOLD))
            reason = str(data.get("reason", ""))
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            logger.warning("JudgeEngine: failed to parse LLM response: %s", exc)
            logger.debug("Raw LLM response: %s", raw)
            score = JUDGE_DETERMINISTIC_THRESHOLD
            reason = f"Failed to parse LLM response: {exc}"

        score = max(0, min(100, score))
        return JudgeVerdict(
            score=score,
            passed=score >= JUDGE_PASS_THRESHOLD,
            reason=reason,
            raw_llm_response=raw,
        )

    # ── Deterministic fallback ─────────────────────────────────────────────

    def _score_deterministic(
        self,
        task_output: dict[str, Any],
        output_schema: Optional[dict[str, Any]] = None,
    ) -> JudgeVerdict:
        """Score using basic structural heuristics when no LLM is available."""
        if not isinstance(task_output, dict):
            return JudgeVerdict(
                score=10,
                passed=False,
                reason="Output is not a valid JSON object",
            )

        if not task_output:
            return JudgeVerdict(
                score=5,
                passed=False,
                reason="Output is empty",
            )

        score = 50  # start at mid-range
        reasons: list[str] = []

        # Check against schema
        if output_schema and "required" in output_schema:
            required = output_schema["required"]
            missing = [f for f in required if f not in task_output]
            if missing:
                score -= 20
                reasons.append(f"Missing required fields: {missing}")
            else:
                score += 20
                reasons.append("All required fields present")

        # Check non-empty values
        empty_values = sum(1 for v in task_output.values() if v is None or v == "")
        if empty_values > 0:
            score -= empty_values * 5
            reasons.append(f"{empty_values} field(s) are empty/null")

        # Check output length (suspicious if too short)
        output_str = json.dumps(task_output)
        if len(output_str) < 20:
            score -= 15
            reasons.append("Output suspiciously short")

        # Check for error-like content
        error_keywords = ["error", "fail", "exception", "timeout", "unavailable"]
        output_lower = output_str.lower()
        for kw in error_keywords:
            if kw in output_lower:
                score -= 10
                reasons.append(f"Output contains '{kw}'")

        score = max(0, min(100, score))
        return JudgeVerdict(
            score=score,
            passed=score >= JUDGE_PASS_THRESHOLD,
            reason="; ".join(reasons) if reasons else "Deterministic: no issues detected",
        )
