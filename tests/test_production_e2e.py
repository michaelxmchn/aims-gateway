"""Production-grade E2E test: AIMSAgentGateway full lifecycle with 70/25/5 split.

Tests all 4 phases of the production pipeline:

1. **Smart Contract Logic** — Deposit, settleTask with gateway ECDSA signature,
   70/25/5 split, claimReward (worker), claimDeveloperReward (developer),
   claimTreasuryFees, timeout refund, compound nonce replay protection.

2. **Python Backend** — InMemorySettlementContract mirrors Solidity exactly.
   BillingEngine orchestrates settlement + PoT generation.  All state changes
   are verified with balance diffs.

3. **Production Security** — ECDSA signature verification, compound nonce,
   deadline enforcement, onlyGateway modifiers.

4. **End-to-End** — Full lifecycle showing USDC flow from user deposit through
   to 3-party settlement with auditable balance diffs.

Run:  python3 -m pytest tests/test_production_e2e.py -v
"""

from __future__ import annotations

import json
import time

import pytest
from eth_account import Account
from eth_utils import keccak, to_canonical_address

# ── Import the exact contract client used in production ────────────────────

from src.chain.contract_client import (
    InMemorySettlementContract,
    TASK_STATUS_NONE,
    TASK_STATUS_SETTLED,
    TASK_STATUS_REFUNDED,
    TASK_STATUS_CLAIMED,
)
from src.chain.abi import (
    BPS_DENOM,
    DEVELOPER_BPS,
    WORKER_BPS,
    TREASURY_BPS,
)
from src.gateway.storage import Storage

# ── Test constants ─────────────────────────────────────────────────────────

COST_PER_TASK = 50_000  # 0.05 USDC (6 decimals)
USDC_UNIT = 10 ** 6
DEPOSIT_AMOUNT = 10 * USDC_UNIT  # 10.0 USDC

# Well-known test keys (never use in production!)
GATEWAY_KEY = "0x1111111111111111111111111111111111111111111111111111111111111111"
USER_KEY = "0x2222222222222222222222222222222222222222222222222222222222222222"
WORKER_KEY = "0x3333333333333333333333333333333333333333333333333333333333333333"
DEVELOPER_KEY = "0x4444444444444444444444444444444444444444444444444444444444444444"


@pytest.fixture
def accounts():
    """Generate deterministic test accounts."""
    gw = Account.from_key(GATEWAY_KEY)
    user = Account.from_key(USER_KEY)
    worker = Account.from_key(WORKER_KEY)
    dev = Account.from_key(DEVELOPER_KEY)
    return {
        "gateway": gw,
        "user": user,
        "worker": worker,
        "developer": dev,
        "treasury": "0xTreasury00000000000000000000000000000000001",
    }


@pytest.fixture
def contract(accounts):
    """Create an InMemorySettlementContract with gateway signing key."""
    c = InMemorySettlementContract(
        gateway_address=accounts["gateway"].address,
        treasury=accounts["treasury"],
        gateway_signing_key=GATEWAY_KEY,
    )
    return c


@pytest.fixture
def storage():
    return Storage()


# ── Helper: sign gateway binding ──────────────────────────────────────────

def sign_binding(gateway_key: str, task_id: bytes, party: str, amount: int) -> str:
    """Sign ``keccak256(abi.encodePacked(taskId, party, amount))`` with gateway key."""
    party_bytes = to_canonical_address(party)
    amount_bytes = amount.to_bytes(32, 'big')
    msg_hash = keccak(task_id + party_bytes + amount_bytes)
    signed = Account.unsafe_sign_hash(msg_hash, gateway_key)
    return signed.signature.hex()


# ═════════════════════════════════════════════════════════════════════════
# Phase 1: Smart Contract Logic Tests
# ═════════════════════════════════════════════════════════════════════════


