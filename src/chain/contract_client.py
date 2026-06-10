"""Settlement contract client abstraction.

Provides an ABC ``SettlementContractClient`` with two implementations:

* ``InMemorySettlementContract`` — pure Python, mirrors the Solidity
  ``AIMSSettlement`` logic exactly.  Used for tests and local dev.
* ``Web3SettlementContract`` — web3.py production wrapper that calls
  the deployed contract on Base via JSON-RPC.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)

# ── Constants (mirrors Solidity) ───────────────────────────────────────────

BPS_DENOM = 10_000
WORKER_BPS = 8_000
OWNER_BPS = 2_000


class SettlementContractClient(ABC):
    """Abstract interface to the on-chain AIMSSettlement contract."""

    @abstractmethod
    def get_user_balance(self, address: str) -> int:
        """Return the deposited balance (USDC, 6 decimals) for *address*."""
        ...

    @abstractmethod
    def deposit(self, user_address: str, amount: int) -> None:
        """Record a deposit of *amount* USDC for *user_address*."""
        ...

    @abstractmethod
    def settle_task(
        self,
        task_id: bytes,
        user: str,
        worker: str,
        amount: int,
        nonce: int,
        gateway_address: str,
    ) -> None:
        """Execute the oracle settlement (onlyGateway-equivalent path).

        Args:
            task_id:  Unique task identifier (bytes32).
            user:     The user whose deposit is being settled.
            worker:   The worker who executed the task.
            amount:   Total settlement amount (USDC, 6 decimals).
            nonce:    Replay-protection nonce.
            gateway_address:  The caller's address (checked against stored gateway).
        """
        ...

    @abstractmethod
    def get_pending_payout(self, address: str) -> int:
        """Return the pending payout for *address*."""
        ...

    @abstractmethod
    def is_nonce_used(self, nonce: int) -> bool:
        """Check whether *nonce* has already been consumed."""
        ...

    @abstractmethod
    def is_task_settled(self, task_id: bytes) -> bool:
        """Check whether *task_id* has already been settled."""
        ...


# ── In-Memory Implementation ───────────────────────────────────────────────


class InMemorySettlementContract(SettlementContractClient):
    """Pure-Python in-memory mirror of the AIMSSettlement Solidity contract.

    Balances, nonces, and settled/claimed task tracking live in dicts so
    tests can verify the full lifecycle without an EVM.
    """

    def __init__(
        self,
        gateway_address: str,
        platform_owner: str,
    ) -> None:
        self._gateway_address = gateway_address.lower()
        self._platform_owner = platform_owner.lower()
        self._balances: dict[str, int] = {}
        self._pending_payouts: dict[str, int] = {}
        self._used_nonces: set[int] = set()
        self._settled_tasks: set[bytes] = set()
        self._claimed_tasks: set[bytes] = set()

    # ── Gateway address (mirrors setGateway / onlyGateway) ────────────────

    @property
    def gateway_address(self) -> str:
        return self._gateway_address

    def set_gateway(self, new_address: str, caller: str) -> None:
        if caller.lower() != self._gateway_address:
            raise PermissionError("onlyGateway: caller is not the gateway")
        self._gateway_address = new_address.lower()

    # ── User balance ─────────────────────────────────────────────────────

    def get_user_balance(self, address: str) -> int:
        return self._balances.get(address.lower(), 0)

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

    # ── Oracle: settleTask ───────────────────────────────────────────────

    def settle_task(
        self,
        task_id: bytes,
        user: str,
        worker: str,
        amount: int,
        nonce: int,
        gateway_address: str,
    ) -> None:
        if gateway_address.lower() != self._gateway_address:
            raise PermissionError("onlyGateway: caller is not the gateway")
        if amount <= 0:
            raise ValueError("amount must be > 0")
        if nonce in self._used_nonces:
            raise ValueError("nonce already used")
        if task_id in self._settled_tasks:
            raise ValueError("task already settled")

        user_addr = user.lower()
        user_bal = self._balances.get(user_addr, 0)
        if user_bal < amount:
            raise ValueError("insufficient user balance")

        # Record nonce + task
        self._used_nonces.add(nonce)
        self._settled_tasks.add(task_id)

        # Deduct from user
        self._balances[user_addr] = user_bal - amount

        # Split 80/20
        worker_amount = (amount * WORKER_BPS) // BPS_DENOM
        owner_amount = amount - worker_amount

        worker_addr = worker.lower()
        self._pending_payouts[worker_addr] = (
            self._pending_payouts.get(worker_addr, 0) + worker_amount
        )
        self._pending_payouts[self._platform_owner] = (
            self._pending_payouts.get(self._platform_owner, 0) + owner_amount
        )

    # ── Pending payouts ──────────────────────────────────────────────────

    def get_pending_payout(self, address: str) -> int:
        return self._pending_payouts.get(address.lower(), 0)

    def claim_reward(self, task_id: bytes, claimant: str) -> int:
        """Claim the worker's payout (mirrors Solidity claimReward).

        Args:
            task_id:   The task identifier.
            claimant:  The worker address calling claim.

        Returns:
            The amount transferred to the claimant.

        Raises:
            ValueError if already claimed or no pending payout.
        """
        if task_id in self._claimed_tasks:
            raise ValueError("reward already claimed")

        claimant_addr = claimant.lower()
        worker_amount = self._pending_payouts.get(claimant_addr, 0)
        if worker_amount <= 0:
            raise ValueError("no pending payout for caller")

        self._claimed_tasks.add(task_id)
        self._pending_payouts[claimant_addr] = 0
        return worker_amount

    def claim_owner_fees(self, caller: str) -> int:
        """Claim the accumulated platform owner fees."""
        if caller.lower() != self._platform_owner:
            raise PermissionError("only platform owner")
        amount = self._pending_payouts.get(self._platform_owner, 0)
        if amount <= 0:
            raise ValueError("no pending payout")
        self._pending_payouts[self._platform_owner] = 0
        return amount

    # ── View helpers ─────────────────────────────────────────────────────

    def is_nonce_used(self, nonce: int) -> bool:
        return nonce in self._used_nonces

    def is_task_settled(self, task_id: bytes) -> bool:
        return task_id in self._settled_tasks

    def is_task_claimed(self, task_id: bytes) -> bool:
        return task_id in self._claimed_tasks


# ── Web3 Implementation ────────────────────────────────────────────────────


class Web3SettlementContract(SettlementContractClient):
    """Production implementation that calls AIMSSettlement on Base via web3.py.

    Requires the environment to have:
      * ``AIMS_RPC_URL`` — Base RPC endpoint (set by deploy infrastructure)
      * ``AIMS_CONTRACT_ADDRESS`` — deployed contract address
      * ``AIMS_GATEWAY_PRIVATE_KEY`` — gateway EOA private key for signing txs

    Uses ``web3.Web3`` with EIP-1559 gas estimation by default.
    """

    def __init__(
        self,
        rpc_url: str,
        contract_address: str,
        gateway_private_key: str,
        platform_owner: str,
    ) -> None:
        self._rpc_url = rpc_url
        self._contract_address = contract_address
        self._gateway_private_key = gateway_private_key
        self._platform_owner = platform_owner

        # Lazily initialised (call _connect() explicitly or via first method)
        self._w3 = None
        self._contract = None

    def _connect(self):
        """Initialise the web3 connection and contract wrapper."""
        if self._w3 is not None:
            return

        from web3 import Web3

        self._w3 = Web3(Web3.HTTPProvider(self._rpc_url))

        from src.chain.abi import AIMS_SETTLEMENT_ABI

        self._contract = self._w3.eth.contract(
            address=Web3.to_checksum_address(self._contract_address),
            abi=AIMS_SETTLEMENT_ABI,
        )

    # ── Read methods (view functions, no gas) ─────────────────────────────

    def get_user_balance(self, address: str) -> int:
        self._connect()
        return self._contract.functions.balances(
            self._w3.to_checksum_address(address)  # type: ignore[union-attr]
        ).call()

    def get_pending_payout(self, address: str) -> int:
        self._connect()
        return self._contract.functions.pendingPayouts(
            self._w3.to_checksum_address(address)  # type: ignore[union-attr]
        ).call()

    def is_nonce_used(self, nonce: int) -> bool:
        self._connect()
        return self._contract.functions.usedNonces(nonce).call()

    def is_task_settled(self, task_id: bytes) -> bool:
        self._connect()
        return self._contract.functions.settledTasks(task_id).call()

    # ── Write methods (gas-bearing transactions) ──────────────────────────

    def deposit(self, user_address: str, amount: int) -> None:
        """Deposit USDC.  In production the user calls the contract directly;
        this is a convenience proxy for the gateway.
        """
        self._connect()
        acct = self._w3.eth.account.from_key(self._gateway_private_key)  # type: ignore[union-attr]

        # In a real deployment the gateway would not deposit on behalf of
        # users — this shows the pattern.
        txn = self._contract.functions.deposit(amount).build_transaction({  # type: ignore[union-attr]
            "from": acct.address,
            "nonce": self._w3.eth.get_transaction_count(acct.address),  # type: ignore[union-attr]
        })
        signed = acct.sign_transaction(txn)
        tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)  # type: ignore[union-attr]
        receipt = self._w3.eth.wait_for_transaction_receipt(tx_hash)  # type: ignore[union-attr]
        logger.info("Deposit tx: %s (status=%s)", receipt.transactionHash.hex(), receipt.status)

    def settle_task(
        self,
        task_id: bytes,
        user: str,
        worker: str,
        amount: int,
        nonce: int,
        gateway_address: str,
    ) -> None:
        """Call settleTask on the contract (onlyGateway-guarded)."""
        self._connect()
        acct = self._w3.eth.account.from_key(self._gateway_private_key)  # type: ignore[union-attr]

        txn = self._contract.functions.settleTask(  # type: ignore[union-attr]
            task_id,
            self._w3.to_checksum_address(user),  # type: ignore[union-attr]
            self._w3.to_checksum_address(worker),  # type: ignore[union-attr]
            amount,
            nonce,
        ).build_transaction({
            "from": acct.address,
            "nonce": self._w3.eth.get_transaction_count(acct.address),  # type: ignore[union-attr]
        })
        signed = acct.sign_transaction(txn)
        tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)  # type: ignore[union-attr]
        receipt = self._w3.eth.wait_for_transaction_receipt(tx_hash)  # type: ignore[union-attr]
        logger.info("settleTask tx: %s (status=%s)", receipt.transactionHash.hex(), receipt.status)

        if receipt.status != 1:
            raise RuntimeError(f"settleTask reverted: tx={receipt.transactionHash.hex()}")
