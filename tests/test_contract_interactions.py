"""Tests for InMemorySettlementContract — full Solidity-mirror lifecycle.

Covers deposit, withdraw, settleTask, reward split, claimReward,
claimOwnerFees, nonce replay protection, and double-claim prevention.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from eth_utils import keccak
import pytest

from src.chain.contract_client import (
    InMemorySettlementContract,
    BPS_DENOM,
    WORKER_BPS,
    OWNER_BPS,
)


# ── Fixtures ────────────────────────────────────────────────────────────────

GATEWAY = "0xGateway000000000000000000000000000000000001"
OWNER = "0xOwner000000000000000000000000000000000001"
USER = "0xUser00000000000000000000000000000000000001"
WORKER = "0xWorker000000000000000000000000000000000001"


@pytest.fixture
def contract():
    return InMemorySettlementContract(
        gateway_address=GATEWAY,
        platform_owner=OWNER,
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
    def test_settle_deducts_from_user(self, contract):
        contract.deposit(USER, 100_000)
        task_id = keccak(text="task-001")
        contract.settle_task(task_id, USER, WORKER, 50_000, 0, GATEWAY)
        assert contract.get_user_balance(USER) == 50_000

    def test_settle_credits_worker_payout(self, contract):
        contract.deposit(USER, 100_000)
        task_id = keccak(text="task-001")
        contract.settle_task(task_id, USER, WORKER, 50_000, 0, GATEWAY)
        expected_worker = (50_000 * WORKER_BPS) // BPS_DENOM  # 40_000
        assert contract.get_pending_payout(WORKER) == expected_worker

    def test_settle_credits_owner_payout(self, contract):
        contract.deposit(USER, 100_000)
        task_id = keccak(text="task-001")
        contract.settle_task(task_id, USER, WORKER, 50_000, 0, GATEWAY)
        expected_owner = 50_000 - ((50_000 * WORKER_BPS) // BPS_DENOM)  # 10_000
        assert contract.get_pending_payout(OWNER) == expected_owner

    def test_settle_split_is_80_20(self, contract):
        contract.deposit(USER, 100_000)
        task_id = keccak(text="task-001")
        contract.settle_task(task_id, USER, WORKER, 50_000, 0, GATEWAY)
        worker_amt = (50_000 * WORKER_BPS) // BPS_DENOM
        owner_amt = 50_000 - worker_amt
        assert worker_amt + owner_amt == 50_000
        assert worker_amt == 40_000
        assert owner_amt == 10_000

    def test_settle_rejects_zero_amount(self, contract):
        task_id = keccak(text="task-001")
        with pytest.raises(ValueError, match="amount must be > 0"):
            contract.settle_task(task_id, USER, WORKER, 0, 0, GATEWAY)

    def test_settle_rejects_used_nonce(self, contract):
        contract.deposit(USER, 100_000)
        task_id = keccak(text="task-001")
        contract.settle_task(task_id, USER, WORKER, 50_000, 0, GATEWAY)
        task_id2 = keccak(text="task-002")
        with pytest.raises(ValueError, match="nonce already used"):
            contract.settle_task(task_id2, USER, WORKER, 10_000, 0, GATEWAY)

    def test_settle_rejects_duplicate_task(self, contract):
        contract.deposit(USER, 100_000)
        task_id = keccak(text="task-001")
        contract.settle_task(task_id, USER, WORKER, 50_000, 0, GATEWAY)
        with pytest.raises(ValueError, match="task already settled"):
            contract.settle_task(task_id, USER, WORKER, 10_000, 1, GATEWAY)

    def test_settle_rejects_non_gateway(self, contract):
        contract.deposit(USER, 100_000)
        task_id = keccak(text="task-001")
        with pytest.raises(PermissionError, match="onlyGateway"):
            contract.settle_task(task_id, USER, WORKER, 50_000, 0, USER)

    def test_settle_rejects_insufficient_balance(self, contract):
        task_id = keccak(text="task-001")
        with pytest.raises(ValueError, match="insufficient user balance"):
            contract.settle_task(task_id, USER, WORKER, 50_000, 0, GATEWAY)

    def test_settle_records_nonce(self, contract):
        contract.deposit(USER, 100_000)
        task_id = keccak(text="task-001")
        contract.settle_task(task_id, USER, WORKER, 50_000, 42, GATEWAY)
        assert contract.is_nonce_used(42)
        assert not contract.is_nonce_used(43)

    def test_settle_records_task(self, contract):
        contract.deposit(USER, 100_000)
        task_id = keccak(text="task-001")
        contract.settle_task(task_id, USER, WORKER, 50_000, 0, GATEWAY)
        assert contract.is_task_settled(task_id)
        assert not contract.is_task_settled(keccak(text="other"))


# ── ClaimReward ─────────────────────────────────────────────────────────────

class TestClaimReward:
    def test_claim_reward_transfers_to_worker(self, contract):
        contract.deposit(USER, 100_000)
        task_id = keccak(text="task-001")
        contract.settle_task(task_id, USER, WORKER, 50_000, 0, GATEWAY)
        amount = contract.claim_reward(task_id, WORKER)
        expected = (50_000 * WORKER_BPS) // BPS_DENOM
        assert amount == expected
        assert contract.get_pending_payout(WORKER) == 0

    def test_claim_reward_double_claim_rejected(self, contract):
        contract.deposit(USER, 100_000)
        task_id = keccak(text="task-001")
        contract.settle_task(task_id, USER, WORKER, 50_000, 0, GATEWAY)
        contract.claim_reward(task_id, WORKER)
        with pytest.raises(ValueError, match="reward already claimed"):
            contract.claim_reward(task_id, WORKER)

    def test_claim_reward_no_payout_rejected(self, contract):
        task_id = keccak(text="no-settle")
        with pytest.raises(ValueError, match="no pending payout"):
            contract.claim_reward(task_id, WORKER)


# ── ClaimOwnerFees ──────────────────────────────────────────────────────────

class TestClaimOwnerFees:
    def test_owner_claims_accumulated_fees(self, contract):
        contract.deposit(USER, 100_000)
        contract.settle_task(keccak(text="task-001"), USER, WORKER, 50_000, 0, GATEWAY)
        contract.settle_task(keccak(text="task-002"), USER, WORKER, 50_000, 1, GATEWAY)
        amount = contract.claim_owner_fees(OWNER)
        expected_per = 50_000 - ((50_000 * WORKER_BPS) // BPS_DENOM)
        assert amount == expected_per * 2
        assert contract.get_pending_payout(OWNER) == 0

    def test_non_owner_cannot_claim_fees(self, contract):
        contract.deposit(USER, 100_000)
        contract.settle_task(keccak(text="task-001"), USER, WORKER, 50_000, 0, GATEWAY)
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
            contract.set_gateway("0xNewGateway", USER)