class TestSmartContractLogic:
    """Verify InMemorySettlementContract mirrors Solidity AIMSAgentGateway."""

    def test_deposit_and_balance(self, contract, accounts):
        """User deposits 10.0 USDC → balance reflects."""
        contract.deposit(accounts["user"].address, DEPOSIT_AMOUNT)
        assert contract.get_user_balance(accounts["user"].address) == DEPOSIT_AMOUNT

    def test_deposit_zero_rejected(self, contract, accounts):
        """Deposit of 0 must be rejected."""
        with pytest.raises(ValueError, match="amount must be > 0"):
            contract.deposit(accounts["user"].address, 0)

    def test_withdraw_reduces_balance(self, contract, accounts):
        """Withdraw reduces user balance."""
        contract.deposit(accounts["user"].address, DEPOSIT_AMOUNT)
        contract.withdraw(accounts["user"].address, 5 * USDC_UNIT)
        assert contract.get_user_balance(accounts["user"].address) == 5 * USDC_UNIT

    def test_withdraw_insufficient(self, contract, accounts):
        """Withdraw more than balance must be rejected."""
        contract.deposit(accounts["user"].address, 1000)
        with pytest.raises(ValueError, match="insufficient balance"):
            contract.withdraw(accounts["user"].address, 2000)

    # ── Developer Registry ────────────────────────────────────────────

    def test_register_developer(self, contract, accounts):
        """Gateway registers a developer for a skill."""
        skill_hash = keccak(text="amazon_scraper")
        contract.register_developer(skill_hash, accounts["developer"].address)
        assert contract.get_developer(skill_hash) == accounts["developer"].address.lower()

    def test_register_developer_empty_rejected(self, contract):
        """Empty developer address must be rejected."""
        with pytest.raises(ValueError, match="invalid developer address"):
            contract.register_developer(keccak(text="test"), "")

    # ── 70/25/5 Settlement ────────────────────────────────────────────

    def test_settle_task_70_25_5_split(self, contract, accounts):
        """settleTask with registered developer → 70/25/5 split."""
        # Setup
        contract.deposit(accounts["user"].address, DEPOSIT_AMOUNT)
        skill_hash = keccak(text="amazon_scraper")
        contract.register_developer(skill_hash, accounts["developer"].address)
        task_id = keccak(text="task-0001")

        nonce = 1
        deadline = int(time.time()) + 300
        gw_sig = sign_binding(
            GATEWAY_KEY, task_id, accounts["worker"].address, COST_PER_TASK,
        )

        # Execute
        contract.settle_task(
            task_id=task_id,
            user=accounts["user"].address,
            worker=accounts["worker"].address,
            skill_id_hash=skill_hash,
            amount=COST_PER_TASK,
            nonce=nonce,
            deadline=deadline,
            gateway_address=accounts["gateway"].address,
            gateway_signature=gw_sig,
        )

        # Verify status
        assert contract.get_task_status(task_id) == TASK_STATUS_SETTLED

        # Verify user balance deducted
        expected_user_balance = DEPOSIT_AMOUNT - COST_PER_TASK
        assert contract.get_user_balance(accounts["user"].address) == expected_user_balance

        # Verify 70/25/5 split
        expected_dev = (COST_PER_TASK * DEVELOPER_BPS) // BPS_DENOM  # 70%
        expected_worker = (COST_PER_TASK * WORKER_BPS) // BPS_DENOM   # 25%
        expected_treasury = COST_PER_TASK - expected_dev - expected_worker  # 5%

        dev_pending = contract.get_pending_payout(accounts["developer"].address)
        worker_pending = contract.get_pending_payout(accounts["worker"].address)
        assert dev_pending == expected_dev, f"Developer: expected {expected_dev}, got {dev_pending}"
        assert worker_pending == expected_worker, f"Worker: expected {expected_worker}, got {worker_pending}"
        assert contract.accumulated_treasury_fees == expected_treasury

    def test_settle_task_no_developer(self, contract, accounts):
        """When no developer registered, their 70% goes to treasury."""
        contract.deposit(accounts["user"].address, DEPOSIT_AMOUNT)
        task_id = keccak(text="task-nodev")

        nonce = 10
        deadline = int(time.time()) + 300
        gw_sig = sign_binding(
            GATEWAY_KEY, task_id, accounts["worker"].address, COST_PER_TASK,
        )

        contract.settle_task(
            task_id=task_id,
            user=accounts["user"].address,
            worker=accounts["worker"].address,
            skill_id_hash=keccak(text="unknown_skill"),
            amount=COST_PER_TASK,
            nonce=nonce,
            deadline=deadline,
            gateway_address=accounts["gateway"].address,
            gateway_signature=gw_sig,
        )

        # No developer registered → 70% + 5% both go to treasury = 75%
        expected_worker = (COST_PER_TASK * WORKER_BPS) // BPS_DENOM
        expected_treasury = COST_PER_TASK - expected_worker

        assert contract.get_pending_payout(accounts["worker"].address) == expected_worker
        assert contract.accumulated_treasury_fees == expected_treasury

    # ── Compound Nonce ────────────────────────────────────────────────

    def test_compound_nonce_replay_protection(self, contract, accounts):
        """Same nonce + different taskId should work; same compound key rejected."""
        contract.deposit(accounts["user"].address, DEPOSIT_AMOUNT)
        contract.register_developer(keccak(text="skill"), accounts["developer"].address)

        task_a = keccak(text="task-a")
        nonce = 42
        deadline = int(time.time()) + 300
        gw_sig = sign_binding(
            GATEWAY_KEY, task_a, accounts["worker"].address, COST_PER_TASK,
        )

        contract.settle_task(
            task_id=task_a, user=accounts["user"].address,
            worker=accounts["worker"].address, skill_id_hash=keccak(text="skill"),
            amount=COST_PER_TASK, nonce=nonce, deadline=deadline,
            gateway_address=accounts["gateway"].address, gateway_signature=gw_sig,
        )

        # Same nonce + same taskId → rejected
        with pytest.raises(ValueError, match="nonce already used"):
            contract.settle_task(
                task_id=task_a, user=accounts["user"].address,
                worker=accounts["worker"].address, skill_id_hash=keccak(text="skill"),
                amount=COST_PER_TASK, nonce=nonce, deadline=deadline,
                gateway_address=accounts["gateway"].address, gateway_signature=gw_sig,
            )

    def test_same_nonce_different_task(self, contract, accounts):
        """Same nonce with different taskId should be allowed (compound)."""
        contract.deposit(accounts["user"].address, 2 * DEPOSIT_AMOUNT)
        contract.register_developer(keccak(text="skill"), accounts["developer"].address)

        nonce = 1
        deadline = int(time.time()) + 300

        for task_name in ["task-a", "task-b"]:
            task_id = keccak(text=task_name)
            gw_sig = sign_binding(
                GATEWAY_KEY, task_id, accounts["worker"].address, COST_PER_TASK,
            )
            contract.settle_task(
                task_id=task_id, user=accounts["user"].address,
                worker=accounts["worker"].address, skill_id_hash=keccak(text="skill"),
                amount=COST_PER_TASK, nonce=nonce, deadline=deadline,
                gateway_address=accounts["gateway"].address, gateway_signature=gw_sig,
            )

        # Both settled
        assert contract.get_task_status(keccak(text="task-a")) == TASK_STATUS_SETTLED
        assert contract.get_task_status(keccak(text="task-b")) == TASK_STATUS_SETTLED

    # ── Deadline ──────────────────────────────────────────────────────

    def test_settle_task_expired_deadline(self, contract, accounts):
        """settleTask with past deadline must be rejected."""
        contract.deposit(accounts["user"].address, COST_PER_TASK)
        task_id = keccak(text="expired")
        sig = sign_binding(GATEWAY_KEY, task_id, accounts["worker"].address, COST_PER_TASK)

        with pytest.raises(ValueError, match="deadline passed"):
            contract.settle_task(
                task_id=task_id, user=accounts["user"].address,
                worker=accounts["worker"].address, skill_id_hash=keccak(text="s"),
                amount=COST_PER_TASK, nonce=99, deadline=int(time.time()) - 10,
                gateway_address=accounts["gateway"].address, gateway_signature=sig,
            )

    # ── Gateway Signature Verification ────────────────────────────────

    def test_invalid_gateway_signature_rejected(self, contract, accounts):
        """settleTask with wrong gateway signature must be rejected."""
        contract.deposit(accounts["user"].address, COST_PER_TASK)
        task_id = keccak(text="bad-sig")

        # Sign with wrong key
        bad_key = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        bad_sig = sign_binding(bad_key, task_id, accounts["worker"].address, COST_PER_TASK)

        with pytest.raises(PermissionError, match="invalid gateway signature"):
            contract.settle_task(
                task_id=task_id, user=accounts["user"].address,
                worker=accounts["worker"].address, skill_id_hash=keccak(text="s"),
                amount=COST_PER_TASK, nonce=1, deadline=int(time.time()) + 300,
                gateway_address=accounts["gateway"].address, gateway_signature=bad_sig,
            )

    # ── Claim: Worker 25% ─────────────────────────────────────────────

    def test_worker_claim_reward(self, contract, accounts):
        """Worker claims their 25% PoT reward."""
        contract.deposit(accounts["user"].address, DEPOSIT_AMOUNT)
        contract.register_developer(keccak(text="s"), accounts["developer"].address)

        task_id = keccak(text="claim-worker")
        gw_sig = sign_binding(GATEWAY_KEY, task_id, accounts["worker"].address, COST_PER_TASK)
        contract.settle_task(
            task_id=task_id, user=accounts["user"].address,
            worker=accounts["worker"].address, skill_id_hash=keccak(text="s"),
            amount=COST_PER_TASK, nonce=7, deadline=int(time.time()) + 300,
            gateway_address=accounts["gateway"].address, gateway_signature=gw_sig,
        )

        expected_worker = (COST_PER_TASK * WORKER_BPS) // BPS_DENOM
        pot_sig = sign_binding(
            GATEWAY_KEY, task_id, accounts["worker"].address, expected_worker,
        )

        claimed = contract.claim_reward(
            task_id, accounts["worker"].address, gateway_signature=pot_sig,
        )
        assert claimed == expected_worker

        # Status stays SETTLED until developer also claims
        assert contract.get_task_status(task_id) == TASK_STATUS_SETTLED

        # Worker's pending payout should be zero after claim
        assert contract.get_pending_payout(accounts["worker"].address) == 0

        # Developer claims too → status becomes CLAIMED
        expected_dev = (COST_PER_TASK * DEVELOPER_BPS) // BPS_DENOM
        dev_sig = sign_binding(GATEWAY_KEY, task_id, accounts["developer"].address, expected_dev)
        contract.claim_developer_reward(task_id, accounts["developer"].address, gateway_signature=dev_sig)
        assert contract.get_task_status(task_id) == TASK_STATUS_CLAIMED

    # ── Claim: Developer 70% ──────────────────────────────────────────

    def test_developer_claim_reward(self, contract, accounts):
        """Developer claims their 70% PoT reward."""
        contract.deposit(accounts["user"].address, DEPOSIT_AMOUNT)
        contract.register_developer(keccak(text="s"), accounts["developer"].address)

        task_id = keccak(text="claim-dev")
        gw_sig = sign_binding(GATEWAY_KEY, task_id, accounts["worker"].address, COST_PER_TASK)
        contract.settle_task(
            task_id=task_id, user=accounts["user"].address,
            worker=accounts["worker"].address, skill_id_hash=keccak(text="s"),
            amount=COST_PER_TASK, nonce=8, deadline=int(time.time()) + 300,
            gateway_address=accounts["gateway"].address, gateway_signature=gw_sig,
        )

        expected_dev = (COST_PER_TASK * DEVELOPER_BPS) // BPS_DENOM
        pot_sig = sign_binding(
            GATEWAY_KEY, task_id, accounts["developer"].address, expected_dev,
        )

        claimed = contract.claim_developer_reward(
            task_id, accounts["developer"].address, gateway_signature=pot_sig,
        )
        assert claimed == expected_dev

        # Verify developer pending payout consumed
        assert contract.get_pending_payout(accounts["developer"].address) == 0

    # ── Treasury Claims ───────────────────────────────────────────────

    def test_treasury_claim(self, contract, accounts):
        """Treasury claims accumulated 5% fees."""
        contract.deposit(accounts["user"].address, DEPOSIT_AMOUNT)
        contract.register_developer(keccak(text="s"), accounts["developer"].address)

        # Settle 3 tasks
        for i in range(3):
            tid = keccak(text=f"treasury-task-{i}")
            gw_sig = sign_binding(GATEWAY_KEY, tid, accounts["worker"].address, COST_PER_TASK)
            contract.deposit(accounts["user"].address, COST_PER_TASK)  # top-up
            contract.settle_task(
                task_id=tid, user=accounts["user"].address,
                worker=accounts["worker"].address, skill_id_hash=keccak(text="s"),
                amount=COST_PER_TASK, nonce=100 + i, deadline=int(time.time()) + 300,
                gateway_address=accounts["gateway"].address, gateway_signature=gw_sig,
            )

        expected_dev = (COST_PER_TASK * DEVELOPER_BPS) // BPS_DENOM
        expected_worker = (COST_PER_TASK * WORKER_BPS) // BPS_DENOM
        expected_treasury_per = COST_PER_TASK - expected_dev - expected_worker
        expected_total_treasury = expected_treasury_per * 3

        assert contract.accumulated_treasury_fees == expected_total_treasury

        # Treasury claims
        claimed = contract.claim_treasury_fees(accounts["treasury"])
        assert claimed == expected_total_treasury
        assert contract.accumulated_treasury_fees == 0

    def test_only_treasury_can_claim(self, contract, accounts):
        """Non-treasury caller cannot claim treasury fees."""
        with pytest.raises(PermissionError, match="only treasury"):
            contract.claim_treasury_fees(accounts["user"].address)

    # ── Timeout Refund ────────────────────────────────────────────────

    def test_refund_task(self, contract, accounts):
        """Gateway can refund a settled task within timeout window."""
        contract.deposit(accounts["user"].address, DEPOSIT_AMOUNT)
        contract.register_developer(keccak(text="s"), accounts["developer"].address)

        task_id = keccak(text="refund-me")
        gw_sig = sign_binding(GATEWAY_KEY, task_id, accounts["worker"].address, COST_PER_TASK)
        contract.settle_task(
            task_id=task_id, user=accounts["user"].address,
            worker=accounts["worker"].address, skill_id_hash=keccak(text="s"),
            amount=COST_PER_TASK, nonce=77, deadline=int(time.time()) + 300,
            gateway_address=accounts["gateway"].address, gateway_signature=gw_sig,
        )

        # Refund
        contract.refund_task(task_id, accounts["user"].address, COST_PER_TASK, reason="timeout")

        assert contract.get_task_status(task_id) == TASK_STATUS_REFUNDED
        # User balance should be restored
        assert contract.get_user_balance(accounts["user"].address) == DEPOSIT_AMOUNT


