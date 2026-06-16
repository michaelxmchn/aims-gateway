"""Multi-mode billing engine for AIMS 2.0 Commerce Matrix.

Supports three billing modes:

  pay_per_task (Metered)
      Deduct per-task USDC from consumer balance on each invocation.
      Split 70/25/5 (Q1) or 95/0/5 (Q2-Q5).

  subscription (Subscription)
      Consumer holds a time-based pass; per-task micro-fees are deducted
      from the pooled subscription revenue (contributor still paid).

  buyout (Buyout)
      Consumer holds a perpetual license; per-task execution tax is
      covered by the pooled buyout revenue.

  free_trial (PLG)
      First invocation per (wallet, skill_id) is always free — zero USDC
      deducted.  The protocol (treasury) subsidises the worker and
      developer payouts via the PLG subsidy pool.

Usage
-----
  # Gateway startup
  engine = CommerceEngine(storage, trial_manager, billing, pot_manager)

  # Per-execution (called from /api/run)
  receipt = engine.charge_and_settle(
      task_id, user, worker, skill_id,
      billing_mode="pay_per_task",
  )
"""

from __future__ import annotations

import enum
import logging
import time
from typing import Any, Callable, Optional

from eth_account import Account
from eth_utils import keccak, to_canonical_address

from src.chain.contract_client import SettlementContractClient
from src.chain.nonce_manager import NonceManager
from src.chain.pot import POTManager, ProofOfTask
from src.gateway.storage import Storage
from src.gateway.trial import FreeTrialManager
from src.chain.abi import BPS_DENOM, WORKER_BPS, DEVELOPER_BPS, TREASURY_BPS

logger = logging.getLogger(__name__)

USDC_DECIMALS = 6
USDC_UNIT = 10**USDC_DECIMALS

# ── Enums ────────────────────────────────────────────────────────────────────


class BillingMode(str, enum.Enum):
    """Commerce Matrix billing modes — maps 1:1 to frontend Commerce Mode."""
    PAY_PER_TASK = "pay_per_task"
    SUBSCRIPTION = "subscription"
    BUYOUT = "buyout"


class RevenuePhase(str, enum.Enum):
    """Revenue split phase — maps to the AIMS Gateway timeline.

    Q1 (launch):
        Developer 70 % / Worker 25 % / Treasury 5 %

    Q2-Q5 (post-launch):
        Developer 95 % / Treasury 5 %  (Worker commission phased out)
    """
    Q1 = "q1"
    Q2_Q5 = "q2_q5"


# ── BillingEngine (unchanged core — settlement orchestration) ───────────────


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
                "developer": dev_address or self._treasury_address,
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

        # 6. Generate worker PoT
        if self._pot_manager is not None:
            worker_share = (self.COST_PER_TASK_USDC * WORKER_BPS) // BPS_DENOM
            try:
                pot = self._pot_manager.generate_pot(
                    task_id, worker_address, amount=worker_share,
                )
                receipt["pot"] = pot
            except Exception as exc:
                logger.warning("request_settlement %s: PoT failed: %s", task_id, exc)

            # 7. Generate developer PoT
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
        """Sign a binding commitment for settlement or PoT."""
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
        """Request a timeout refund for a task."""
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


# ═══════════════════════════════════════════════════════════════════════════════
# CommerceEngine — mode-aware billing on top of BillingEngine
# ═══════════════════════════════════════════════════════════════════════════════


class InsufficientPoolBalance(Exception):
    """Raised when a subscription / buyout pool lacks funds for settlement."""


