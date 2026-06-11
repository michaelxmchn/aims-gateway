"""Tests for InMemorySettlementContract — full Solidity-mirror lifecycle.

Covers deposit, withdraw, settleTask, 70/25/5 split, claimReward,
claimDeveloperReward, claimTreasuryFees, compound nonce, and lifecycle.

All gateway-signed operations use real ECDSA signatures.
"""

from __future__ import annotations

import time

from eth_account import Account
from eth_utils import keccak, to_canonical_address
import pytest

from src.chain.contract_client import (
    InMemorySettlementContract,
    TASK_STATUS_NONE,
    TASK_STATUS_SETTLED,
    TASK_STATUS_REFUNDED,
    TASK_STATUS_CLAIMED,
)
from src.chain.abi import (
    BPS_DENOM,
    WORKER_BPS,
    DEVELOPER_BPS,
    TREASURY_BPS,
)

# ── Well-known test keys ──────────────────────────────────────────────────────

_GATEWAY_ACCT = Account.create()
GATEWAY_KEY = _GATEWAY_ACCT.key.hex()
GATEWAY = _GATEWAY_ACCT.address

TREASURY = "0xTreasury00000000000000000000000000000000001"
USER = "0x1111111111111111111111111111111111111111"
WORKER = "0x2222222222222222222222222222222222222222"
DEVELOPER = "0x3333333333333333333333333333333333333333"

COST = 50_000
SKILL = keccak(text="test-skill")


def _settle_sig(
    task_id: bytes, worker: str, amount: int,
) -> str:
    """Sign a settleTask message with the gateway's private key."""
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


@pytest.fixture
def contract():
    return InMemorySettlementContract(
        gateway_address=GATEWAY,
        treasury=TREASURY,
        gateway_signing_key=GATEWAY_KEY,
    )