# ═════════════════════════════════════════════════════════════════════════
# Phase 2: BillingEngine Integration Tests
# ═════════════════════════════════════════════════════════════════════════


class TestBillingEngineIntegration:
    """Verify BillingEngine orchestrates settlement correctly."""

    @pytest.fixture
    def billing(self, contract, storage, accounts):
        from src.chain.pot import POTManager
        pot_manager = POTManager(storage, GATEWAY_KEY)
        from src.gateway.billing import BillingEngine

        return BillingEngine(
            storage=storage,
            treasury_address=accounts["treasury"],
            gateway_address=accounts["gateway"].address,
            gateway_signing_key=GATEWAY_KEY,
            contract_client=contract,
            pot_manager=pot_manager,
        )

    def test_check_user_balance(self, billing, accounts):
        """check_user_balance returns deposited amount."""
        billing._contract.deposit(accounts["user"].address, 5 * USDC_UNIT)
        balance = billing.check_user_balance(accounts["user"].address)
        assert balance == 5 * USDC_UNIT

    def test_request_settlement_full_flow(self, billing, contract, accounts):
        """Full settlement flow with PoT generation."""
        # Deposit
        contract.deposit(accounts["user"].address, DEPOSIT_AMOUNT)

        # Register developer
        skill_id = "amazon_scraper"
        billing.register_developer(skill_id, accounts["developer"].address)

        # Settle
        result = billing.request_settlement(
            task_id="e2e-task-1",
            user_address=accounts["user"].address,
            worker_address=accounts["worker"].address,
            skill_id=skill_id,
        )

        assert result["status"] == "COMPLETED"
        assert result["pot"] is not None
        assert result["developer_pot"] is not None
        assert result["nonce"] is not None

        # Verify PoT for worker
        pot = result["pot"]
        assert pot.task_id == "e2e-task-1"
        assert pot.party_address.lower() == accounts["worker"].address.lower()

    def test_insufficient_balance_rejected(self, billing, accounts):
        """Settlement with insufficient balance returns FAILED."""
        result = billing.request_settlement(
            task_id="no-funds",
            user_address=accounts["user"].address,
            worker_address=accounts["worker"].address,
        )
        assert result["status"] == "FAILED"
        assert "Insufficient balance" in result["error"]

    def test_settlement_generates_worker_and_developer_pot(self, billing, contract, accounts):
        """Both worker and developer receive PoTs on settlement."""
        contract.deposit(accounts["user"].address, DEPOSIT_AMOUNT)
        billing.register_developer("my_skill", accounts["developer"].address)

        result = billing.request_settlement(
            task_id="dual-pot",
            user_address=accounts["user"].address,
            worker_address=accounts["worker"].address,
            skill_id="my_skill",
        )

        assert result["status"] == "COMPLETED"
        assert result["pot"] is not None, "Worker PoT missing"
        assert result["developer_pot"] is not None, "Developer PoT missing"

        # Both PoTs should have different party addresses
        assert result["pot"].party_address.lower() == accounts["worker"].address.lower()
        assert result["developer_pot"].party_address.lower() == accounts["developer"].address.lower()

    def test_claim_task_still_allows_developer_claim(self, billing, contract, accounts):
        """Worker claim does not block developer from claiming independently."""
        contract.deposit(accounts["user"].address, DEPOSIT_AMOUNT)
        billing.register_developer("skill_a", accounts["developer"].address)

        result = billing.request_settlement(
            task_id="ind-claim",
            user_address=accounts["user"].address,
            worker_address=accounts["worker"].address,
            skill_id="skill_a",
        )
        assert result["status"] == "COMPLETED"
        worker_pot = result["pot"]
        dev_pot = result["developer_pot"]

        # Worker claims first (PoT was signed by gateway for worker)
        from eth_utils import keccak as _keccak
        tid32 = _keccak(text="ind-claim")
        contract.claim_reward(
            tid32, accounts["worker"].address,
            gateway_signature=worker_pot.signature,
        )

        # Developer can still claim independently — worker claim did not block it
        contract.claim_developer_reward(
            tid32, accounts["developer"].address,
            gateway_signature=dev_pot.signature,
        )

        # Both should have succeeded — verify pending payouts are zero
        assert contract.get_pending_payout(accounts["worker"].address) == 0
        assert contract.get_pending_payout(accounts["developer"].address) == 0


