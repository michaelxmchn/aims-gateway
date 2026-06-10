"""Tests for InMemorySettlementContract — full Solidity-mirror lifecycle.

Covers deposit, withdraw, settleTask, reward split, claimReward,
claimOwnerFees, nonce replay protection, and double-claim prevention.

All gateway-signed operations (settleTask, claimReward) use real ECDSA
signatures generated with the gateway's private key, mirroring the
on-chain ``ECDSA.recover`` path.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from eth_account import Account
from eth_utils import keccak, to_bytes, to_canonical_address
import pytest

from src.chain.contract_client import (
    InMemorySettlementContract,
    BPS_DENOM,
    WORKER_BPS,
    OWNER_BPS,
)


# ── Gateway key pair (shared across all tests) ──────────────────────────────
# Generate once so all fixture instances use the same gateway identity.

_GATEWAY_ACCT = Account.create()
GATEWAY_KEY = _GATEWAY_ACCT.key.hex()
GATEWAY = _GATEWAY_ACCT.address

OWNER = "0x3333333333333333333333333333333333333333"
USER = "0x1111111111111111111111111111111111111111"
WORKER = "0x2222222222222222222222222222222222222222"


# ── Signing helpers ─────────────────────────────────────────────────────────


def _settle_sig(
    task_id: bytes, user: str, worker: str, amount: int, nonce: int,
) -> str:
    """Sign a settleTask message with the gateway's private key.

    Produces the same signature that ``BillingEngine._sign_settlement``
    creates, matching the Solidity ``ECDSA.recover`` path.

    The gateway signs ``keccak256(abi.encodePacked(taskId, worker, amount))``
    — user and nonce are function parameters only, not part of the signed hash.
    """
    worker_bytes = to_canonical_address(worker)
    amount_bytes = amount.to_bytes(32, 'big')
    msg_hash = keccak(task_id + worker_bytes + amount_bytes)
    signed = Account.unsafe_sign_hash(msg_hash, GATEWAY_KEY)
    return signed.signature.hex()


def _claim_sig(task_id: bytes, claimant: str, amount: int) -> str:
    """Sign a claimReward (PoT) message with the gateway's private key."""
    claimant_bytes = to_canonical_address(claimant)
    amount_bytes = amount.to_bytes(32, 'big')
    msg_hash = keccak(task_id + claimant_bytes + amount_bytes)
    signed = Account.unsafe_sign_hash(msg_hash, GATEWAY_KEY)
    return signed.signature.hex()


# ── Contract fixture ─────────────────────────────────────────────────────────


@pytest.fixture
def contract():
    return InMemorySettlementContract(
        gateway_address=GATEWAY,
        platform_owner=OWNER,
        gateway_signing_key=GATEWAY_KEY,
    )


# ── Deposit / Withdraw ──────────────────────────────────────────────────────

class TestDepositWithdraw:
    def test_deposit_increases_balance(self, contract):
        contract.deposit(USER, 100_000)
        assert contract.get_user_balance(USER) == 100_000

    def test_deposit_accumulates(self, contract):
        contract.deposit(USER, 50_000)
        contract.deposit(USER, 30_000)
        assert contract.get_user_balance(USER) == 80_000

    def test_deposit_zero_rejected(self, contract):
        with pytest.raises(ValueError, match="amount must be > 0"):
            contract.deposit(USER, 0)

    def test_withdraw_reduces_balance(self, contract):
        contract.deposit(USER, 100_000)
        contract.withdraw(USER, 30_000)
        assert contract.get_user_balance(USER) == 70_000

    def test_withdraw_insufficient_rejected(self, contract):
        contract.deposit(USER, 10_000)
        with pytest.raises(ValueError, match="insufficient balance"):
            contract.withdraw(USER, 20_000)

    def test_withdraw_zero_rejected(self, contract):
        with pytest.raises(ValueError, match="amount must be > 0"):
            contract.withdraw(USER, 0)

    def test_independent_balances(self, contract):
        contract.deposit(USER, 100_000)
        contract.deposit(WORKER, 50_000)
        assert contract.get_user_balance(USER) == 100_000
        assert contract.get_user_balance(WORKER) == 50_000