def _deadline() -> int:
    return int(time.time()) + 300


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
    def test_settle_deducts_from_user(self, contract):
        contract.deposit(USER, 100_000)
        tid = keccak(text="task-001")
        sig = _settle_sig(tid, WORKER, COST)
        contract.settle_task(tid, USER, WORKER, SKILL, COST, 0, _deadline(), GATEWAY, sig)
        assert contract.get_user_balance(USER) == 50_000

    def test_settle_credits_worker_payout(self, contract):
        contract.deposit(USER, 100_000)
        tid = keccak(text="task-001")
        sig = _settle_sig(tid, WORKER, COST)
        contract.settle_task(tid, USER, WORKER, SKILL, COST, 0, _deadline(), GATEWAY, sig)
        expected = (COST * WORKER_BPS) // BPS_DENOM  # 12_500
        assert contract.get_pending_payout(WORKER) == expected

    def test_settle_split_is_70_25_5(self, contract):
        contract.deposit(USER, 100_000)
        contract.register_developer(SKILL, DEVELOPER)
        tid = keccak(text="task-001")
        sig = _settle_sig(tid, WORKER, COST)
        contract.settle_task(tid, USER, WORKER, SKILL, COST, 0, _deadline(), GATEWAY, sig)
        worker_amt = (COST * WORKER_BPS) // BPS_DENOM
        dev_amt = (COST * DEVELOPER_BPS) // BPS_DENOM
        treasury_amt = COST - worker_amt - dev_amt
        assert worker_amt + dev_amt + treasury_amt == COST
        assert contract.get_pending_payout(WORKER) == worker_amt
        assert contract.get_pending_payout(DEVELOPER) == dev_amt
        assert contract.accumulated_treasury_fees == treasury_amt

    def test_settle_rejects_zero_amount(self, contract):
        tid = keccak(text="task-001")
        with pytest.raises(ValueError, match="amount must be > 0"):
            contract.settle_task(tid, USER, WORKER, SKILL, 0, 0, _deadline(), GATEWAY, "")

    def test_settle_rejects_used_compound_nonce(self, contract):
        """Same compound key (same nonce, same taskId) rejected."""
        contract.deposit(USER, 100_000)
        tid1 = keccak(text="task-001")
        sig1 = _settle_sig(tid1, WORKER, COST)
        contract.settle_task(tid1, USER, WORKER, SKILL, COST, 0, _deadline(), GATEWAY, sig1)
        # Same nonce (0) with same taskId → must be rejected
        with pytest.raises(ValueError, match="nonce already used"):
            contract.settle_task(tid1, USER, WORKER, SKILL, COST, 0, _deadline(), GATEWAY, sig1)

    def test_settle_same_nonce_different_task_allowed(self, contract):
        """Same numeric nonce with different taskId is allowed (compound nonce)."""
        contract.deposit(USER, 200_000)
        tid1 = keccak(text="task-a")
        sig1 = _settle_sig(tid1, WORKER, COST)
        contract.settle_task(tid1, USER, WORKER, SKILL, COST, 0, _deadline(), GATEWAY, sig1)

        tid2 = keccak(text="task-b")
        sig2 = _settle_sig(tid2, WORKER, COST)
        contract.settle_task(tid2, USER, WORKER, SKILL, COST, 0, _deadline(), GATEWAY, sig2)

        assert contract.get_task_status(tid1) == TASK_STATUS_SETTLED
        assert contract.get_task_status(tid2) == TASK_STATUS_SETTLED

    def test_settle_rejects_duplicate_task(self, contract):
        contract.deposit(USER, 100_000)
        tid = keccak(text="task-001")
        sig = _settle_sig(tid, WORKER, COST)
        contract.settle_task(tid, USER, WORKER, SKILL, COST, 0, _deadline(), GATEWAY, sig)
        with pytest.raises(ValueError, match="task already settled"):
            contract.settle_task(tid, USER, WORKER, SKILL, COST, 1, _deadline(), GATEWAY, sig)

    def test_settle_rejects_invalid_signature(self, contract):
        contract.deposit(USER, 100_000)
        tid = keccak(text="task-001")
        bad_key = Account.create().key.hex()
        worker_bytes = to_canonical_address(WORKER)
        amount_bytes = COST.to_bytes(32, 'big')
        msg_hash = keccak(tid + worker_bytes + amount_bytes)
        bad_sig = Account.unsafe_sign_hash(msg_hash, bad_key).signature.hex()
        with pytest.raises(PermissionError, match="invalid gateway signature"):
            contract.settle_task(tid, USER, WORKER, SKILL, COST, 0, _deadline(), GATEWAY, bad_sig)

    def test_settle_rejects_insufficient_balance(self, contract):
        tid = keccak(text="task-001")
        sig = _settle_sig(tid, WORKER, COST)
        with pytest.raises(ValueError, match="insufficient user balance"):
            contract.settle_task(tid, USER, WORKER, SKILL, COST, 0, _deadline(), GATEWAY, sig)

    def test_settle_rejects_expired_deadline(self, contract):
        contract.deposit(USER, 100_000)
        tid = keccak(text="task-001")
        sig = _settle_sig(tid, WORKER, COST)
        with pytest.raises(ValueError, match="deadline"):
            contract.settle_task(tid, USER, WORKER, SKILL, COST, 0, 0, GATEWAY, sig)

    def test_settle_tracks_status(self, contract):
        contract.deposit(USER, 100_000)
        tid = keccak(text="task-status")
        assert contract.get_task_status(tid) == TASK_STATUS_NONE
        sig = _settle_sig(tid, WORKER, COST)
        contract.settle_task(tid, USER, WORKER, SKILL, COST, 0, _deadline(), GATEWAY, sig)
        assert contract.get_task_status(tid) == TASK_STATUS_SETTLED


# ── ClaimReward ─────────────────────────────────────────────────────────────

