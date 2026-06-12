"""Universal "First-Task-Free" PLG enforcement protocol.

Every unique consumer wallet receives exactly ONE (1) free execution per
Skill ID across all function_types and billing_modes.  On the 2nd invocation
the gateway checks for active payment proof; if none is found, execution is
aborted with a 402 + mode-specific billing prompt.

Mode-specific unlocking after trial consumption:

  - **pay_per_task**:  Gateway's existing balance check covers this.
  - **subscription**:  Wallet must hold a non-expired subscription pass.
  - **buyout**:        Wallet must have purchased a perpetual license.
"""

from __future__ import annotations

import time
from typing import Any

from src.gateway.storage import Storage


class FreeTrialError(Exception):
    """Raised when trial enforcement rejects an execution."""


class FreeTrialManager:
    """Tracks per-(wallet, skill_id) trial usage and enforces hard lockout.

    Storage layout::

        trial:{wallet_lower}:{skill_id}       → int  (execution count)
        subscription:{wallet_lower}:{skill_id} → dict (expires_at, …)
        buyout:{wallet_lower}:{skill_id}       → dict (purchased, ts, …)

    Thread-safe through the underlying ``Storage`` abstraction.
    """

    TRIAL_NS = "trial"
    SUBSCRIPTION_NS = "subscription"
    BUYOUT_NS = "buyout"

    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    # ── Trial tracking ────────────────────────────────────────────────────────

    def _trial_key(self, wallet: str, skill_id: str) -> str:
        return f"{self.TRIAL_NS}:{wallet.lower()}:{skill_id}"

    def get_usage_count(self, wallet: str, skill_id: str) -> int:
        """Return the number of times *wallet* has executed *skill_id*."""
        return self._storage.get(self._trial_key(wallet, skill_id)) or 0

    def is_trial_eligible(self, wallet: str, skill_id: str) -> bool:
        """Check if *wallet* still has a free trial available."""
        return self.get_usage_count(wallet, skill_id) < 1

    def consume_trial(self, wallet: str, skill_id: str) -> int:
        """Mark one free trial execution.  Returns the new usage count."""
        key = self._trial_key(wallet, skill_id)
        count = (self._storage.get(key) or 0) + 1
        self._storage.set(key, count)
        return count

    # ── Subscription checks ───────────────────────────────────────────────────

    def _subscription_key(self, wallet: str, skill_id: str) -> str:
        return f"{self.SUBSCRIPTION_NS}:{wallet.lower()}:{skill_id}"

    def has_active_subscription(self, wallet: str, skill_id: str) -> bool:
        """Check if *wallet* has a non-expired subscription."""
        sub = self._storage.get(self._subscription_key(wallet, skill_id))
        if sub is None:
            return False
        expires_at = sub.get("expires_at", 0)
        return isinstance(expires_at, (int, float)) and time.time() < expires_at

    def set_subscription(
        self, wallet: str, skill_id: str, expires_at: float,
    ) -> None:
        """Record or renew a subscription pass."""
        key = self._subscription_key(wallet, skill_id)
        self._storage.set(key, {"expires_at": expires_at, "ts": time.time()})

    # ── Buyout (perpetual) license checks ─────────────────────────────────────

    def _buyout_key(self, wallet: str, skill_id: str) -> str:
        return f"{self.BUYOUT_NS}:{wallet.lower()}:{skill_id}"

    def has_buyout_license(self, wallet: str, skill_id: str) -> bool:
        """Check if *wallet* holds a perpetual license."""
        lic = self._storage.get(self._buyout_key(wallet, skill_id))
        return lic is not None and lic.get("purchased") is True

    def set_buyout_license(self, wallet: str, skill_id: str) -> None:
        """Record a perpetual buyout purchase."""
        key = self._buyout_key(wallet, skill_id)
        self._storage.set(key, {"purchased": True, "ts": time.time()})

    # ── Unified enforcement ──────────────────────────────────────────────────

    def check_trial_or_payment(
        self,
        wallet: str,
        skill_id: str,
        *,
        billing_mode: str,
    ) -> tuple[bool, str]:
        """Check trial eligibility or payment proof.

        Returns:
            ``(allowed, reason)``.  When *allowed* is ``False`` the caller
            should abort; *reason* is a human-readable billing prompt
            suitable for a 402 Payment Required response.
        """
        count = self.get_usage_count(wallet, skill_id)

        if count == 0:
            return (True, "free_trial")

        # ── Post-trial: check payment proof per billing mode ───────────
        if billing_mode == "pay_per_task":
            # Balance is checked separately by the billing engine.
            return (True, "pay_per_task")

        if billing_mode == "subscription":
            if self.has_active_subscription(wallet, skill_id):
                return (True, "subscription_active")
            return (
                False,
                "SUBSCRIPTION_REQUIRED: Purchase a subscription pass to "
                "continue using this skill.",
            )

        if billing_mode == "buyout":
            if self.has_buyout_license(wallet, skill_id):
                return (True, "buyout_licensed")
            return (
                False,
                "BUYOUT_REQUIRED: Purchase a perpetual license to unlock "
                "this skill permanently.",
            )

        return (
            False,
            f"PAYMENT_REQUIRED: Unknown billing mode '{billing_mode}'.",
        )

    def enforce(
        self,
        wallet: str,
        skill_id: str,
        *,
        billing_mode: str,
    ) -> None:
        """Enforce trial / payment gate.  Raises ``FreeTrialError`` on lockout.

        Call this at the start of every skill execution request, *before*
        the balance check.

        Raises:
            FreeTrialError: the execution should be aborted.
        """
        allowed, reason = self.check_trial_or_payment(
            wallet, skill_id, billing_mode=billing_mode,
        )
        if not allowed:
            raise FreeTrialError(reason)

        # Count the trial usage only once per wallet+skill
        if reason == "free_trial":
            self.consume_trial(wallet, skill_id)
