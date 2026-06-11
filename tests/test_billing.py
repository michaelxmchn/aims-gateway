"""Tests for the Web3 BillingEngine (on-chain settlement orchestrator).

All tests use in-memory ``Storage`` and ``InMemorySettlementContract``
— no Redis or EVM required. Gateway ECDSA signatures are generated
with a test key to match the on-chain ``ECDSA.recover`` verification.
"""

from __future__ import annotations

import time

from eth_account import Account
from eth_utils import keccak, to_canonical_address
import pytest

from src.chain.contract_client import InMemorySettlementContract
from src.chain.abi import WORKER_BPS, BPS_DENOM
from src.chain.pot import POTManager
from src.gateway.billing import BillingEngine
from src.gateway.storage import Storage


# ── Gateway key pair ────────────────────────────────────────────────────────

_GATEWAY_ACCT = Account.create()
GATEWAY_KEY = _GATEWAY_ACCT.key.hex()
GATEWAY = _GATEWAY_ACCT.address

TREASURY = "0xTreasury00000000000000000000000000000000001"
USER = "0x1111111111111111111111111111111111111111"
WORKER = "0x2222222222222222222222222222222222222222"

COST = BillingEngine.COST_PER_TASK_USDC  # 50_000 (0.05 USDC atomic)


@pytest.fixture
def contract():
    return InMemorySettlementContract(
        gateway_address=GATEWAY,
        treasury=TREASURY,
        gateway_signing_key=GATEWAY_KEY,
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
        treasury_address=TREASURY,
        gateway_address=GATEWAY,
        contract_client=contract,
        pot_manager=pot_manager,
        gateway_signing_key=GATEWAY_KEY,
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

    def test_balance_zero_for_unregistered(self):
        """Unknown address returns 0 (no auto-seed with no contract)."""
        storage = Storage()
        eng = BillingEngine(storage=storage, contract_client=None)
        bal = eng.check_user_balance("0xUnknownAddress00000000000000000000000000")
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

    def test_settlement_credits_worker_pending(self, ready_billing, funded_contract):
        ready_billing.request_settlement("task-001", USER, WORKER)
        assert funded_contract.get_pending_payout(WORKER) > 0

    def test_settlement_returns_pot(self, ready_billing):
        receipt = ready_billing.request_settlement("task-001", USER, WORKER)
        assert receipt["status"] == "COMPLETED"
        assert receipt["pot"] is not None
        assert receipt["pot"].task_id == "task-001"
        assert receipt["pot"].party_address.lower() == WORKER.lower()

    def test_settlement_insufficient_balance(self, billing):
        # USER has no balance
        receipt = billing.request_settlement("task-001", USER, WORKER)
        assert receipt["status"] == "FAILED"
        assert "Insufficient balance" in receipt["error"]

    def test_settlement_nonce_monotonic(self, ready_billing):
        r1 = ready_billing.request_settlement("task-001", USER, WORKER)
        r2 = ready_billing.request_settlement("task-002", USER, WORKER)
        assert r1["nonce"] is not None
        assert r2["nonce"] is not None

    def test_settlement_no_pot_manager(self, funded_contract):
        storage = Storage()
        eng = BillingEngine(
            storage=storage,
            contract_client=funded_contract,
            gateway_signing_key=GATEWAY_KEY,
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

        # Worker claims on-chain with PoT
        task_id_bytes = keccak(text="task-001")
        expected_payout = (COST * WORKER_BPS) // BPS_DENOM  # 25% share
        claimant_bytes = to_canonical_address(WORKER)
        amount_bytes = expected_payout.to_bytes(32, 'big')
        pot_hash = keccak(task_id_bytes + claimant_bytes + amount_bytes)
        claim_sig = Account.unsafe_sign_hash(pot_hash, GATEWAY_KEY).signature.hex()
        payout = funded_contract.claim_reward(task_id_bytes, WORKER, claim_sig)
        assert payout == expected_payout


# ── PoT generation helper ───────────────────────────────────────────────────

class TestGeneratePot:
    def test_generate_pot(self, billing):
        pot = billing.generate_pot("task-001", WORKER)
        assert pot is not None
        assert pot.task_id == "task-001"
        assert pot.party_address.lower() == WORKER.lower()

    def test_generate_pot_no_manager(self):
        storage = Storage()
        eng = BillingEngine(storage=storage, contract_client=None, pot_manager=None)
        pot = eng.generate_pot("task-001", WORKER)
        assert pot is None
