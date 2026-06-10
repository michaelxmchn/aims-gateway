"""Settlement contract client abstraction for AIMSAgentGateway.

Provides an ABC ``SettlementContractClient`` with two implementations:

* ``InMemorySettlementContract`` — pure Python, mirrors the new
  ``AIMSAgentGateway`` Solidity logic exactly (70/25/5 split,
  compound nonce, developer registry, settlement snapshots,
  timeout refund).  Used for tests and local dev.
* ``Web3SettlementContract`` — web3.py production wrapper that calls
  the deployed contract on Base via JSON-RPC.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

from eth_account import Account
from eth_utils import keccak, to_canonical_address

from src.chain.abi import (
    BPS_DENOM,
    DEVELOPER_BPS,
    TREASURY_BPS,
    WORKER_BPS,
)

logger = logging.getLogger(__name__)

# ── Task status enum (mirrors Solidity) ──────────────────────────────────────

TASK_STATUS_NONE = 0
TASK_STATUS_SETTLED = 1
TASK_STATUS_REFUNDED = 2
TASK_STATUS_CLAIMED = 3


# ── Data classes ────────────────────────────────────────────────────────────


@dataclass
class TaskSettlement:
    """Snapshot of a settled task (mirrors Solidity struct)."""

    worker: str
    developer: str
    total_amount: int
    worker_share: int
    developer_share: int
    treasury_share: int
    settled_at: float


class SettlementContractClient(ABC):
    """Abstract interface to the on-chain AIMSAgentGateway contract."""

    @abstractmethod
    def get_user_balance(self, address: str) -> int:
        """Return the deposited balance (USDC, 6 decimals) for *address*."""
        ...

    @abstractmethod
    def deposit(self, user_address: str, amount: int) -> None:
        """Record a deposit of *amount* USDC for *user_address*."""
        ...

    @abstractmethod
    def register_developer(self, skill_id_hash: bytes, developer: str) -> None:
        """Register the developer wallet for a skill."""
        ...

    @abstractmethod
    def get_developer(self, skill_id_hash: bytes) -> str:
        """Return the developer address for a skill, or empty string."""
        ...

    @abstractmethod
    def settle_task(
        self,
        task_id: bytes,
        user: str,
        worker: str,
        skill_id_hash: bytes,
        amount: int,
        nonce: int,
        deadline: int,
        gateway_address: str,
        gateway_signature: str = "",
    ) -> None:
        """Execute settlement with gateway ECDSA signature verification.

        The gateway signs ``keccak256(abi.encodePacked(taskId, worker, amount))``.
        Anyone can submit — the contract recovers the signer and checks it.

        On success, the 70/25/5 split is credited to developer/worker/treasury.
        """
        ...

    @abstractmethod
    def refund_task(
        self, task_id: bytes, user: str, amount: int, reason: str,
    ) -> None:
        """Refund a settled task (only gateway). Returns USDC to user."""
        ...

    @abstractmethod
    def get_pending_payout(self, address: str) -> int:
        """Return the pending payout for *address*."""
        ...

    @abstractmethod
    def claim_reward(
        self, task_id: bytes, claimant: str, gateway_signature: str = "",
    ) -> int:
        """Claim worker's 25 % reward. Returns the amount transferred."""
        ...

    @abstractmethod
    def claim_developer_reward(
        self, task_id: bytes, developer: str, gateway_signature: str = "",
    ) -> int:
        """Claim developer's 70 % reward. Returns the amount transferred."""
        ...

    @abstractmethod
    def get_task_status(self, task_id: bytes) -> int:
        """Return the task status (0=None, 1=Settled, 2=Refunded, 3=Claimed)."""
        ...

    @abstractmethod
    def get_task_settlement(self, task_id: bytes) -> Optional[TaskSettlement]:
        """Return the settlement snapshot for a task, or None."""
        ...

    @abstractmethod
    def is_compound_nonce_used(self, nonce: int, task_id: bytes) -> bool:
        """Check whether ``keccak256(nonce, taskId)`` has been used."""
        ...


# ── In-Memory Implementation ───────────────────────────────────────────────


