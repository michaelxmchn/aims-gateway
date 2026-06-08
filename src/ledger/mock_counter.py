"""MockLedger — USDT Just-In-Time Escrow & Settlement (Layer 0).

Simulates a real web3 USD stablecoin clearing house. All balances are
in USDT (float, 2-decimal precision for display).

Lifecycle:
  1. freeze_usdt(user_id, amount) — deduct from user, hold in escrow_vault
  2. settle_escrow(freeze_id, success, dev_address):
       SUCCESS → 1% platform tax → founder_treasury, 99% → developer
       FAILED  → 100% instant refund to user
  3. Escrow vault is cleared after settlement.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger(__name__)

ESCROW_TAX_RATE: float = 0.01
"""1% platform fee on successful settlements — sent to founder treasury."""


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

    # ── balance management ──────────────────────────────────────────────

    def seed_usdt(self, user_id: str, amount: float) -> None:
        """Seed a user with initial USDT for testing."""
        self._user_balances[user_id] = self._user_balances.get(user_id, 0.0) + amount
        logger.info(
            "SEED  %s +$%.2f USDT (balance=$%.2f)",
            user_id, amount, self._user_balances[user_id],
        )

    def get_user_usdt(self, user_id: str) -> float:
        return self._user_balances.get(user_id, 0.0)

    def get_dev_usdt(self, dev_address: str) -> float:
        return self._dev_balances.get(dev_address, 0.0)

    @property
    def founder_treasury_usdt(self) -> float:
        return self._founder_treasury_usdt

    # ── JIT Escrow ─────────────────────────────────────────────────────

    def freeze_usdt(self, user_id: str, amount: float) -> Optional[FreezeReceipt]:
        """Step 1: Freeze USDT from the user's balance into escrow.

        Returns FreezeReceipt on success, None if insufficient balance.
        """
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
        receipt = self._escrow_vault.pop(freeze_id, None)
        if receipt is None:
            logger.error("Escrow receipt not found: %s", freeze_id)
            return None

        gross = receipt.amount

        if success:
            tax = round(gross * ESCROW_TAX_RATE, 2)
            dev_net = round(gross - tax, 2)

            # 1% platform tax → founder treasury
            self._founder_treasury_usdt += tax
            # 99% → developer
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
                "SETTLE %s → SUCCESS: dev=%s +$%.2f USDT  "
                "[gross=$%.2f  tax=$%.2f  treasury=$%.2f]",
                freeze_id, dev_address, dev_net,
                gross, tax, self._founder_treasury_usdt,
            )

        else:  # FAILED — 100% instant refund
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
                "SETTLE %s → REFUND:  user=%s +$%.2f USDT (100%% back)  "
                "[gross=$%.2f]",
                freeze_id, receipt.user_id, gross, gross,
            )

        return detail