# ── SettleTask ──────────────────────────────────────────────────────────────

class TestSettleTask:
    def _settle(self, contract, task_id: bytes, nonce: int = 0, **kw):
        """Convenience helper: deposit, then settle with a gateway signature."""
        contract.deposit(USER, 100_000) if kw.get("pre_deposit", True) else None
        sig = _settle_sig(task_id, USER, WORKER, 50_000, nonce)
        contract.settle_task(
            task_id, USER, WORKER, 50_000, nonce,
            gateway_address=GATEWAY, gateway_signature=sig,
        )

    def test_settle_deducts_from_user(self, contract):
        self._settle(contract, keccak(text="task-001"))
        assert contract.get_user_balance(USER) == 50_000

    def test_settle_credits_worker_payout(self, contract):
        self._settle(contract, keccak(text="task-001"))
        expected_worker = (50_000 * WORKER_BPS) // BPS_DENOM  # 40_000
        assert contract.get_pending_payout(WORKER) == expected_worker

    def test_settle_credits_owner_payout(self, contract):
        self._settle(contract, keccak(text="task-001"))
        expected_owner = 50_000 - ((50_000 * WORKER_BPS) // BPS_DENOM)  # 10_000
        assert contract.get_pending_payout(OWNER) == expected_owner

    def test_settle_split_is_80_20(self, contract):
        self._settle(contract, keccak(text="task-001"))
        worker_amt = (50_000 * WORKER_BPS) // BPS_DENOM
        owner_amt = 50_000 - worker_amt
        assert worker_amt + owner_amt == 50_000
        assert worker_amt == 40_000
        assert owner_amt == 10_000

    def test_settle_rejects_zero_amount(self, contract):
        task_id = keccak(text="task-001")
        with pytest.raises(ValueError, match="amount must be > 0"):
            contract.settle_task(task_id, USER, WORKER, 0, 0, GATEWAY, "")

    def test_settle_rejects_used_nonce(self, contract):
        self._settle(contract, keccak(text="task-001"), nonce=0)
        task_id2 = keccak(text="task-002")
        sig = _settle_sig(task_id2, USER, WORKER, 10_000, 0)
        with pytest.raises(ValueError, match="nonce already used"):
            contract.settle_task(task_id2, USER, WORKER, 10_000, 0, GATEWAY, sig)

    def test_settle_rejects_duplicate_task(self, contract):
        tid = keccak(text="task-001")
        self._settle(contract, tid, nonce=0)
        sig = _settle_sig(tid, USER, WORKER, 10_000, 1)
        with pytest.raises(ValueError, match="task already settled"):
            contract.settle_task(tid, USER, WORKER, 10_000, 1, GATEWAY, sig)

    def test_settle_rejects_non_gateway(self, contract):
        contract.deposit(USER, 100_000)
        task_id = keccak(text="task-001")
        # Sign with USER's key instead of gateway — recovered signer won't match
        user_key = Account.create().key.hex()
        worker_bytes = to_canonical_address(WORKER)
        amount_bytes = (50_000).to_bytes(32, 'big')
        msg_hash = keccak(task_id + worker_bytes + amount_bytes)
        bad_sig = Account.unsafe_sign_hash(msg_hash, user_key).signature.hex()
        with pytest.raises(PermissionError, match="invalid gateway signature"):
            contract.settle_task(task_id, USER, WORKER, 50_000, 0, GATEWAY, bad_sig)

    def test_settle_rejects_insufficient_balance(self, contract):
        task_id = keccak(text="task-001")
        sig = _settle_sig(task_id, USER, WORKER, 50_000, 0)
        with pytest.raises(ValueError, match="insufficient user balance"):
            contract.settle_task(task_id, USER, WORKER, 50_000, 0, GATEWAY, sig)

    def test_settle_records_nonce(self, contract):
        self._settle(contract, keccak(text="task-001"), nonce=42)
        assert contract.is_nonce_used(42)
        assert not contract.is_nonce_used(43)

    def test_settle_records_task(self, contract):
        self._settle(contract, keccak(text="task-001"))
        assert contract.is_task_settled(keccak(text="task-001"))
        assert not contract.is_task_settled(keccak(text="other"))


# ── ClaimReward ─────────────────────────────────────────────────────────────

class TestClaimReward:
    def test_claim_reward_transfers_to_worker(self, contract):
        contract.deposit(USER, 100_000)
        task_id = keccak(text="task-001")
        sig = _settle_sig(task_id, USER, WORKER, 50_000, 0)
        contract.settle_task(task_id, USER, WORKER, 50_000, 0, GATEWAY, sig)
        claim_sig = _claim_sig(task_id, WORKER, 40_000)
        amount = contract.claim_reward(task_id, WORKER, claim_sig)
        expected = (50_000 * WORKER_BPS) // BPS_DENOM
        assert amount == expected
        assert contract.get_pending_payout(WORKER) == 0

    def test_claim_reward_double_claim_rejected(self, contract):
        contract.deposit(USER, 100_000)
        task_id = keccak(text="task-001")
        sig = _settle_sig(task_id, USER, WORKER, 50_000, 0)
        contract.settle_task(task_id, USER, WORKER, 50_000, 0, GATEWAY, sig)
        claim_sig = _claim_sig(task_id, WORKER, 40_000)
        contract.claim_reward(task_id, WORKER, claim_sig)
        with pytest.raises(ValueError, match="reward already claimed"):
            contract.claim_reward(task_id, WORKER, claim_sig)

    def test_claim_reward_no_payout_rejected(self, contract):
        task_id = keccak(text="no-settle")
        with pytest.raises(ValueError, match="no pending payout"):
            contract.claim_reward(task_id, WORKER, "")


# ── ClaimOwnerFees ──────────────────────────────────────────────────────────

class TestClaimOwnerFees:
    def test_owner_claims_accumulated_fees(self, contract):
        contract.deposit(USER, 100_000)
        tid1 = keccak(text="task-001")
        contract.settle_task(tid1, USER, WORKER, 50_000, 0, GATEWAY,
                             _settle_sig(tid1, USER, WORKER, 50_000, 0))
        tid2 = keccak(text="task-002")
        contract.settle_task(tid2, USER, WORKER, 50_000, 1, GATEWAY,
                             _settle_sig(tid2, USER, WORKER, 50_000, 1))
        amount = contract.claim_owner_fees(OWNER)
        expected_per = 50_000 - ((50_000 * WORKER_BPS) // BPS_DENOM)
        assert amount == expected_per * 2
        assert contract.get_pending_payout(OWNER) == 0

    def test_non_owner_cannot_claim_fees(self, contract):
        contract.deposit(USER, 100_000)
        tid = keccak(text="task-001")
        contract.settle_task(tid, USER, WORKER, 50_000, 0, GATEWAY,
                             _settle_sig(tid, USER, WORKER, 50_000, 0))
        with pytest.raises(PermissionError, match="only platform owner"):
            contract.claim_owner_fees(WORKER)


# ── Gateway management ──────────────────────────────────────────────────────

class TestGatewayManagement:
    def test_set_gateway_by_gateway(self, contract):
        new_gw = "0xNewGateway0000000000000000000000000000000"
        contract.set_gateway(new_gw, GATEWAY)
        assert contract.gateway_address == new_gw.lower()

    def test_set_gateway_rejects_non_gateway(self, contract):
        with pytest.raises(PermissionError, match="onlyGateway"):
            contract.set_gateway("0xNewGateway0000000000000000000000000000000", USER)