class InMemorySettlementContract(SettlementContractClient):
    """Pure-Python in-memory mirror of the AIMSAgentGateway Solidity contract.

    Mirrors all Solidity logic: 70/25/5 split, compound nonce,
    developer registry, settlement snapshots, timeout refund,
    task lifecycle state machine.
    """

    MAX_TIMEOUT = 300  # matches Solidity MAX_TIMEOUT

    def __init__(
        self,
        gateway_address: str,
        treasury: str,
        gateway_signing_key: str | None = None,
    ) -> None:
        self._gateway_address = gateway_address.lower()
        self._treasury = treasury.lower()
        self._gateway_signing_key = gateway_signing_key

        # User deposits
        self._balances: dict[str, int] = {}

        # Developer registry: skill_id_hash (bytes32) → address
        self._developers: dict[bytes, str] = {}

        # Task lifecycle: task_id bytes → status int
        self._task_status: dict[bytes, int] = {}

        # Settlement snapshots
        self._settlements: dict[bytes, TaskSettlement] = {}

        # Compound nonce: keccak256(nonce, taskId) → True
        self._used_compound_nonces: set[bytes] = set()

        # Pending payouts
        self._pending_payouts: dict[str, int] = {}

        # Accumulated treasury fees
        self._accumulated_treasury_fees: int = 0

    # ── Gateway address ─────────────────────────────────────────────────

    @property
    def gateway_address(self) -> str:
        return self._gateway_address

    def set_gateway(self, new_address: str, caller: str) -> None:
        if caller.lower() != self._gateway_address:
            raise PermissionError("onlyGateway: caller is not the gateway")
        self._gateway_address = new_address.lower()

    # ── User balance ────────────────────────────────────────────────────

    def get_user_balance(self, address: str) -> int:
        return self._balances.get(address.lower(), 0)

    def balance_of(self, address: str) -> int:
        return self.get_user_balance(address)

    def deposit(self, user_address: str, amount: int) -> None:
        if amount <= 0:
            raise ValueError("amount must be > 0")
        addr = user_address.lower()
        self._balances[addr] = self._balances.get(addr, 0) + amount

    def withdraw(self, user_address: str, amount: int) -> None:
        if amount <= 0:
            raise ValueError("amount must be > 0")
        addr = user_address.lower()
        current = self._balances.get(addr, 0)
        if current < amount:
            raise ValueError("insufficient balance")
        self._balances[addr] = current - amount

    # ── Developer registry ──────────────────────────────────────────────

    def register_developer(self, skill_id_hash: bytes, developer: str) -> None:
        if not developer:
            raise ValueError("invalid developer address")
        self._developers[skill_id_hash] = developer.lower()

    def get_developer(self, skill_id_hash: bytes) -> str:
        return self._developers.get(skill_id_hash, "")

    # ── Helpers: gateway signature verification ─────────────────────────

    @staticmethod
    def _compute_binding_hash(
        task_id: bytes, party: str, amount: int,
    ) -> bytes:
        """Compute ``keccak256(abi.encodePacked(taskId, party, amount))``."""
        party_bytes = to_canonical_address(party)
        amount_bytes = amount.to_bytes(32, 'big')
        return keccak(task_id + party_bytes + amount_bytes)

    def _verify_gateway_signature(
        self, message_hash: bytes, signature: str,
    ) -> None:
        """Recover signer from *signature* and verify it matches the gateway."""
        if not signature:
            raise PermissionError("missing gateway signature")
        recovered = Account._recover_hash(message_hash, signature=signature)
        if recovered.lower() != self._gateway_address:
            raise PermissionError(
                f"invalid gateway signature: recovered {recovered}, "
                f"expected {self._gateway_address}"
            )

    # ── settleTask ──────────────────────────────────────────────────────

    def settle_task(
        self,
        task_id: bytes,
        user: str,
        worker: str,
        skill_id_hash: bytes,
        amount: int,
        nonce: int,
        deadline: int,
        gateway_address: str,
        gateway_signature: str = "",
    ) -> None:
        # Deadline guard
        if time.time() > deadline:
            raise ValueError("deadline passed")

        if amount <= 0:
            raise ValueError("amount must be > 0")

        # Compound nonce
        compound_key = keccak(nonce.to_bytes(32, 'big') + task_id)
        if compound_key in self._used_compound_nonces:
            raise ValueError("nonce already used")

        # Task lifecycle
        if self._task_status.get(task_id, TASK_STATUS_NONE) != TASK_STATUS_NONE:
            raise ValueError("task already settled or refunded")

        user_addr = user.lower()
        user_bal = self._balances.get(user_addr, 0)
        if user_bal < amount:
            raise ValueError("insufficient user balance")

        # Gateway signature
        msg_hash = self._compute_binding_hash(task_id, worker, amount)
        self._verify_gateway_signature(msg_hash, gateway_signature)

        # Look up developer
        developer = self._developers.get(skill_id_hash, "").lower()
        has_developer = bool(developer) and developer != "0x"

        # Calculate splits
        developer_share = (amount * DEVELOPER_BPS) // BPS_DENOM if has_developer else 0
        worker_share = (amount * WORKER_BPS) // BPS_DENOM
        treasury_share = amount - developer_share - worker_share

        # Record compound nonce
        self._used_compound_nonces.add(compound_key)

        # Mark task settled
        self._task_status[task_id] = TASK_STATUS_SETTLED

        # Deduct from user
        self._balances[user_addr] = user_bal - amount

        # Store snapshot
        settlement = TaskSettlement(
            worker=worker.lower(),
            developer=developer,
            total_amount=amount,
            worker_share=worker_share,
            developer_share=developer_share,
            treasury_share=treasury_share,
            settled_at=time.time(),
        )
        self._settlements[task_id] = settlement

        # Credit pending payouts
        self._pending_payouts[worker.lower()] = (
            self._pending_payouts.get(worker.lower(), 0) + worker_share
        )
        if has_developer:
            self._pending_payouts[developer] = (
                self._pending_payouts.get(developer, 0) + developer_share
            )
        else:
            self._accumulated_treasury_fees += developer_share
        self._accumulated_treasury_fees += treasury_share

    # ── refundTask ──────────────────────────────────────────────────────

    def refund_task(
        self, task_id: bytes, user: str, amount: int, reason: str = "",
    ) -> None:
        status = self._task_status.get(task_id, TASK_STATUS_NONE)
        if status != TASK_STATUS_SETTLED:
            raise ValueError("task not settled")
        if amount <= 0:
            raise ValueError("amount must be > 0")

        settlement = self._settlements.get(task_id)
        if settlement is None:
            raise ValueError("no settlement record")

        # Unwind payouts
        remaining_worker = self._pending_payouts.get(settlement.worker, 0)
        if remaining_worker >= settlement.worker_share:
            self._pending_payouts[settlement.worker] = remaining_worker - settlement.worker_share
        else:
            self._pending_payouts[settlement.worker] = 0

        if settlement.developer:
            remaining_dev = self._pending_payouts.get(settlement.developer, 0)
            if remaining_dev >= settlement.developer_share:
                self._pending_payouts[settlement.developer] = remaining_dev - settlement.developer_share
            else:
                self._pending_payouts[settlement.developer] = 0

        # Reduce treasury
        if self._accumulated_treasury_fees >= settlement.treasury_share:
            self._accumulated_treasury_fees -= settlement.treasury_share
        else:
            self._accumulated_treasury_fees = 0

        self._task_status[task_id] = TASK_STATUS_REFUNDED
        self._balances[user.lower()] = self._balances.get(user.lower(), 0) + amount

    # ── Pending payouts ─────────────────────────────────────────────────

    def get_pending_payout(self, address: str) -> int:
        return self._pending_payouts.get(address.lower(), 0)

    # ── Claim: Worker (25 %) ────────────────────────────────────────────

    def claim_reward(
        self, task_id: bytes, claimant: str, gateway_signature: str = "",
    ) -> int:
        status = self._task_status.get(task_id, TASK_STATUS_NONE)
        if status != TASK_STATUS_SETTLED:
            raise ValueError("task not settled or already claimed")

        settlement = self._settlements.get(task_id)
        if settlement is None:
            raise ValueError("no settlement record")
        if settlement.worker != claimant.lower():
            raise PermissionError("not the assigned worker")

        worker_amount = settlement.worker_share
        if worker_amount <= 0:
            raise ValueError("worker share is zero")

        pending = self._pending_payouts.get(claimant.lower(), 0)
        if pending < worker_amount:
            raise ValueError("insufficient pending payout")

        # Verify PoT
        pot_hash = self._compute_binding_hash(task_id, claimant, worker_amount)
        self._verify_gateway_signature(pot_hash, gateway_signature)

        self._task_status[task_id] = TASK_STATUS_CLAIMED
        self._pending_payouts[claimant.lower()] = pending - worker_amount
        return worker_amount

    # ── Claim: Developer (70 %) ─────────────────────────────────────────

    def claim_developer_reward(
        self, task_id: bytes, developer: str, gateway_signature: str = "",
    ) -> int:
        status = self._task_status.get(task_id, TASK_STATUS_NONE)
        if status != TASK_STATUS_SETTLED:
            raise ValueError("task not settled or already claimed")

        settlement = self._settlements.get(task_id)
        if settlement is None:
            raise ValueError("no settlement record")
        if settlement.developer != developer.lower():
            raise PermissionError("not the assigned developer")

        dev_amount = settlement.developer_share
        if dev_amount <= 0:
            raise ValueError("developer share is zero")

        pending = self._pending_payouts.get(developer.lower(), 0)
        if pending < dev_amount:
            raise ValueError("insufficient pending payout")

        # Verify PoT
        pot_hash = self._compute_binding_hash(task_id, developer, dev_amount)
        self._verify_gateway_signature(pot_hash, gateway_signature)

        self._task_status[task_id] = TASK_STATUS_CLAIMED
        self._pending_payouts[developer.lower()] = pending - dev_amount
        return dev_amount

    # ── Treasury ────────────────────────────────────────────────────────

    @property
    def accumulated_treasury_fees(self) -> int:
        return self._accumulated_treasury_fees

    def claim_treasury_fees(self, caller: str) -> int:
        if caller.lower() != self._treasury:
            raise PermissionError("only treasury")
        amount = self._accumulated_treasury_fees
        if amount <= 0:
            raise ValueError("no accumulated fees")
        self._accumulated_treasury_fees = 0
        return amount

    # ── View helpers ────────────────────────────────────────────────────

    def get_task_status(self, task_id: bytes) -> int:
        return self._task_status.get(task_id, TASK_STATUS_NONE)

    def get_task_settlement(self, task_id: bytes) -> Optional[TaskSettlement]:
        return self._settlements.get(task_id)

    def is_compound_nonce_used(self, nonce: int, task_id: bytes) -> bool:
        return keccak(nonce.to_bytes(32, 'big') + task_id) in self._used_compound_nonces


