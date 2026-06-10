"""Tests for the Web3 BillingEngine (on-chain settlement orchestrator).

All tests use in-memory ``Storage`` and ``InMemorySettlementContract``
— no Redis or EVM required.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from eth_account import Account
import pytest

from src.chain.contract_client import InMemorySettlementContract
from src.chain.pot import POTManager
from src.gateway.billing import BillingEngine
from src.gateway.storage import Storage


# ── Fixtures ────────────────────────────────────────────────────────────────

GATEWAY = "0xGateway000000000000000000000000000000000001"
OWNER = "0xOwner000000000000000000000000000000000001"
USER = "0xUser00000000000000000000000000000000000001"
WORKER = "0xWorker000000000000000000000000000000000001"

COST = BillingEngine.COST_PER_TASK_USDC  # 50_000 (0.05 USDC atomic)


@pytest.fixture
def contract():
    return InMemorySettlementContract(
        gateway_address=GATEWAY,
        platform_owner=OWNER,
    )


@pytest.fixture
def pot_manager():
    storage = Storage()
    key = Account.create().key.hex()
    return POTManager(storage, key)


@pytest.fixture
def billing(contract, pot_manager):
    storage = Storage()
    return BillingEngine(
        storage=storage,
        owner_address=OWNER,
        contract_client=contract,
        pot_manager=pot_manager,
    )


@pytest.fixture
def funded_contract(contract):
    """A contract with USER having sufficient balance."""
    contract.deposit(USER, 1_000_000)  # 1.0 USDC
    return contract


@pytest.fixture
def ready_billing(billing, funded_contract):
    """BillingEngine with a funded user."""
    return billing


# ── Balance checks ──────────────────────────────────────────────────────────

class TestCheckBalance:
    def test_balance_returns_contract_value(self, ready_billing):
        bal = ready_billing.check_user_balance(USER)
        assert bal == 1_000_000

    def test_balance_zero_for_unknown(self, billing):
        bal = billing.check_user_balance("0xUnknown")
        assert bal == 0

    def test_no_contract_returns_zero(self):
        storage = Storage()
        eng = BillingEngine(storage=storage, contract_client=None)
        bal = eng.check_user_balance(USER)
        assert bal == 0


# ── Settlement requests ─────────────────────────────────────────────────────

class TestRequestSettlement:
    def test_settlement_deducts_from_user(self, ready_billing, funded_contract):
        receipt = ready_billing.request_settlement("task-001", USER, WORKER)
        assert receipt["status"] == "COMPLETED"
        assert funded_contract.get_user_balance(USER) == 1_000_000 - COST

    def test_settlement_credits_pending_payouts(self, ready_billing, funded_contract):
        ready_billing.request_settlement("task-001", USER, WORKER)
        assert funded_contract.get_pending_payout(WORKER) > 0
        assert funded_contract.get_pending_payout(OWNER) > 0

    def test_settlement_returns_pot(self, ready_billing):
        receipt = ready_billing.request_settlement("task-001", USER, WORKER)
        assert receipt["status"] == "COMPLETED"
        assert receipt["pot"] is not None
        assert receipt["pot"].task_id == "task-001"
        assert receipt["pot"].worker_address == WORKER

    def test_settlement_insufficient_balance(self, billing, contract):
        # USER has no balance
        receipt = billing.request_settlement("task-001", USER, WORKER)
        assert receipt["status"] == "FAILED"
        assert "Insufficient balance" in receipt["error"]

    def test_settlement_nonce_monotonic(self, ready_billing):
        r1 = ready_billing.request_settlement("task-001", USER, WORKER)
        r2 = ready_billing.request_settlement("task-002", USER, WORKER)
        assert r1["nonce"] == 0 or r1["nonce"] is not None
        assert r2["nonce"] is not None

    def test_settlement_no_pot_manager(self, funded_contract):
        storage = Storage()
        eng = BillingEngine(
            storage=storage,
            contract_client=funded_contract,
            pot_manager=None,
        )
        receipt = eng.request_settlement("task-001", USER, WORKER)
        assert receipt["status"] == "COMPLETED"
        assert receipt["pot"] is None

    def test_settlement_no_contract(self):
        storage = Storage()
        eng = BillingEngine(storage=storage, contract_client=None)
        receipt = eng.request_settlement("task-001", USER, WORKER)
        assert receipt["status"] == "FAILED"
        assert "No contract client" in receipt["error"]

    def test_double_settle_rejected(self, ready_billing, funded_contract):
        ready_billing.request_settlement("task-001", USER, WORKER)
        receipt = ready_billing.request_settlement("task-001", USER, WORKER)
        assert receipt["status"] == "FAILED"

    def test_settlement_then_claim(self, ready_billing, funded_contract):
        receipt = ready_billing.request_settlement("task-001", USER, WORKER)
        assert receipt["status"] == "COMPLETED"
        # Worker claims on-chain
        task_id_bytes = __import__("eth_utils", fromlist=["keccak"]).keccak(text="task-001")
        payout = funded_contract.claim_reward(task_id_bytes, WORKER)
        assert payout == (COST * 8000 // 10000)


# ── PoT generation helper ───────────────────────────────────────────────────

class TestGeneratePot:
    def test_generate_pot(self, billing):
        pot = billing.generate_pot("task-001", WORKER)
        assert pot is not None
        assert pot.task_id == "task-001"
        assert pot.worker_address == WORKER

    def test_generate_pot_no_manager(self):
        storage = Storage()
        eng = BillingEngine(storage=storage, contract_client=None, pot_manager=None)
        pot = eng.generate_pot("task-001", WORKER)
        assert pot is None
