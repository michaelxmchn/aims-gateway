"""MockLedger — Non-Custodial Escrow & Settlement (Layer 0).

Implements the two-step transaction lifecycle:
  1. freeze_points()  — reserve points when a workflow starts
  2. settle_transaction() — commit or refund based on ExecutionReceipt

Settlement rules:
  - Receipt.status == "SUCCESS" → points transferred to developer
  - Receipt.status == "FAILED"  → points refunded to user + 2.0 slash from developer staked_points

All operations are in-memory (mock) for MVP. Real implementation talks
to the Base chain via the AIMS Marketplace contract.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

from src.runtime.sandbox import ExecutionReceipt

logger = logging.getLogger(__name__)

SLASH_AMOUNT = 2.0
"""Points slashed from developer's staked_points on each failed execution."""


@dataclass
class FreezeReceipt:
    """Proof that points were frozen for a workflow."""

    freeze_id: str
    user: str
    developer: str
    points: int
    skill_name: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class SettlementDetail:
    """Result of settling a frozen transaction."""

    freeze_id: str
    outcome: str  # "TRANSFERRED" | "REFUNDED" | "SLASHED"
    user: str
    developer: str
    points_moved: int
    slashed_from_dev: float = 0.0
    developer_remaining_staked: float = 0.0


class MockLedger:
    """In-memory mock of the on-chain escrow and settlement contract.

    Maintains balance ledgers for users and developers, and a frozen-pool
    for in-flight transactions.
    """

    def __init__(self) -> None:
        self._user_balances: Dict[str, int] = {}
        self._dev_balances: Dict[str, int] = {}
        self._frozen: Dict[str, FreezeReceipt] = {}
        self._freeze_counter: int = 0

    # ── balance management ──────────────────────────────────────────────

    def seed_balance(self, user: str, points: int) -> None:
        """Seed a user with initial points for testing."""
        self._user_balances[user] = self._user_balances.get(user, 0) + points
        logger.info("Seeded %s +%d points (balance=%d)", user, points, self._user_balances[user])

    def get_user_balance(self, user: str) -> int:
        return self._user_balances.get(user, 0)

    def get_dev_balance(self, dev: str) -> int:
        return self._dev_balances.get(dev, 0)

    # ── two-step escrow ─────────────────────────────────────────────────

    def freeze_points(self, user: str, developer: str, skill_name: str, points: int) -> Optional[FreezeReceipt]:
        """Step 1: Freeze points from the user's balance for this workflow.

        Returns None if insufficient balance.
        """
        balance = self._user_balances.get(user, 0)
        if balance < points:
            logger.warning(
                "Insufficient balance: user=%s has %d, needs %d",
                user, balance, points,
            )
            return None

        self._user_balances[user] = balance - points
        self._freeze_counter += 1
        receipt = FreezeReceipt(
            freeze_id=f"frz-{self._freeze_counter:04d}",
            user=user,
            developer=developer,
            points=points,
            skill_name=skill_name,
        )
        self._frozen[receipt.freeze_id] = receipt
        logger.info(
            "FREEZE %s: %s → %d pts (%s '%s')",
            receipt.freeze_id, user, points, developer, skill_name,
        )
        return receipt

    def settle_transaction(
        self,
        freeze_id: str,
        receipt: ExecutionReceipt,
        dev_staked_points: float = 0.0,
    ) -> Optional[SettlementDetail]:
        """Step 2: Settle based on execution result.

        SUCCESS → transfer frozen points to developer.
        FAILED  → refund points to user, slash 2.0 from developer's staked.

        Returns None if freeze_id not found.
        """
        freeze = self._frozen.pop(freeze_id, None)
        if freeze is None:
            logger.error("Freeze receipt not found: %s", freeze_id)
            return None

        if receipt.status == "SUCCESS":
            # Transfer to developer
            self._dev_balances[freeze.developer] = (
                self._dev_balances.get(freeze.developer, 0) + freeze.points
            )
            detail = SettlementDetail(
                freeze_id=freeze_id,
                outcome="TRANSFERRED",
                user=freeze.user,
                developer=freeze.developer,
                points_moved=freeze.points,
            )
            logger.info(
                "SETTLE %s → TRANSFERRED: %s +%d pts (dev balance=%d)",
                freeze_id, freeze.developer, freeze.points,
                self._dev_balances[freeze.developer],
            )

        else:  # FAILED
            # Refund user
            self._user_balances[freeze.user] = (
                self._user_balances.get(freeze.user, 0) + freeze.points
            )
            # Slash developer's staked points
            remaining = max(0.0, dev_staked_points - SLASH_AMOUNT)

            detail = SettlementDetail(
                freeze_id=freeze_id,
                outcome="REFUNDED" if SLASH_AMOUNT <= 0 else "SLASHED",
                user=freeze.user,
                developer=freeze.developer,
                points_moved=freeze.points,
                slashed_from_dev=SLASH_AMOUNT,
                developer_remaining_staked=remaining,
            )
            logger.info(
                "SETTLE %s → REFUNDED: %s +%d pts | SLASHED dev -%.1f staked (remaining=%.1f)",
                freeze_id, freeze.user, freeze.points, SLASH_AMOUNT, remaining,
            )

        return detail