# ── Web3 Implementation ────────────────────────────────────────────────────


class Web3SettlementContract(SettlementContractClient):
    """Production implementation that calls AIMSAgentGateway on Base via web3.py.

    Requires:
      * ``AIMS_RPC_URL`` — Base RPC endpoint
      * ``AIMS_CONTRACT_ADDRESS`` — deployed contract address
      * ``AIMS_GATEWAY_PRIVATE_KEY`` — gateway EOA private key for signing txs
    """

    def __init__(
        self,
        rpc_url: str,
        contract_address: str,
        gateway_private_key: str,
        treasury: str,
    ) -> None:
        self._rpc_url = rpc_url
        self._contract_address = contract_address
        self._gateway_private_key = gateway_private_key
        self._treasury = treasury
        self._w3 = None
        self._contract = None

    def _connect(self):
        if self._w3 is not None:
            return
        from web3 import Web3
        self._w3 = Web3(Web3.HTTPProvider(self._rpc_url))
        from src.chain.abi import AIMS_AGENT_GATEWAY_ABI
        self._contract = self._w3.eth.contract(
            address=Web3.to_checksum_address(self._contract_address),
            abi=AIMS_AGENT_GATEWAY_ABI,
        )

    # ── Read methods (view functions, no gas) ───────────────────────────

    def get_user_balance(self, address: str) -> int:
        self._connect()
        return self._contract.functions.balances(
            self._w3.to_checksum_address(address)
        ).call()

    def get_developer(self, skill_id_hash: bytes) -> str:
        self._connect()
        return self._contract.functions.getDeveloper(skill_id_hash).call()

    def get_pending_payout(self, address: str) -> int:
        self._connect()
        return self._contract.functions.getPendingPayout(
            self._w3.to_checksum_address(address)
        ).call()

    def get_task_status(self, task_id: bytes) -> int:
        self._connect()
        return self._contract.functions.taskStatus(task_id).call()

    def get_task_settlement(self, task_id: bytes) -> Optional[TaskSettlement]:
        self._connect()
        try:
            result = self._contract.functions.getTaskSettlement(task_id).call()
            # result is a tuple: (worker, dev, total, wShare, dShare, tShare, settledAt, status)
            return TaskSettlement(
                worker=result[0],
                developer=result[1],
                total_amount=result[2],
                worker_share=result[3],
                developer_share=result[4],
                treasury_share=result[5],
                settled_at=result[6],
            )
        except Exception:
            return None

    def is_compound_nonce_used(self, nonce: int, task_id: bytes) -> bool:
        self._connect()
        return self._contract.functions.isCompoundNonceUsed(nonce, task_id).call()

    # ── Write methods ──────────────────────────────────────────────────

    def _send_tx(self, fn_call, value: int = 0) -> dict:
        """Build, sign, send, and wait for a transaction. Returns receipt."""
        self._connect()
        acct = self._w3.eth.account.from_key(self._gateway_private_key)
        gas_estimate = fn_call.estimate_transaction({"from": acct.address})
        txn = fn_call.build_transaction({
            "from": acct.address,
            "nonce": self._w3.eth.get_transaction_count(acct.address),
            "gas": int(gas_estimate * 1.2),  # 20 % buffer
            "maxPriorityFeePerGas": self._w3.eth.max_priority_fee,
        })
        signed = acct.sign_transaction(txn)
        tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self._w3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt.status != 1:
            raise RuntimeError(f"tx reverted: {receipt.transactionHash.hex()}")
        logger.info("tx: %s (status=%s)", receipt.transactionHash.hex(), receipt.status)
        return receipt

    def deposit(self, user_address: str, amount: int) -> None:
        """Deposit USDC.  In production the user calls the contract directly."""
        self._connect()
        fn = self._contract.functions.deposit(amount)
        self._send_tx(fn)

    def register_developer(self, skill_id_hash: bytes, developer: str) -> None:
        self._connect()
        fn = self._contract.functions.registerDeveloper(
            skill_id_hash,
            self._w3.to_checksum_address(developer),
        )
        self._send_tx(fn)

    def settle_task(
        self,
        task_id: bytes,
        user: str,
        worker: str,
        skill_id_hash: bytes,
        amount: int,
        nonce: int,
        deadline: int,
        gateway_address: str,
        gateway_signature: str = "",
    ) -> None:
        self._connect()
        sig_bytes = bytes.fromhex(gateway_signature.removeprefix("0x"))
        fn = self._contract.functions.settleTask(
            task_id,
            self._w3.to_checksum_address(user),
            self._w3.to_checksum_address(worker),
            skill_id_hash,
            amount,
            nonce,
            deadline,
            sig_bytes,
        )
        self._send_tx(fn)

    def refund_task(
        self, task_id: bytes, user: str, amount: int, reason: str = "",
    ) -> None:
        self._connect()
        fn = self._contract.functions.refundTask(
            task_id,
            self._w3.to_checksum_address(user),
            amount,
            reason,
        )
        self._send_tx(fn)

    def claim_reward(
        self, task_id: bytes, claimant: str, gateway_signature: str = "",
    ) -> int:
        self._connect()
        sig_bytes = bytes.fromhex(gateway_signature.removeprefix("0x"))
        fn = self._contract.functions.claimReward(task_id, sig_bytes)
        self._send_tx(fn)
        # Return the worker share from the settlement
        settlement = self.get_task_settlement(task_id)
        return settlement.worker_share if settlement else 0

    def claim_developer_reward(
        self, task_id: bytes, developer: str, gateway_signature: str = "",
    ) -> int:
        self._connect()
        sig_bytes = bytes.fromhex(gateway_signature.removeprefix("0x"))
        fn = self._contract.functions.claimDeveloperReward(task_id, sig_bytes)
        self._send_tx(fn)
        settlement = self.get_task_settlement(task_id)
        return settlement.developer_share if settlement else 0
