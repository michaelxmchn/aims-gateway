"""Billing engine for the AIMS Web3 settlement system (Layer 3.5).

Acts as an **on-chain settlement orchestrator** — no longer manages Redis
credit balances.  Instead it:

1. Reads user deposit balances from the settlement contract (view function).
2. Calls ``settleTask`` on the contract via the oracle path.
3. Generates Proof-of-Task (PoT) receipts that workers use to claim rewards.

Usage::

    billing = BillingEngine(storage=storage, contract_client=contract, pot_manager=pot)
    balance = billing.check_user_balance("0xUserAddress...")
    result = billing.request_settlement("task-0001", "0xUser...", "0xWorker...")
    # result["pot"] → ProofOfTask
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from eth_utils import keccak

from src.chain.contract_client import SettlementContractClient
from src.chain.nonce_manager import NonceManager
from src.chain.pot import POTManager, ProofOfTask
from src.gateway.storage import Storage

logger = logging.getLogger(__name__)

# USDC uses 6 decimal places on most EVM chains.
USDC_DECIMALS = 6
USDC_UNIT = 10**USDC_DECIMALS  # 1_000_000


class BillingEngine:
    """Orchestrates on-chain settlement for the AIMS credit system.

    Each task costs ``COST_PER_TASK`` USDC (0.05).  On SUCCESS, the gateway
    oracle calls ``settleTask`` on the contract which splits 80/20 between
    the worker and platform owner.  The worker receives a Proof-of-Task (PoT)
    enabling them to call ``claimReward`` on-chain.
    """

    COST_PER_TASK_USDC: int = 50_000  # 0.05 USDC in atomic units (6 decimals)

    def __init__(
        self,
        storage: Storage,
        owner_address: str = "0xOwner000000000000000000000000000000000001",
        gateway_address: str = "0xGateway000000000000000000000000000000000001",
        contract_client: Optional[SettlementContractClient] = None,
        pot_manager: Optional[POTManager] = None,
    ) -> None:
        self._storage = storage
        self._owner_address = owner_address
        self._gateway_address = gateway_address
        self._contract = contract_client
        self._pot_manager = pot_manager

        self._nonce_manager = NonceManager(storage)

    # ── Balance (view function, no gas) ───────────────────────────────────

    def check_user_balance(self, user_address: str) -> int:
        """Read the user's deposited USDC balance from the contract.

        Returns the balance in atomic USDC units (6 decimals).
        """
        if self._contract is None:
            logger.warning("No contract client configured — returning 0 for %s", user_address)
            return 0
        return self._contract.get_user_balance(user_address)

    # ── Settlement orchestration ─────────────────────────────────────────

    def request_settlement(
        self,
        task_id: str,
        user_address: str,
        worker_address: str,
    ) -> dict[str, Any]:
        """Request on-chain settlement for a completed task.

        Flow:
        1. Check that the user's deposited balance covers ``COST_PER_TASK_USDC``.
        2. Get the next monotonic nonce for the gateway.
        3. Call ``settleTask`` on the settlement contract.
        4. Generate a Proof-of-Task for the worker.
        5. Return a receipt including the PoT.

        Args:
            task_id:        Unique task identifier.
            user_address:   EVM address of the user whose deposit is charged.
            worker_address: EVM address of the worker that executed the task.

        Returns:
            A receipt dict with keys:
              - ``task_id``
              - ``user_address``
              - ``worker_address``
              - ``amount`` (COST_PER_TASK_USDC)
              - ``nonce``
              - ``pot`` (ProofOfTask or None)
              - ``status`` ("COMPLETED" | "FAILED")
              - ``error`` (if any)
        """
        receipt: dict[str, Any] = {
            "task_id": task_id,
            "user_address": user_address,
            "worker_address": worker_address,
            "amount": self.COST_PER_TASK_USDC,
            "nonce": None,
            "pot": None,
            "status": "FAILED",
            "error": "",
        }

        if self._contract is None:
            receipt["error"] = "No contract client configured"
            logger.error("request_settlement: no contract client")
            return receipt

        # ── 1. Check user balance ────────────────────────────────────
        balance = self._contract.get_user_balance(user_address)
        if balance < self.COST_PER_TASK_USDC:
            receipt["error"] = (
                f"Insufficient balance. Required: {self.COST_PER_TASK_USDC}, "
                f"balance: {balance}"
            )
            logger.warning(
                "request_settlement %s: %s", task_id, receipt["error"]
            )
            return receipt

        # ── 2. Get nonce ─────────────────────────────────────────────
        nonce = self._nonce_manager.consume(user_address)
        receipt["nonce"] = nonce

        # ── 3. Call settleTask on contract ──────────────────────────
        try:
            task_id_bytes = keccak(text=task_id)
            self._contract.settle_task(
                task_id=task_id_bytes,
                user=user_address,
                worker=worker_address,
                amount=self.COST_PER_TASK_USDC,
                nonce=nonce,
                gateway_address=self._gateway_address,
            )
        except (ValueError, PermissionError, RuntimeError) as exc:
            receipt["error"] = str(exc)
            logger.error("request_settlement %s: settleTask failed: %s", task_id, exc)
            return receipt

        # ── 4. Generate PoT ──────────────────────────────────────────
        if self._pot_manager is not None:
            try:
                pot = self._pot_manager.generate_pot(task_id, worker_address)
                receipt["pot"] = pot
            except Exception as exc:
                logger.warning(
                    "request_settlement %s: PoT generation failed: %s", task_id, exc
                )

        receipt["status"] = "COMPLETED"
        logger.info(
            "Settlement completed: task=%s user=%s worker=%s nonce=%d",
            task_id, user_address, worker_address, nonce,
        )
        return receipt

    # ── PoT generation helper ────────────────────────────────────────────

    def generate_pot(self, task_id: str, worker_address: str) -> Optional[ProofOfTask]:
        """Generate a Proof-of-Task for the given task and worker.

        Delegates to ``POTManager.generate_pot()``.
        """
        if self._pot_manager is None:
            logger.warning("generate_pot: no POTManager configured")
            return None
        return self._pot_manager.generate_pot(task_id, worker_address)
