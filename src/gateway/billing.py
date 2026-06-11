"""Billing engine for the AIMS Agent Gateway (Layer 5).

Orchestrates on-chain settlement for the AIMS DePIN mesh.  Each task costs
``COST_PER_TASK`` USDC (0.05).  On SUCCESS, the gateway oracle calls
``settleTask`` on the contract which splits 70/25/5 between developer, worker,
and treasury.

Key differences from the previous billing engine:
  - 70/25/5 split (old: 80/20)
  - Compound nonce (nonce + taskId) replay protection
  - Deadline-based settlement authorization
  - Developer registry lookup
  - Timeout refund support
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from eth_account import Account
from eth_utils import keccak, to_canonical_address

from src.chain.contract_client import SettlementContractClient
from src.chain.nonce_manager import NonceManager
from src.chain.pot import POTManager, ProofOfTask
from src.gateway.storage import Storage
from src.chain.abi import BPS_DENOM, WORKER_BPS, DEVELOPER_BPS

logger = logging.getLogger(__name__)

# USDC uses 6 decimal places on most EVM chains.
USDC_DECIMALS = 6
USDC_UNIT = 10**USDC_DECIMALS  # 1_000_000


class BillingEngine:
    """Orchestrates on-chain settlement for the AIMS credit system.

    Each task costs ``COST_PER_TASK`` USDC (0.05).  On SUCCESS, the gateway
    oracle calls ``settleTask`` on the contract which splits 70/25/5 between
    developer / worker / treasury.

    Maintains a reversible audit trail — every settlement event is recorded
    in ``_audit_ledger`` with [timestamp, tx_hash, action, roles, amount]
    for retrospective query and reconciliation.
    """

    COST_PER_TASK_USDC: int = 50_000  # 0.05 USDC in atomic units (6 decimals)
    SETTLEMENT_DEADLINE_SECONDS: int = 300  # 5 min deadline for settlement tx

    def __init__(
        self,
        storage: Storage,
        treasury_address: str = "0xTreasury00000000000000000000000000000000001",
        gateway_address: str = "0xGateway000000000000000000000000000000000001",
        gateway_signing_key: str = "",
        contract_client: Optional[SettlementContractClient] = None,
        pot_manager: Optional[POTManager] = None,
    ) -> None:
        self._storage = storage
        self._treasury_address = treasury_address
        self._gateway_address = gateway_address
        self._gateway_signing_key = gateway_signing_key
        self._contract = contract_client
        self._pot_manager = pot_manager
        self._nonce_manager = NonceManager(storage)
        # Reversible audit trail: list of dicts with keys:
        #   ts, tx_hash, action, task_id, roles, amounts, detail
        self._audit_ledger: list[dict] = []

    # ── Audit trail ─────────────────────────────────────────────────────

    def _record(
        self,
        action: str,
        task_id: str,
        roles: dict[str, str],
        amounts: dict[str, int],
        tx_hash: str = "",
        detail: str = "",
    ) -> None:
        """Append an immutable entry to the audit trail."""
        self._audit_ledger.append({
            "ts": time.time(),
            "tx_hash": tx_hash,
            "action": action,
            "task_id": task_id,
            "roles": dict(roles),
            "amounts": dict(amounts),
            "detail": detail,
        })

    def get_audit_trail(
        self,
        task_id: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Query the reversible audit trail, optionally filtered by task_id."""
        if task_id:
            return [e for e in self._audit_ledger if e["task_id"] == task_id][-limit:]
        return self._audit_ledger[-limit:]

    def get_audit_summary(self) -> dict:
        """Return aggregate settlement stats from the audit trail."""
        total_settled = 0
        action_counts: dict[str, int] = {}
        for entry in self._audit_ledger:
            action_counts[entry["action"]] = action_counts.get(entry["action"], 0) + 1
            if "amounts" in entry:
                total_settled += sum(
                    v for k, v in entry["amounts"].items()
                    if k in ("user_deduction", "worker_share", "developer_share", "treasury_share")
                )
        return {
            "total_entries": len(self._audit_ledger),
            "total_settled_atomic": total_settled,
            "action_counts": action_counts,
            "last_entry": self._audit_ledger[-1] if self._audit_ledger else None,
        }

    # ── Balance (view function, no gas) ─────────────────────────────────

    def check_user_balance(self, user_address: str, local_fallback: int = 0) -> int:
        """Read the user's deposited USDC balance from the contract.

        In InMemory mode, auto-seeds **10.0 USDC** for any wallet that
        passes signature verification.
        In Web3 mode, returns the sum of on-chain balance + local_fallback
        (proxy deposits tracked in server.py's ``_local_deposits``).
        """
        if self._contract is None:
            logger.warning("No contract client — returning 0 for %s", user_address)
            return 0

        onchain = self._contract.get_user_balance(user_address)

        # Detect Web3 mode: the contract client has a ``_w3`` attribute.
        if hasattr(self._contract, "_w3"):
            return onchain + local_fallback

        # InMemory mode — auto-seed new wallets
        if onchain == 0 and hasattr(self._contract, "deposit"):
            seed_amount = 10 * USDC_UNIT
            self._contract.deposit(user_address, seed_amount)
            logger.info("Auto-seeded %s with 10.0 USDC (InMemory mode)", user_address)
            return seed_amount
        return onchain

    # ── Developer registry ──────────────────────────────────────────────

    def register_developer(self, skill_id: str, developer_address: str) -> None:
        """Register a developer wallet for a skill in the settlement contract."""
        if self._contract is None:
            logger.warning("No contract client — cannot register developer")
            return
        skill_id_hash = keccak(text=skill_id)
        self._contract.register_developer(skill_id_hash, developer_address)
        logger.info(
            "Developer registered: skill=%s developer=%s", skill_id, developer_address,
        )

    def get_developer(self, skill_id: str) -> str:
        """Look up the developer address for a skill."""
        if self._contract is None:
            return ""
        skill_id_hash = keccak(text=skill_id)
        return self._contract.get_developer(skill_id_hash)

    # ── Settlement orchestration ────────────────────────────────────────

    def request_settlement(
        self,
        task_id: str,
        user_address: str,
        worker_address: str,
        skill_id: str = "",
    ) -> dict[str, Any]:
        """Request on-chain settlement for a completed task.

        Flow:
        1. Check user deposit balance.
        2. Get monotonic nonce for the gateway.
        3. Compute gateway ECDSA signature for settlement authorization.
        4. Call ``settleTask`` on the contract with 70/25/5 split.
        5. Generate Proof-of-Task for the worker (and developer PoT).
        6. Return receipt with PoT.

        Args:
            task_id:        Unique task identifier.
            user_address:   EVM address of the user.
            worker_address: EVM address of the worker.
            skill_id:       Skill identifier (used to look up developer).

        Returns:
            Receipt dict with task_id, user, worker, amount, nonce, pot, status.
        """
        receipt: dict[str, Any] = {
            "task_id": task_id,
            "user_address": user_address,
            "worker_address": worker_address,
            "skill_id": skill_id,
            "amount": self.COST_PER_TASK_USDC,
            "nonce": None,
            "pot": None,
            "developer_pot": None,
            "status": "FAILED",
            "error": "",
        }

        if self._contract is None:
            receipt["error"] = "No contract client configured"
            logger.error("request_settlement: no contract client")
            return receipt

        # 1. Check user balance
        balance = self._contract.get_user_balance(user_address)
        if balance < self.COST_PER_TASK_USDC:
            receipt["error"] = (
                f"Insufficient balance. Required: {self.COST_PER_TASK_USDC}, "
                f"balance: {balance}"
            )
            logger.warning("request_settlement %s: %s", task_id, receipt["error"])
            return receipt

        # 2. Get nonce
        nonce = self._nonce_manager.consume(user_address)
        receipt["nonce"] = nonce

        # Compute skill ID hash
        skill_id_hash = keccak(text=skill_id) if skill_id else keccak(text="unknown")

        # 3. Compute gateway signature for settleTask
        # The gateway signs: keccak256(abi.encodePacked(taskId, worker, amount))
        task_id_bytes = keccak(text=task_id)
        gw_sig = self._sign_binding(
            task_id_bytes, worker_address, self.COST_PER_TASK_USDC,
        )

        # 4. Compute deadline
        deadline = int(time.time()) + self.SETTLEMENT_DEADLINE_SECONDS

        # 5. Call settleTask on contract
        try:
            self._contract.settle_task(
                task_id=task_id_bytes,
                user=user_address,
                worker=worker_address,
                skill_id_hash=skill_id_hash,
                amount=self.COST_PER_TASK_USDC,
                nonce=nonce,
                deadline=deadline,
                gateway_address=self._gateway_address,
                gateway_signature=gw_sig,
            )
        except (ValueError, PermissionError, RuntimeError) as exc:
            receipt["error"] = str(exc)
            logger.error("request_settlement %s: settleTask failed: %s", task_id, exc)
            return receipt

        # 5a. Audit trail — record the settlement
        worker_share = (self.COST_PER_TASK_USDC * WORKER_BPS) // BPS_DENOM
        dev_address = self._contract.get_developer(skill_id_hash) if skill_id_hash else ""
        dev_share = (self.COST_PER_TASK_USDC * DEVELOPER_BPS) // BPS_DENOM if dev_address else 0
        treasury_share = self.COST_PER_TASK_USDC - worker_share - dev_share
        self._record(
            action="settle",
            task_id=task_id,
            roles={
                "user": user_address,
                "worker": worker_address,
                "developer": dev_address or treasury_address,
                "gateway": self._gateway_address,
            },
            amounts={
                "user_deduction": self.COST_PER_TASK_USDC,
                "worker_share": worker_share,
                "developer_share": dev_share,
                "treasury_share": treasury_share,
            },
            tx_hash="",
            detail=f"nonce={nonce} skill={skill_id}",
        )

        # 6. Generate worker PoT (signed over worker's 25% share)
        if self._pot_manager is not None:
            worker_share = (self.COST_PER_TASK_USDC * WORKER_BPS) // BPS_DENOM
            try:
                pot = self._pot_manager.generate_pot(
                    task_id, worker_address, amount=worker_share,
                )
                receipt["pot"] = pot
            except Exception as exc:
                logger.warning("request_settlement %s: PoT failed: %s", task_id, exc)

            # 7. Generate developer PoT (signed over developer's 70% share)
            dev_address = self._contract.get_developer(skill_id_hash)
            if dev_address:
                dev_share = (self.COST_PER_TASK_USDC * DEVELOPER_BPS) // BPS_DENOM
                try:
                    dev_pot = self._pot_manager.generate_pot(
                        task_id, dev_address, amount=dev_share,
                    )
                    receipt["developer_pot"] = dev_pot
                except Exception as exc:
                    logger.warning(
                        "request_settlement %s: dev PoT failed: %s", task_id, exc,
                    )

        receipt["status"] = "COMPLETED"
        logger.info(
            "Settlement completed: task=%s user=%s worker=%s nonce=%d",
            task_id, user_address, worker_address, nonce,
        )
        return receipt

    def _sign_binding(
        self,
        task_id_bytes: bytes,
        party_address: str,
        amount: int,
    ) -> str:
        """Sign a binding commitment for settlement or PoT.

        The message: ``keccak256(abi.encodePacked(taskId, party, amount))``
        Matches the Solidity contract's ``_verifyGatewaySignature``.
        """
        if not self._gateway_signing_key:
            logger.warning("No gateway signing key configured")
            return ""
        party_bytes = to_canonical_address(party_address)
        amount_bytes = amount.to_bytes(32, 'big')
        message_hash = keccak(task_id_bytes + party_bytes + amount_bytes)
        signed = Account.unsafe_sign_hash(message_hash, self._gateway_signing_key)
        return signed.signature.hex()

    # ── Timeout refund ──────────────────────────────────────────────────

    def request_refund(self, task_id: str, user_address: str) -> dict[str, Any]:
        """Request a timeout refund for a task.

        Can only be called by the gateway.  Returns the full task amount
        to the user's deposit balance.
        """
        result: dict[str, Any] = {
            "task_id": task_id,
            "user_address": user_address,
            "status": "FAILED",
            "error": "",
        }
        if self._contract is None:
            result["error"] = "No contract client"
            return result

        try:
            self._contract.refund_task(
                task_id=keccak(text=task_id),
                user=user_address,
                amount=self.COST_PER_TASK_USDC,
                reason="timeout",
            )
            result["status"] = "COMPLETED"
            self._record(
                action="refund",
                task_id=task_id,
                roles={"user": user_address, "gateway": self._gateway_address},
                amounts={"refund": self.COST_PER_TASK_USDC},
                detail="timeout refund",
            )
        except (ValueError, RuntimeError) as exc:
            result["error"] = str(exc)
        return result

    # ── PoT generation helper ───────────────────────────────────────────

    def generate_pot(self, task_id: str, worker_address: str) -> Optional[ProofOfTask]:
        """Generate a Proof-of-Task for the given task and worker."""
        if self._pot_manager is None:
            logger.warning("generate_pot: no POTManager configured")
            return None
        return self._pot_manager.generate_pot(task_id, worker_address)