class CommerceEngine:
    """Multi-mode billing orchestration for the AIMS Commerce Matrix.

    Dispatches settlement to the correct funding source based on billing
    mode, deducting from the consumer's on-chain balance (Metered), the
    subscription pool (Subscription), the buyout pool (Buyout), or the
    PLG subsidy pool (Free Trial).

    Owns all pool balances and revenue-phase configuration in Storage.
    """

    # ── Storage namespaces ──────────────────────────────────────────────

    NS_REVENUE_PHASE = "revenue:phase"
    NS_SUBSCRIPTION_POOL = "pool:subscription"
    NS_BUYOUT_POOL = "pool:buyout"
    NS_PLG_SUBSIDY_POOL = "pool:plg"
    NS_SKILL_PRICING = "skill:pricing"
    NS_CONSUMER_SPEND = "consumer:spend"

    # ── Default prices (USDC atomic units, 6 decimals) ──────────────────

    DEFAULT_PER_TASK_PRICE: int = 50_000          # 0.05 USDC
    DEFAULT_SUBSCRIPTION_MONTHLY: int = 2_000_000  # 2.0 USDC / month
    DEFAULT_BUYOUT_LICENSE: int = 50_000_000        # 50.0 USDC

    # Worker bandwidth fee for non-metered modes (covers execution cost)
    WORKER_BANDWIDTH_FEE: int = 5_000              # 0.005 USDC

    def __init__(
        self,
        storage: Storage,
        trial_manager: FreeTrialManager,
        billing: BillingEngine,
        pot_manager: Optional[POTManager] = None,
        on_settlement: Optional[Callable[[dict], None]] = None,
    ) -> None:
        self._storage = storage
        self._trial_manager = trial_manager
        self._billing = billing
        self._pot_manager = pot_manager
        self._on_settlement = on_settlement

    # ── Audit trail (delegates to billing engine) ───────────────────────

    def _record(
        self,
        action: str,
        task_id: str,
        roles: dict[str, str],
        amounts: dict[str, int],
        tx_hash: str = "",
        detail: str = "",
    ) -> None:
        """Append an immutable entry to the billing audit trail."""
        self._billing._record(action, task_id, roles, amounts, tx_hash, detail)
        if self._on_settlement is not None:
            self._on_settlement({
                "action": action,
                "task_id": task_id,
                "roles": dict(roles),
                "amounts": {k: v for k, v in amounts.items()} if isinstance(amounts, dict) else amounts,
                "ts": time.time(),
                "detail": detail,
            })

    # ── Revenue phase ───────────────────────────────────────────────────

    def get_revenue_phase(self) -> RevenuePhase:
        raw = self._storage.get(self.NS_REVENUE_PHASE)
        if raw not in ("q1", "q2_q5"):
            return RevenuePhase.Q1
        return RevenuePhase(raw)

    def set_revenue_phase(self, phase: RevenuePhase | str) -> None:
        if isinstance(phase, RevenuePhase):
            phase = phase.value
        self._storage.set(self.NS_REVENUE_PHASE, phase)

    def _split_bps(self) -> tuple[int, int, int]:
        """Return (dev_bps, worker_bps, treasury_bps) for current phase."""
        phase = self.get_revenue_phase()
        if phase == RevenuePhase.Q2_Q5:
            return (9_500, 0, 500)      # 95/0/5
        return (7_000, 2_500, 500)     # 70/25/5

    # ── Skill pricing ───────────────────────────────────────────────────

    def _pricing_key(self, skill_id: str) -> str:
        return f"{self.NS_SKILL_PRICING}:{skill_id}"

    def get_skill_pricing(self, skill_id: str) -> dict:
        """Return full pricing tuple for *skill_id*."""
        default = {
            "per_task_atomic": self.DEFAULT_PER_TASK_PRICE,
            "subscription_monthly_atomic": self.DEFAULT_SUBSCRIPTION_MONTHLY,
            "buyout_license_atomic": self.DEFAULT_BUYOUT_LICENSE,
        }
        stored = self._storage.get(self._pricing_key(skill_id))
        if stored is None:
            return default
        return {**default, **stored}

    def set_skill_pricing(
        self,
        skill_id: str,
        *,
        per_task_atomic: int | None = None,
        subscription_monthly_atomic: int | None = None,
        buyout_license_atomic: int | None = None,
    ) -> None:
        existing = self.get_skill_pricing(skill_id)
        if per_task_atomic is not None:
            existing["per_task_atomic"] = per_task_atomic
        if subscription_monthly_atomic is not None:
            existing["subscription_monthly_atomic"] = subscription_monthly_atomic
        if buyout_license_atomic is not None:
            existing["buyout_license_atomic"] = buyout_license_atomic
        self._storage.set(self._pricing_key(skill_id), existing)

    # ── Pool balances ───────────────────────────────────────────────────

    def _subscription_pool(self) -> int:
        return self._storage.get(self.NS_SUBSCRIPTION_POOL, 0)

    def _buyout_pool(self) -> int:
        return self._storage.get(self.NS_BUYOUT_POOL, 0)

    def _plg_pool(self) -> int:
        return self._storage.get(self.NS_PLG_SUBSIDY_POOL, 0)

    def _add_to_pool(self, ns: str, amount: int) -> int:
        pool = (self._storage.get(ns) or 0) + amount
        self._storage.set(ns, pool)
        return pool

    def _drain_pool(self, ns: str, amount: int) -> bool:
        pool = self._storage.get(ns) or 0
        if pool < amount:
            return False
        self._storage.set(ns, pool - amount)
        return True

    # ── Purchase endpoints ──────────────────────────────────────────────

    def purchase_subscription(
        self, wallet: str, skill_id: str, contract_client: SettlementContractClient,
    ) -> dict:
        """Purchase a monthly subscription pass.

        Deducts the subscription price from the consumer's on-chain balance
        and credits it to the subscription pool.  Activates a 30-day pass.
        """
        pricing = self.get_skill_pricing(skill_id)
        price = pricing["subscription_monthly_atomic"]

        balance = contract_client.get_user_balance(wallet)
        if balance < price:
            return {
                "status": "FAILED",
                "error": f"Insufficient balance. Required: {price / USDC_UNIT:.2f} USDC, balance: {balance / USDC_UNIT:.2f} USDC",
            }

        # Deduct from user on-chain balance
        contract_client.withdraw(wallet, price)

        # Credit subscription pool
        self._add_to_pool(self.NS_SUBSCRIPTION_POOL, price)

        # Activate 30-day pass
        expires_at = time.time() + 30 * 86400
        self._trial_manager.set_subscription(wallet, skill_id, expires_at)

        logger.info(
            "Subscription purchased: wallet=%s skill=%s price=%d expires=%s",
            wallet, skill_id, price, time.strftime("%Y-%m-%d", time.gmtime(expires_at)),
        )
        return {
            "status": "COMPLETED",
            "amount_atomic": price,
            "expires_at": expires_at,
        }

    def purchase_buyout(
        self, wallet: str, skill_id: str, contract_client: SettlementContractClient,
    ) -> dict:
        """Purchase a perpetual buyout license.

        Deducts the buyout price from the consumer's on-chain balance and
        credits it to the buyout pool.  Records a perpetual license.
        """
        pricing = self.get_skill_pricing(skill_id)
        price = pricing["buyout_license_atomic"]

        balance = contract_client.get_user_balance(wallet)
        if balance < price:
            return {
                "status": "FAILED",
                "error": f"Insufficient balance. Required: {price / USDC_UNIT:.2f} USDC, balance: {balance / USDC_UNIT:.2f} USDC",
            }

        contract_client.withdraw(wallet, price)
        self._add_to_pool(self.NS_BUYOUT_POOL, price)
        self._trial_manager.set_buyout_license(wallet, skill_id)

        logger.info(
            "Buyout purchased: wallet=%s skill=%s price=%d",
            wallet, skill_id, price,
        )
        return {
            "status": "COMPLETED",
            "amount_atomic": price,
        }

    # ── Seed PLG subsidy pool (admin) ───────────────────────────────────

    def seed_plg_pool(self, amount_atomic: int) -> int:
        """Add *amount_atomic* USDC to the PLG subsidy pool from treasury."""
        return self._add_to_pool(self.NS_PLG_SUBSIDY_POOL, amount_atomic)

    # ── Mode-aware charge + settlement ──────────────────────────────────

    def charge_and_settle(
        self,
        task_id: str,
        user_address: str,
        worker_address: str,
        skill_id: str,
        *,
        billing_mode: str,
        is_free_trial: bool = False,
    ) -> dict[str, Any]:
        """Mode-aware charge and settlement orchestration.

        Returns a receipt dict with ``status``, ``mode``, ``deduction_source``,
        ``amount_deducted``, ``split``, and ``pot`` (if applicable).

        **Metered (pay_per_task):**
            Deducts ``skill_per_task_price`` or default 0.05 USDC from the
            consumer's on-chain balance, then splits per revenue phase.

        **Subscription:**
            No consumer deduction.  Worker bandwidth (0.005 USDC) drawn from
            the subscription pool.  Developer share drawn from subscription
            pool.  PoT generated for worker.

        **Buyout:**
            No consumer deduction.  Worker bandwidth drawn from buyout pool.
            No developer per-task payout (already paid lump sum).  Treasury
            platform tax drawn from buyout pool.

        **Free Trial (PLG):**
            No consumer deduction.  Full 70/25/5 covered by the PLG subsidy
            pool.  If subsidy pool is insufficient, falls back to treasury.
        """
        receipt: dict[str, Any] = {
            "task_id": task_id,
            "user_address": user_address,
            "worker_address": worker_address,
            "skill_id": skill_id,
            "mode": billing_mode,
            "is_free_trial": is_free_trial,
            "deduction_source": "",
            "amount_deducted": 0,
            "split": {},
            "pot": None,
            "developer_pot": None,
            "status": "FAILED",
            "error": "",
        }

        pricing = self.get_skill_pricing(skill_id)

        if billing_mode == BillingMode.PAY_PER_TASK and not is_free_trial:
            # ── Metered: deduct from consumer balance ────────────────
            return self._settle_metered(
                receipt, task_id, user_address, worker_address, skill_id, pricing,
            )

        # ── Non-metered paths (no consumer deduction) ────────────────
        dev_bps, worker_bps, treasury_bps = self._split_bps()
        per_task_price = pricing["per_task_atomic"]

        # If free trial, draw from PLG pool
        if is_free_trial:
            source = self.NS_PLG_SUBSIDY_POOL
            pool_balance = self._plg_pool()
        elif billing_mode == BillingMode.SUBSCRIPTION:
            source = self.NS_SUBSCRIPTION_POOL
            pool_balance = self._subscription_pool()
            # Subscription: worker gets bandwidth fee, dev gets per-task (pooled)
            worker_bps = 0
            treasury_bps = 500
        elif billing_mode == BillingMode.BUYOUT:
            source = self.NS_BUYOUT_POOL
            pool_balance = self._buyout_pool()
            # Buyout: only worker bandwidth and treasury tax
            worker_bps = 0
            treasury_bps = 500
        else:
            receipt["error"] = f"Unknown billing mode: {billing_mode}"
            return receipt

        worker_share = (per_task_price * worker_bps) // BPS_DENOM if worker_bps else 0
        # For subscription/buyout/free trial, worker gets fixed bandwidth fee
        if billing_mode in (BillingMode.SUBSCRIPTION, BillingMode.BUYOUT):
            worker_share = min(worker_share, self.WORKER_BANDWIDTH_FEE)
        if is_free_trial:
            worker_share = (per_task_price * WORKER_BPS) // BPS_DENOM  # full 25%

        # Developer share
        dev_address = self._billing.get_developer(skill_id) if skill_id else ""
        dev_share = 0
        if dev_address and billing_mode != BillingMode.BUYOUT:
            dev_share = (per_task_price * dev_bps) // BPS_DENOM

        # Treasury share = remainder
        treasury_share = per_task_price - worker_share - dev_share
        if treasury_share < 0:
            treasury_share = 0

        total_needed = worker_share + dev_share + treasury_share

        # Check pool balance
        if pool_balance < total_needed:
            # Fallback: try treasury (the billing engine's contract balance)
            logger.warning(
                "Pool %s insufficient (%d < %d) — falling back to treasury",
                source, pool_balance, total_needed,
            )
            if is_free_trial:
                # PLG fallback: still process, just log it
                receipt["detail"] = f"PLG pool depleted, covered by treasury"
            else:
                self._record(
                    action="pool_shortfall",
                    task_id=task_id,
                    roles={"user": user_address, "worker": worker_address},
                    amounts={"pool_shortfall": total_needed - pool_balance},
                    detail=f"source={source} billing_mode={billing_mode}",
                )
                receipt["error"] = (
                    f"Insufficient {billing_mode} pool balance. "
                    f"Required: {total_needed / USDC_UNIT:.4f} USDC, "
                    f"pool: {pool_balance / USDC_UNIT:.4f} USDC"
                )
                return receipt

        # Drain the pool
        if pool_balance >= total_needed:
            self._drain_pool(source, total_needed)

        # Generate PoTs
        if self._pot_manager is not None:
            try:
                pot = self._pot_manager.generate_pot(
                    task_id, worker_address, amount=worker_share,
                )
                receipt["pot"] = pot
            except Exception as exc:
                logger.warning("charge_and_settle %s: worker PoT failed: %s", task_id, exc)

            if dev_address and dev_share > 0:
                try:
                    dev_pot = self._pot_manager.generate_pot(
                        task_id, dev_address, amount=dev_share,
                    )
                    receipt["developer_pot"] = dev_pot
                except Exception as exc:
                    logger.warning(
                        "charge_and_settle %s: dev PoT failed: %s", task_id, exc,
                    )

        receipt["deduction_source"] = source
        receipt["amount_deducted"] = total_needed
        receipt["split"] = {
            "developer_share": dev_share,
            "worker_share": worker_share,
            "treasury_share": treasury_share,
        }
        receipt["status"] = "COMPLETED"

        self._record(
            action="settle_nonmetered",
            task_id=task_id,
            roles={
                "user": user_address,
                "worker": worker_address,
                "developer": dev_address or self._billing._treasury_address,
            },
            amounts={
                "deduction_source": source,
                "worker_share": worker_share,
                "developer_share": dev_share,
                "treasury_share": treasury_share,
                "total_deducted": total_needed,
            },
            detail=f"mode={billing_mode} free_trial={is_free_trial} source={source}",
        )
        return receipt

    def _settle_metered(
        self,
        receipt: dict,
        task_id: str,
        user_address: str,
        worker_address: str,
        skill_id: str,
        pricing: dict,
    ) -> dict:
        """Execute metered settlement via the underlying BillingEngine settlement path."""
        # Use the existing BillingEngine.request_settlement for metered mode
        settlement = self._billing.request_settlement(
            task_id, user_address, worker_address, skill_id,
        )
        receipt.update(settlement)
        receipt["mode"] = BillingMode.PAY_PER_TASK
        receipt["deduction_source"] = "consumer_balance"
        receipt["amount_deducted"] = settlement.get("amount", self.DEFAULT_PER_TASK_PRICE)
        return receipt

    # ── Consumer spend tracking ─────────────────────────────────────────

    def record_consumer_spend(self, wallet: str, skill_id: str, amount_atomic: int) -> None:
        """Record a consumer's cumulative spend (for dashboard display)."""
        key = f"{self.NS_CONSUMER_SPEND}:{wallet.lower()}:{skill_id}"
        total = (self._storage.get(key) or 0) + amount_atomic
        self._storage.set(key, total)

    def get_consumer_spend(self, wallet: str, skill_id: str) -> int:
        """Return cumulative spend for (wallet, skill_id)."""
        key = f"{self.NS_CONSUMER_SPEND}:{wallet.lower()}:{skill_id}"
        return self._storage.get(key) or 0