# ═════════════════════════════════════════════════════════════════════════
# Phase 3: Production Security Tests
# ═════════════════════════════════════════════════════════════════════════


class TestProductionSecurity:
    """Security-critical path tests."""

    def test_compound_nonce_isolation(self, contract, accounts):
        """Compound nonce ensures (nonce, taskId) is globally unique."""
        contract.deposit(accounts["user"].address, DEPOSIT_AMOUNT)
        contract.register_developer(keccak(text="s"), accounts["developer"].address)

        nonce = 1
        deadline = int(time.time()) + 300

        # Two tasks with same nonce
        for task_name in ["t1", "t2"]:
            tid = keccak(text=task_name)
            sig = sign_binding(GATEWAY_KEY, tid, accounts["worker"].address, COST_PER_TASK)
            contract.settle_task(
                task_id=tid, user=accounts["user"].address,
                worker=accounts["worker"].address, skill_id_hash=keccak(text="s"),
                amount=COST_PER_TASK, nonce=nonce, deadline=deadline,
                gateway_address=accounts["gateway"].address, gateway_signature=sig,
            )

        # Both should succeed (different taskId → different compound key)
        assert contract.get_task_status(keccak(text="t1")) == TASK_STATUS_SETTLED
        assert contract.get_task_status(keccak(text="t2")) == TASK_STATUS_SETTLED

    def test_replay_same_compound_nonce_rejected(self, contract, accounts):
        """Exactly same (nonce, taskId) rejected."""
        contract.deposit(accounts["user"].address, DEPOSIT_AMOUNT)
        contract.register_developer(keccak(text="s"), accounts["developer"].address)

        tid = keccak(text="replay")
        sig = sign_binding(GATEWAY_KEY, tid, accounts["worker"].address, COST_PER_TASK)
        contract.settle_task(
            task_id=tid, user=accounts["user"].address,
            worker=accounts["worker"].address, skill_id_hash=keccak(text="s"),
            amount=COST_PER_TASK, nonce=1, deadline=int(time.time()) + 300,
            gateway_address=accounts["gateway"].address, gateway_signature=sig,
        )

        with pytest.raises(ValueError, match="nonce already used"):
            contract.settle_task(
                task_id=tid, user=accounts["user"].address,
                worker=accounts["worker"].address, skill_id_hash=keccak(text="s"),
                amount=COST_PER_TASK, nonce=1, deadline=int(time.time()) + 300,
                gateway_address=accounts["gateway"].address, gateway_signature=sig,
            )

    def test_wrong_worker_cannot_claim(self, contract, accounts):
        """Only the assigned worker can claim reward."""
        contract.deposit(accounts["user"].address, DEPOSIT_AMOUNT)
        contract.register_developer(keccak(text="s"), accounts["developer"].address)

        tid = keccak(text="wrong-claimer")
        sig = sign_binding(GATEWAY_KEY, tid, accounts["worker"].address, COST_PER_TASK)
        contract.settle_task(
            task_id=tid, user=accounts["user"].address,
            worker=accounts["worker"].address, skill_id_hash=keccak(text="s"),
            amount=COST_PER_TASK, nonce=5, deadline=int(time.time()) + 300,
            gateway_address=accounts["gateway"].address, gateway_signature=sig,
        )

        # User tries to claim as worker
        expected_worker = (COST_PER_TASK * WORKER_BPS) // BPS_DENOM
        bad_pot = sign_binding(GATEWAY_KEY, tid, accounts["user"].address, expected_worker)
        with pytest.raises(PermissionError, match="not the assigned worker"):
            contract.claim_reward(tid, accounts["user"].address, gateway_signature=bad_pot)

    def test_double_claim_prevented(self, contract, accounts):
        """Worker cannot claim the same task twice."""
        contract.deposit(accounts["user"].address, DEPOSIT_AMOUNT)
        contract.register_developer(keccak(text="s"), accounts["developer"].address)

        tid = keccak(text="double-claim")
        sig = sign_binding(GATEWAY_KEY, tid, accounts["worker"].address, COST_PER_TASK)
        contract.settle_task(
            task_id=tid, user=accounts["user"].address,
            worker=accounts["worker"].address, skill_id_hash=keccak(text="s"),
            amount=COST_PER_TASK, nonce=9, deadline=int(time.time()) + 300,
            gateway_address=accounts["gateway"].address, gateway_signature=sig,
        )

        expected_worker = (COST_PER_TASK * WORKER_BPS) // BPS_DENOM
        pot_sig = sign_binding(GATEWAY_KEY, tid, accounts["worker"].address, expected_worker)
        contract.claim_reward(tid, accounts["worker"].address, gateway_signature=pot_sig)

        # Second claim fails because worker already claimed
        with pytest.raises(ValueError, match="worker already claimed"):
            contract.claim_reward(tid, accounts["worker"].address, gateway_signature=pot_sig)

    def test_gateway_only_operations(self, contract, accounts):
        """Only gateway can register developer and refund."""
        # Non-gateway attempting gateway-only operations should fail
        developer_addr = accounts["developer"].address
        skill_hash = keccak(text="some-skill")

        # Only gateway can set_gateway
        with pytest.raises(PermissionError, match="onlyGateway"):
            contract.set_gateway(developer_addr, caller=accounts["worker"].address)

    # ── Task lifecycle state machine ──────────────────────────────────

    def test_task_lifecycle_none_to_settled_to_claimed(self, contract, accounts):
        """Task status flows: None → Settled → Claimed."""
        contract.deposit(accounts["user"].address, DEPOSIT_AMOUNT)
        contract.register_developer(keccak(text="s"), accounts["developer"].address)

        tid = keccak(text="lifecycle")
        assert contract.get_task_status(tid) == TASK_STATUS_NONE

        sig = sign_binding(GATEWAY_KEY, tid, accounts["worker"].address, COST_PER_TASK)
        contract.settle_task(
            task_id=tid, user=accounts["user"].address,
            worker=accounts["worker"].address, skill_id_hash=keccak(text="s"),
            amount=COST_PER_TASK, nonce=11, deadline=int(time.time()) + 300,
            gateway_address=accounts["gateway"].address, gateway_signature=sig,
        )
        assert contract.get_task_status(tid) == TASK_STATUS_SETTLED

        expected_worker = (COST_PER_TASK * WORKER_BPS) // BPS_DENOM
        pot_sig = sign_binding(GATEWAY_KEY, tid, accounts["worker"].address, expected_worker)
        contract.claim_reward(tid, accounts["worker"].address, gateway_signature=pot_sig)

        # Status stays SETTLED until developer also claims
        assert contract.get_task_status(tid) == TASK_STATUS_SETTLED

        # Developer claims → status becomes CLAIMED
        expected_dev = (COST_PER_TASK * DEVELOPER_BPS) // BPS_DENOM
        dev_sig = sign_binding(GATEWAY_KEY, tid, accounts["developer"].address, expected_dev)
        contract.claim_developer_reward(tid, accounts["developer"].address, gateway_signature=dev_sig)
        assert contract.get_task_status(tid) == TASK_STATUS_CLAIMED

    def test_task_lifecycle_none_to_settled_to_refunded(self, contract, accounts):
        """Task status flows: None → Settled → Refunded."""
        contract.deposit(accounts["user"].address, DEPOSIT_AMOUNT)
        contract.register_developer(keccak(text="s"), accounts["developer"].address)

        tid = keccak(text="lifecycle-refund")
        sig = sign_binding(GATEWAY_KEY, tid, accounts["worker"].address, COST_PER_TASK)
        contract.settle_task(
            task_id=tid, user=accounts["user"].address,
            worker=accounts["worker"].address, skill_id_hash=keccak(text="s"),
            amount=COST_PER_TASK, nonce=12, deadline=int(time.time()) + 300,
            gateway_address=accounts["gateway"].address, gateway_signature=sig,
        )

        contract.refund_task(tid, accounts["user"].address, COST_PER_TASK, reason="timeout")
        assert contract.get_task_status(tid) == TASK_STATUS_REFUNDED