class TestClaimReward:
    def test_worker_claims_25_percent(self, contract):
        contract.deposit(USER, 100_000)
        contract.register_developer(SKILL, DEVELOPER)
        tid = keccak(text="task-001")
        sig = _settle_sig(tid, WORKER, COST)
        contract.settle_task(tid, USER, WORKER, SKILL, COST, 0, _deadline(), GATEWAY, sig)

        expected = (COST * WORKER_BPS) // BPS_DENOM
        claim_sig = _claim_sig(tid, WORKER, expected)
        amount = contract.claim_reward(tid, WORKER, claim_sig)
        assert amount == expected
        assert contract.get_pending_payout(WORKER) == 0

    def test_double_claim_rejected(self, contract):
        contract.deposit(USER, 100_000)
        contract.register_developer(SKILL, DEVELOPER)
        tid = keccak(text="task-002")
        sig = _settle_sig(tid, WORKER, COST)
        contract.settle_task(tid, USER, WORKER, SKILL, COST, 0, _deadline(), GATEWAY, sig)
        expected = (COST * WORKER_BPS) // BPS_DENOM
        claim_sig = _claim_sig(tid, WORKER, expected)
        contract.claim_reward(tid, WORKER, claim_sig)
        with pytest.raises(ValueError, match="worker already claimed"):
            contract.claim_reward(tid, WORKER, claim_sig)

    def test_developer_claims_70_percent(self, contract):
        contract.deposit(USER, 100_000)
        contract.register_developer(SKILL, DEVELOPER)
        tid = keccak(text="task-003")
        sig = _settle_sig(tid, WORKER, COST)
        contract.settle_task(tid, USER, WORKER, SKILL, COST, 0, _deadline(), GATEWAY, sig)

        expected = (COST * DEVELOPER_BPS) // BPS_DENOM
        claim_sig = _claim_sig(tid, DEVELOPER, expected)
        amount = contract.claim_developer_reward(tid, DEVELOPER, claim_sig)
        assert amount == expected
        assert contract.get_pending_payout(DEVELOPER) == 0

    def test_wrong_worker_rejected(self, contract):
        contract.deposit(USER, 100_000)
        tid = keccak(text="task-004")
        sig = _settle_sig(tid, WORKER, COST)
        contract.settle_task(tid, USER, WORKER, SKILL, COST, 0, _deadline(), GATEWAY, sig)
        with pytest.raises(PermissionError, match="not the assigned worker"):
            contract.claim_reward(tid, DEVELOPER, "")

    def test_no_settlement_rejected(self, contract):
        tid = keccak(text="no-settle")
        with pytest.raises(ValueError, match="no settlement record"):
            contract.claim_reward(tid, WORKER, "")


# ── Treasury ────────────────────────────────────────────────────────────────

class TestTreasury:
    def test_treasury_claims_accumulated_fees(self, contract):
        contract.deposit(USER, 200_000)
        contract.register_developer(SKILL, DEVELOPER)
        for i in range(2):
            tid = keccak(text=f"task-{i}")
            sig = _settle_sig(tid, WORKER, COST)
            contract.settle_task(tid, USER, WORKER, SKILL, COST, i, _deadline(), GATEWAY, sig)

        treasury_share = COST - ((COST * (WORKER_BPS + DEVELOPER_BPS)) // BPS_DENOM)
        expected = treasury_share * 2
        amount = contract.claim_treasury_fees(TREASURY)
        assert amount == expected
        assert contract.accumulated_treasury_fees == 0

    def test_non_treasury_cannot_claim_fees(self, contract):
        contract.deposit(USER, 100_000)
        tid = keccak(text="task-fees")
        sig = _settle_sig(tid, WORKER, COST)
        contract.settle_task(tid, USER, WORKER, SKILL, COST, 0, _deadline(), GATEWAY, sig)
        with pytest.raises(PermissionError, match="only treasury"):
            contract.claim_treasury_fees(WORKER)

    def test_treasury_no_fees_raises_error(self, contract):
        with pytest.raises(ValueError, match="no accumulated fees"):
            contract.claim_treasury_fees(TREASURY)


# ── Gateway management ──────────────────────────────────────────────────────

class TestGatewayManagement:
    def test_set_gateway_by_gateway(self, contract):
        new_gw = "0xNewGateway0000000000000000000000000000000"
        contract.set_gateway(new_gw, GATEWAY)
        assert contract.gateway_address == new_gw.lower()

    def test_set_gateway_rejects_non_gateway(self, contract):
        with pytest.raises(PermissionError, match="onlyGateway"):
            contract.set_gateway("0xNewGateway0000000000000000000000000000000", USER)
