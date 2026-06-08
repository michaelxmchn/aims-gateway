"""MockLedger — USDT Just-In-Time Escrow & Dynamic Billing (Layer 0).

Simulates a real web3 USD stablecoin clearing house. All balances are
in USDT (float, 2-decimal precision for display).

Lifecycle:
  Fixed-Price (legacy):
    1. freeze_usdt(user_id, amount) — deduct from user, hold in escrow_vault
    2. settle_escrow(freeze_id, success, dev_address):
         SUCCESS → 1% platform tax → founder_treasury, 99% → developer
         FAILED  → 100% instant refund to user

  Dynamic Billing (gas-based):
    1. create_escrow_hold(user_id, max_budget) — pre-auth freeze max budget
    2. release_escrow_dynamic(escrow_id, ...) — settle based on real execution time:
         gas_cost = exec_time × BASE_GAS_RATE
         total   = gas_cost + developer_premium  (capped at max_budget)
         SUCCESS → tax to treasury, payout to dev, refund unused to user
         FAILED  → 100% refund of entire max_budget to user
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# ── Gas & Fee Constants ──────────────────────────────────────────────

BASE_GAS_RATE: float = 0.01
"""USDT per second of execution time — the base compute cost."""

PLATFORM_TAX_RATE: float = 0.01
"""1% platform fee on total cost — sent to founder treasury on success."""

ESCROW_TAX_RATE = PLATFORM_TAX_RATE
"""Alias for backward compatibility with legacy settle_escrow()."""


@dataclass
class FreezeReceipt:
    """Proof that USDT was frozen in escrow when a workflow started."""

    freeze_id: str
    user_id: str
    amount: float             # USDT
    skill_name: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class SettlementDetail:
    """Result of settling a frozen escrow transaction."""

    freeze_id: str
    outcome: str              # "TRANSFERRED" | "REFUNDED"
    user_id: str
    dev_address: str
    gross_amount: float       # Total USDT that was in escrow
    platform_tax: float = 0.0  # USDT sent to founder treasury
    dev_net: float = 0.0      # USDT sent to developer (after tax)
    user_refund: float = 0.0  # USDT returned to user (on failure)


# ── Dynamic Billing (gas-based) dataclasses ─────────────────────────


@dataclass
class EscrowHold:
    """Pre-authorized escrow hold with a maximum budget ceiling.

    The full max_budget is frozen from the user's wallet up front.
    On settlement, only the actual cost is consumed; the remainder
    is immediately refunded.
    """

    escrow_id: str
    user_id: str
    max_budget: float         # USDT — the ceiling frozen from the user
    timestamp: float = field(default_factory=time.time)


@dataclass
class DynamicSettlementDetail:
    """Itemised billing receipt for a gas-based escrow release."""

    escrow_id: str
    outcome: str              # "COMPLETED" | "REFUNDED"
    user_id: str
    developer_id: str

    # Execution
    execution_time: float     # seconds measured by the sandbox
    gas_rate: float           # USDT/s (the BASE_GAS_RATE constant)
    gas_cost: float           # execution_time × gas_rate
    developer_premium: float  # the skill's price_points in USDT

    # Settlement
    max_budget: float         # original frozen amount
    total_cost: float         # gas_cost + developer_premium (capped)
    platform_tax: float       # total_cost × PLATFORM_TAX_RATE
    developer_payout: float   # total_cost − platform_tax
    unused_refund: float      # max_budget − total_cost (returned to user)


class MockLedger:
    """In-memory USDT escrow and settlement mock.

    Maintains user balances, developer balances, an escrow vault for
    in-flight transactions, and a founder treasury that collects the
    1% platform tax.
    """

    def __init__(self) -> None:
        self._user_balances: Dict[str, float] = {}
        self._dev_balances: Dict[str, float] = {}
        self._escrow_vault: Dict[str, FreezeReceipt] = {}
        self._founder_treasury_usdt: float = 0.0
        self._freeze_counter: int = 0
        self._lock = threading.Lock()

        # ── Worker Registration & Staking ──────────────────────────────────
        self._staked_collateral: Dict[str, float] = {}
        self.worker_strikes: Dict[str, int] = {}
        """Strike counter keyed by worker_id (public for test inspection)."""

        # ── Reputation & Rating ──────────────────────────────────────────
        self._user_skill_usage: Dict[str, set[str]] = {}
        """Track which skills each user has successfully used (for rating gating)."""
        self._user_reputation: Dict[str, float] = {}
        """User reputation score (1.0 = default, [0.0, 1.0] range)."""
        self._rating_history: Dict[str, list[str]] = {}
        """Which skills each user has rated (user_id → [skill_id, ...])."""
        self._skill_rating_entries: Dict[str, list[dict]] = {}
        """Rating entries per skill: [{"user_id": ..., "reputation": ..., "rating": ...}, ...]."""
        self._skill_weighted_score: Dict[str, float] = {}
        """Weighted average score per skill (default 5.0)."""

    # ── thread-safe read helpers ─────────────────────────────────────────

    def _snapshot_wealth(self) -> float:
        """Return total USDT across all balances + treasury + collateral (must hold lock)."""
        total = self._founder_treasury_usdt
        for v in self._user_balances.values():
            total += v
        for v in self._dev_balances.values():
            total += v
        for v in self._staked_collateral.values():
            total += v
        return total

    @property
    def total_system_wealth(self) -> float:
        """Thread-safe snapshot of every USDT in the system."""
        with self._lock:
            return self._snapshot_wealth()

    # ── balance management ──────────────────────────────────────────────

    def seed_usdt(self, user_id: str, amount: float) -> None:
        """Seed a user with initial USDT for testing."""
        with self._lock:
            self._user_balances[user_id] = self._user_balances.get(user_id, 0.0) + amount
        logger.info(
            "SEED  %s +$%.2f USDT (balance=$%.2f)",
            user_id, amount, self._user_balances[user_id],
        )

    def get_user_usdt(self, user_id: str) -> float:
        with self._lock:
            return self._user_balances.get(user_id, 0.0)

    def get_dev_usdt(self, dev_address: str) -> float:
        with self._lock:
            return self._dev_balances.get(dev_address, 0.0)

    @property
    def founder_treasury_usdt(self) -> float:
        with self._lock:
            return self._founder_treasury_usdt

    # ── Worker Registration & Staking ─────────────────────────────────────

    def seed_dev_usdt(self, worker_id: str, amount: float) -> None:
        """Seed a worker's dev balance with USDT (for testing)."""
        with self._lock:
            self._dev_balances[worker_id] = self._dev_balances.get(worker_id, 0.0) + amount
        logger.info(
            "SEED-DEV %s +$%.2f USDT (balance=$%.2f)",
            worker_id, amount, self._dev_balances[worker_id],
        )

    def register_worker(self, worker_id: str, stake_amount: float = 5.0) -> bool:
        """Register a worker by freezing *stake_amount* USDT as collateral.

        Deducts from the worker's dev balance. Returns ``True`` if the
        stake was successfully frozen, ``False`` if insufficient funds.
        """
        with self._lock:
            balance = self._dev_balances.get(worker_id, 0.0)
            if balance < stake_amount:
                logger.warning(
                    "REGISTER FAIL: %s has $%.2f, needs $%.2f to stake",
                    worker_id, balance, stake_amount,
                )
                return False

            self._dev_balances[worker_id] = round(balance - stake_amount, 2)
            self._staked_collateral[worker_id] = round(
                self._staked_collateral.get(worker_id, 0.0) + stake_amount, 2,
            )
            self.worker_strikes.setdefault(worker_id, 0)

        logger.info(
            "REGISTER %s → staked $%.2f USDT (collateral=$%.2f, strikes=%d)",
            worker_id, stake_amount,
            self._staked_collateral[worker_id],
            self.worker_strikes[worker_id],
        )
        return True

    def get_staked_collateral(self, worker_id: str) -> float:
        """Return the amount of USDT a worker has locked as collateral."""
        with self._lock:
            return self._staked_collateral.get(worker_id, 0.0)

    def apply_penalty(self, worker_id: str, reason: str) -> float:
        """Issue a strike to *worker_id*.

        **Strike accumulation (3-strike rule):**
          - Strikes 1-2: warning only.
          - Strike 3+: **Slash Event** — $1.00 USDT deducted from
            ``_staked_collateral`` and transferred to ``founder_treasury``.
            Strike counter is reset to 0.

        Returns the amount slashed (1.0 on slash, 0.0 on warning-only).
        """
        with self._lock:
            self.worker_strikes[worker_id] = self.worker_strikes.get(worker_id, 0) + 1
            strikes = self.worker_strikes[worker_id]

            logger.warning(
                "STRIKE %d for '%s' — reason: %s",
                strikes, worker_id, reason,
            )

            if strikes >= 3:
                collateral = self._staked_collateral.get(worker_id, 0.0)
                if collateral >= 1.0:
                    self._staked_collateral[worker_id] = round(collateral - 1.0, 2)
                    self._founder_treasury_usdt += 1.0
                    self.worker_strikes[worker_id] = 0  # reset after slash
                    logger.warning(
                        "SLASH $1.00 from '%s' collateral! "
                        "(remaining=$%.2f  treasury=$%.2f)",
                        worker_id, self._staked_collateral[worker_id],
                        self._founder_treasury_usdt,
                    )
                    return 1.0
                else:
                    logger.warning(
                        "Insufficient collateral to slash '%s' ($%.2f)",
                        worker_id, collateral,
                    )

            return 0.0

    # ── Reputation & Rating ────────────────────────────────────────────────

    def get_user_reputation(self, user_id: str) -> float:
        """Return user's reputation score (default 1.0)."""
        with self._lock:
            return self._user_reputation.get(user_id, 1.0)

    def get_skill_weighted_score(self, skill_id: str) -> float:
        """Return skill's weighted score (default 5.0)."""
        with self._lock:
            return self._skill_weighted_score.get(skill_id, 5.0)

    def submit_rating(self, user_id: str, skill_id: str, rating_value: float) -> bool:
        """Submit a rating for a skill with reputation-weighted scoring.

        **Gating:** User must have a successful usage record for this skill
        (preventing sybil rating bombing).

        **Outlier Detection:** When the skill has >= 5 historical ratings,
        if ``|rating - historical_mean| > 2.5``, the rating is flagged as
        an **ANOMALY**, suppressed (not appended), and the user's reputation
        is penalised by -0.1. The skill's ``weighted_score`` is unchanged.

        **Normal path:** The rating is appended and ``weighted_score`` is
        recomputed as::

            weighted_score = Σ(reputation_i × rating_i) / Σ(reputation_i)

        Returns ``True`` if the rating was accepted, ``False`` if suppressed.
        """
        with self._lock:
            # ── Gate: must have used this skill successfully ──────────
            usage = self._user_skill_usage.get(user_id, set())
            if skill_id not in usage:
                logger.warning(
                    "RATING REJECTED: User '%s' has no usage record for '%s'",
                    user_id, skill_id,
                )
                return False

            rating_value = max(1.0, min(5.0, rating_value))
            entries = self._skill_rating_entries.get(skill_id, [])
            rep = self._user_reputation.get(user_id, 1.0)

            # ── Outlier detection (requires >= 5 historical entries) ──
            if len(entries) >= 5:
                historical_mean = sum(e["rating"] for e in entries) / len(entries)
                if abs(rating_value - historical_mean) > 2.5:
                    new_rep = max(0.0, rep - 0.1)
                    self._user_reputation[user_id] = new_rep
                    logger.warning(
                        "[Audit] Anomaly detected from User '%s'. Rating suppressed. "
                        "User reputation penalized: %.2f → %.2f",
                        user_id, rep, new_rep,
                    )
                    return False

            # ── Normal rating — append and recalculate weighted score ─
            entry = {"user_id": user_id, "reputation": rep, "rating": rating_value}
            entries.append(entry)
            self._skill_rating_entries[skill_id] = entries

            # Track user's rating history
            if user_id not in self._rating_history:
                self._rating_history[user_id] = []
            self._rating_history[user_id].append(skill_id)

            # Weighted average: Σ(rep × rating) / Σ(rep)
            total_weighted = sum(e["reputation"] * e["rating"] for e in entries)
            total_weight = sum(e["reputation"] for e in entries)
            self._skill_weighted_score[skill_id] = (
                round(total_weighted / total_weight, 2) if total_weight > 0 else 5.0
            )

            logger.info(
                "RATING: User '%s' rated '%s' = %.1f  (rep=%.2f)  weighted_score=%.2f",
                user_id, skill_id, rating_value, rep,
                self._skill_weighted_score[skill_id],
            )
            return True

    # ── JIT Escrow ─────────────────────────────────────────────────────

    def freeze_usdt(self, user_id: str, amount: float) -> Optional[FreezeReceipt]:
        """Step 1: Freeze USDT from the user's balance into escrow.

        Returns FreezeReceipt on success, None if insufficient balance.
        """
        with self._lock:
            balance = self._user_balances.get(user_id, 0.0)
            if balance < amount:
                logger.warning(
                    "INSUFFICIENT USDT: user=%s has $%.2f, needs $%.2f",
                    user_id, balance, amount,
                )
                return None

            self._user_balances[user_id] = balance - amount
            self._freeze_counter += 1
            receipt = FreezeReceipt(
                freeze_id=f"escrow-{self._freeze_counter:04d}",
                user_id=user_id,
                amount=amount,
                skill_name="",
            )
            self._escrow_vault[receipt.freeze_id] = receipt
        logger.info(
            "FREEZE %s → $%.2f USDT held in escrow  [user=%s]",
            receipt.freeze_id, amount, user_id,
        )
        return receipt

    def settle_escrow(
        self,
        freeze_id: str,
        success: bool,
        dev_address: str = "",
        skill_name: str = "",
    ) -> Optional[SettlementDetail]:
        """Step 2: Settle an escrow transaction based on execution outcome.

        SUCCESS → 1% platform tax to founder_treasury, 99% to dev.
        FAILED  → 100% instant refund to user.

        Returns SettlementDetail, or None if freeze_id not found.
        """
        with self._lock:
            receipt = self._escrow_vault.pop(freeze_id, None)
            if receipt is None:
                logger.error("Escrow receipt not found: %s", freeze_id)
                return None

            gross = receipt.amount

            if success:
                tax = round(gross * ESCROW_TAX_RATE, 2)
                dev_net = round(gross - tax, 2)

                # 1% platform tax -> founder treasury
                self._founder_treasury_usdt += tax
                # 99% -> developer
                self._dev_balances[dev_address] = self._dev_balances.get(dev_address, 0.0) + dev_net

                detail = SettlementDetail(
                    freeze_id=freeze_id,
                    outcome="TRANSFERRED",
                    user_id=receipt.user_id,
                    dev_address=dev_address,
                    gross_amount=gross,
                    platform_tax=tax,
                    dev_net=dev_net,
                )
                logger.info(
                    "SETTLE %s -> SUCCESS: dev=%s +$%.2f USDT  "
                    "[gross=$%.2f  tax=$%.2f  treasury=$%.2f]",
                    freeze_id, dev_address, dev_net,
                    gross, tax, self._founder_treasury_usdt,
                )

            else:  # FAILED - 100% instant refund
                self._user_balances[receipt.user_id] = (
                    self._user_balances.get(receipt.user_id, 0.0) + gross
                )
                # NO tax, NO dev payment

                detail = SettlementDetail(
                    freeze_id=freeze_id,
                    outcome="REFUNDED",
                    user_id=receipt.user_id,
                    dev_address=dev_address,
                    gross_amount=gross,
                    user_refund=gross,
                )
                logger.info(
                    "SETTLE %s -> REFUND:  user=%s +$%.2f USDT (100%% back)  "
                    "[gross=$%.2f]",
                    freeze_id, receipt.user_id, gross, gross,
                )

        return detail

    # ── Dynamic Billing (gas-based) ─────────────────────────────────────

    def create_escrow_hold(self, user_id: str, max_budget: float) -> Optional[EscrowHold]:
        """Pre-authorise and freeze *max_budget* from the user's wallet.

        The full ceiling is held in the escrow vault. Only the actual cost
        will be consumed at settlement time; the rest is refunded.
        Returns ``None`` if the user has insufficient balance.
        """
        with self._lock:
            balance = self._user_balances.get(user_id, 0.0)
            if balance < max_budget:
                logger.warning(
                    "INSUFFICIENT USDT: user=%s has $%.2f, needs $%.2f",
                    user_id, balance, max_budget,
                )
                return None

            self._user_balances[user_id] = balance - max_budget
            self._freeze_counter += 1
            hold = EscrowHold(
                escrow_id=f"escrow-{self._freeze_counter:04d}",
                user_id=user_id,
                max_budget=max_budget,
            )
            self._escrow_vault[hold.escrow_id] = hold
        logger.info(
            "ESCROW-HOLD %s → $%.2f USDT frozen (max budget)  [user=%s]",
            hold.escrow_id, max_budget, user_id,
        )
        return hold

    def release_escrow_dynamic(
        self,
        escrow_id: str,
        user_id: str,
        developer_id: str,
        execution_time: float,
        developer_premium: float = 0.0,
        success: bool = True,
        skill_id: str = "",
    ) -> Optional[DynamicSettlementDetail]:
        """Release an escrow hold with gas-based dynamic billing.

        **On SUCCESS:**
          1. ``gas_cost = execution_time * BASE_GAS_RATE``
          2. ``total_cost = gas_cost + developer_premium`` (capped at max_budget)
          3. ``platform_tax = total_cost * PLATFORM_TAX_RATE``  ->  founder_treasury
          4. ``developer_payout = total_cost - platform_tax``    ->  developer
          5. ``unused_refund = max_budget - total_cost``         ->  user

        **On FAILED:**
          100 % of the frozen *max_budget* is returned to the user.
        """
        with self._lock:
            hold = self._escrow_vault.pop(escrow_id, None)
            if hold is None:
                logger.error("Escrow hold not found: %s", escrow_id)
                return None

            max_budget = hold.max_budget

            if success:
                gas_cost = execution_time * BASE_GAS_RATE
                total_cost = gas_cost + developer_premium
                total_cost = min(total_cost, max_budget)  # never exceed the ceiling
                platform_tax = round(total_cost * PLATFORM_TAX_RATE, 2)
                developer_payout = round(total_cost - platform_tax, 2)
                unused_refund = round(max_budget - total_cost, 2)

                # Distribute
                self._founder_treasury_usdt += platform_tax
                self._dev_balances[developer_id] = (
                    self._dev_balances.get(developer_id, 0.0) + developer_payout
                )
                self._user_balances[user_id] = (
                    self._user_balances.get(user_id, 0.0) + unused_refund
                )

                detail = DynamicSettlementDetail(
                    escrow_id=escrow_id,
                    outcome="COMPLETED",
                    user_id=user_id,
                    developer_id=developer_id,
                    execution_time=execution_time,
                    gas_rate=BASE_GAS_RATE,
                    gas_cost=gas_cost,
                    developer_premium=developer_premium,
                    max_budget=max_budget,
                    total_cost=total_cost,
                    platform_tax=platform_tax,
                    developer_payout=developer_payout,
                    unused_refund=unused_refund,
                )
                logger.info(
                    "ESCROW-RELEASE %s -> COMPLETED  [gas=$%.4f  premium=$%.2f  "
                    "tax=$%.2f  dev=$%.2f  refund=$%.2f]",
                    escrow_id, gas_cost, developer_premium,
                    platform_tax, developer_payout, unused_refund,
                )

                # Record skill usage for rating gating
                if skill_id:
                    if user_id not in self._user_skill_usage:
                        self._user_skill_usage[user_id] = set()
                    self._user_skill_usage[user_id].add(skill_id)
                    self._user_reputation.setdefault(user_id, 1.0)

            else:  # FAILED - 100 % instant refund
                self._user_balances[user_id] = (
                    self._user_balances.get(user_id, 0.0) + max_budget
                )

                detail = DynamicSettlementDetail(
                    escrow_id=escrow_id,
                    outcome="REFUNDED",
                    user_id=user_id,
                    developer_id=developer_id,
                    execution_time=execution_time,
                    gas_rate=BASE_GAS_RATE,
                    gas_cost=0.0,
                    developer_premium=0.0,
                    max_budget=max_budget,
                    total_cost=0.0,
                    platform_tax=0.0,
                    developer_payout=0.0,
                    unused_refund=max_budget,
                )
                logger.info(
                    "ESCROW-RELEASE %s -> REFUNDED  [100%% back  $%.2f USDT -> %s]",
                    escrow_id, max_budget, user_id,
                )

        return detail