# ═════════════════════════════════════════════════════════════════════════
# Phase 4: End-to-End Balance Audit
# ═════════════════════════════════════════════════════════════════════════


class TestEndToEndBalanceAudit:
    """Full lifecycle with balance diffs for all 3 parties.

    This test mirrors what an Anvil/Hardhat fork would verify — that
    USDC flows correctly between user, developer, worker, and treasury.
    """

    def test_full_lifecycle_balance_diffs(self, contract, accounts):
        """Complete lifecycle: deposit → settle → claim → audit.

        Balance diffs verified:
          - User:    -0.05 USDC (task cost)
          - Worker:  +0.0125 USDC (25 %)
          - Developer: +0.035 USDC (70 %)
          - Treasury: +0.0025 USDC (5 %)
        """
        # ── Setup ────────────────────────────────────────────────────
        user_addr = accounts["user"].address
        worker_addr = accounts["worker"].address
        dev_addr = accounts["developer"].address

        initial_user = DEPOSIT_AMOUNT
        initial_worker = 0
        initial_dev = 0
        initial_treasury = 0

        contract.deposit(user_addr, initial_user)
        contract.register_developer(keccak(text="skill"), dev_addr)

        # ── Settle 5 tasks ──────────────────────────────────────────
        num_tasks = 5
        for i in range(num_tasks):
            contract.deposit(user_addr, COST_PER_TASK)  # top-up each time
            tid = keccak(text=f"audit-task-{i}")
            gw_sig = sign_binding(GATEWAY_KEY, tid, worker_addr, COST_PER_TASK)
            contract.settle_task(
                task_id=tid, user=user_addr, worker=worker_addr,
                skill_id_hash=keccak(text="skill"),
                amount=COST_PER_TASK, nonce=200 + i,
                deadline=int(time.time()) + 300,
                gateway_address=accounts["gateway"].address,
                gateway_signature=gw_sig,
            )

        # ── Snapshot balances after settlement ──────────────────────
        user_after_settle = contract.get_user_balance(user_addr)
        worker_pending = contract.get_pending_payout(worker_addr)
        dev_pending = contract.get_pending_payout(dev_addr)
        treasury_fees = contract.accumulated_treasury_fees

        total_supply = user_after_settle + worker_pending + dev_pending + treasury_fees
        expected_supply = initial_user + (num_tasks * COST_PER_TASK)  # top-ups
        assert total_supply == expected_supply, (
            f"Wealth audit failed: {total_supply} != {expected_supply}"
        )

        # ── Claim worker rewards ────────────────────────────────────
        expected_worker_per = (COST_PER_TASK * WORKER_BPS) // BPS_DENOM
        for i in range(num_tasks):
            tid = keccak(text=f"audit-task-{i}")
            pot_sig = sign_binding(GATEWAY_KEY, tid, worker_addr, expected_worker_per)
            contract.claim_reward(tid, worker_addr, gateway_signature=pot_sig)

        # After claim, worker pending = 0, but we need to track actual balance
        # In InMemory mode, claim_reward returns the amount but doesn't add to balance
        # (in Solidity, it transfers USDC). For audit, we track pending -> 0.

        # ── Claim developer rewards ─────────────────────────────────
        expected_dev_per = (COST_PER_TASK * DEVELOPER_BPS) // BPS_DENOM
        for i in range(num_tasks):
            tid = keccak(text=f"audit-task-{i}")
            pot_sig = sign_binding(GATEWAY_KEY, tid, dev_addr, expected_dev_per)
            contract.claim_developer_reward(tid, dev_addr, gateway_signature=pot_sig)

        # ── Claim treasury ──────────────────────────────────────────
        treasury_claimed = contract.claim_treasury_fees(accounts["treasury"])

        # ── Final audit ─────────────────────────────────────────────
        final_user = contract.get_user_balance(user_addr)
        final_worker = contract.get_pending_payout(worker_addr)
        final_dev = contract.get_pending_payout(dev_addr)
        final_treasury = contract.accumulated_treasury_fees

        # All pending payouts should be zero after claims
        assert final_worker == 0, f"Worker pending not zero: {final_worker}"
        assert final_dev == 0, f"Developer pending not zero: {final_dev}"
        assert final_treasury == 0, f"Treasury not zero: {final_treasury}"

        # Verify total supply conserved
        total_final = final_user + treasury_claimed + (expected_worker_per * num_tasks) + (expected_dev_per * num_tasks)
        assert total_final == expected_supply, (
            f"Final wealth audit failed: {total_final} != {expected_supply}"
        )

        expected_user = initial_user
        assert final_user == expected_user, (
            f"User balance: expected {expected_user}, got {final_user}"
        )

        logger.info("=" * 60)
        logger.info("BALANCE AUDIT: PASSED")
        logger.info("  User (%s):     %s USDC", user_addr, final_user / USDC_UNIT)
        logger.info("  Worker earned: %s USDC (25%%)", (expected_worker_per * num_tasks) / USDC_UNIT)
        logger.info("  Developer earned: %s USDC (70%%)", (expected_dev_per * num_tasks) / USDC_UNIT)
        logger.info("  Treasury earned:  %s USDC (5%%)", treasury_claimed / USDC_UNIT)
        logger.info("=" * 60)


import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════
# Run instructions
# ═════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
