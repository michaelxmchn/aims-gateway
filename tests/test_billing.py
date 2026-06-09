"""Tests for the AIMS Credit & Revenue system (BillingEngine + TransactionLedger).

All tests use the in-memory ``Storage`` fallback — no Redis required.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.gateway.billing import BillingEngine
from src.gateway.ledger import TransactionLedger
from src.gateway.storage import Storage


# ── Helpers ────────────────────────────────────────────────────────────────

def make_billing(owner_id: str = "test_owner") -> tuple[BillingEngine, Storage]:
    storage = Storage()
    billing = BillingEngine(storage=storage, owner_id=owner_id)
    return billing, storage


def make_ledger() -> tuple[TransactionLedger, Storage]:
    storage = Storage()
    ledger = TransactionLedger(storage=storage)
    return ledger, storage


# ── BillingEngine — Balance API ────────────────────────────────────────────

class TestBillingBalance:
    def setup_method(self) -> None:
        self.billing, _ = make_billing()

    def test_deposit_increases_balance(self) -> None:
        new_bal = self.billing.deposit("alice", 10.0)
        assert new_bal == 10.0
        assert self.billing.get_balance("alice") == 10.0

    def test_deposit_accumulates(self) -> None:
        self.billing.deposit("alice", 5.0)
        self.billing.deposit("alice", 3.0)
        assert self.billing.get_balance("alice") == 8.0

    def test_get_balance_default_zero(self) -> None:
        assert self.billing.get_balance("nonexistent") == 0.0

    def test_deposit_rounds_to_4dp(self) -> None:
        new_bal = self.billing.deposit("alice", 1.23456789)
        assert new_bal == 1.2346  # rounded to 4dp

    def test_multiple_users_independent(self) -> None:
        self.billing.deposit("alice", 10.0)
        self.billing.deposit("bob", 20.0)
        assert self.billing.get_balance("alice") == 10.0
        assert self.billing.get_balance("bob") == 20.0

    def test_worker_balance(self) -> None:
        self.billing.deposit("worker-01", 5.0)
        assert self.billing.get_worker_balance("worker-01") == 5.0

    def test_owner_balance(self) -> None:
        self.billing.deposit("test_owner", 2.0)
        assert self.billing.get_owner_balance() == 2.0


# ── BillingEngine — Reservation API ────────────────────────────────────────

class TestBillingReservation:
    def setup_method(self) -> None:
        self.billing, _ = make_billing()

    def test_reserve_with_sufficient_balance(self) -> None:
        self.billing.deposit("alice", 1.0)
        assert self.billing.reserve_credits("task-001", "alice") is True

    def test_reserve_with_insufficient_balance(self) -> None:
        assert self.billing.reserve_credits("task-001", "alice") is False

    def test_reserve_exact_amount(self) -> None:
        self.billing.deposit("alice", BillingEngine.COST_PER_TASK)
        assert self.billing.reserve_credits("task-001", "alice") is True

    def test_reservation_stores_metadata(self) -> None:
        self.billing.deposit("alice", 1.0)
        self.billing.reserve_credits("task-001", "alice")
        reservation = self.billing.get_reservation("task-001")
        assert reservation is not None
        assert reservation["user_id"] == "alice"
        assert reservation["amount"] == BillingEngine.COST_PER_TASK

    def test_reservation_nonexistent(self) -> None:
        assert self.billing.get_reservation("no-such-task") is None


# ── BillingEngine — Settlement API ─────────────────────────────────────────

class TestBillingSettlement:
    def setup_method(self) -> None:
        self.billing, _ = make_billing()
        self.billing.deposit("alice", 1.0)
        self.billing.reserve_credits("task-001", "alice")

    def test_settle_success_deducts_from_user(self) -> None:
        self.billing.settle_task("task-001", "worker-01", success=True)
        expected = round(1.0 - BillingEngine.COST_PER_TASK, 4)
        assert self.billing.get_balance("alice") == expected

    def test_settle_success_pays_worker(self) -> None:
        self.billing.settle_task("task-001", "worker-01", success=True)
        expected = round(BillingEngine.COST_PER_TASK * BillingEngine.WORKER_SHARE, 4)
        assert self.billing.get_worker_balance("worker-01") == expected

    def test_settle_success_pays_owner(self) -> None:
        self.billing.settle_task("task-001", "worker-01", success=True)
        expected = round(BillingEngine.COST_PER_TASK * BillingEngine.OWNER_SHARE, 4)
        assert self.billing.get_owner_balance() == expected

    def test_settle_success_exact_split(self) -> None:
        receipt = self.billing.settle_task("task-001", "worker-01", success=True)
        assert receipt is not None
        assert receipt["cost"] == BillingEngine.COST_PER_TASK
        assert receipt["worker_payout"] == round(BillingEngine.COST_PER_TASK * 0.80, 4)
        assert receipt["gateway_payout"] == round(BillingEngine.COST_PER_TASK * 0.20, 4)
        assert receipt["status"] == "COMPLETED"

    def test_settle_worker_is_owner(self) -> None:
        """When worker == owner, all revenue goes to the worker."""
        self.billing.deposit("bob", 1.0)
        self.billing.reserve_credits("task-002", "bob")
        self.billing.settle_task("task-002", "test_owner", success=True)
        # Owner (test_owner) already gets 20%. Worker (test_owner) also gets 80%.
        # Since they are the same, all 0.05 goes to test_owner
        assert self.billing.get_owner_balance() == 0.05

    def test_settle_failure_no_deduction(self) -> None:
        receipt = self.billing.settle_task("task-001", "worker-01", success=False)
        assert receipt is not None
        assert receipt["status"] == "REFUNDED"
        assert receipt["cost"] == 0.0
        assert receipt["worker_payout"] == 0.0
        assert receipt["gateway_payout"] == 0.0
        # Alice's balance should be unchanged
        assert self.billing.get_balance("alice") == 1.0

    def test_settle_failure_releases_reservation(self) -> None:
        self.billing.settle_task("task-001", "worker-01", success=False)
        assert self.billing.get_reservation("task-001") is None

    def test_settle_no_reservation_returns_none(self) -> None:
        result = self.billing.settle_task("no-such-task", "worker-01", success=True)
        assert result is None

    def test_double_spend_idempotent(self) -> None:
        """Second call returns the same receipt, no double deduction."""
        r1 = self.billing.settle_task("task-001", "worker-01", success=True)
        r2 = self.billing.settle_task("task-001", "worker-01", success=True)
        assert r2 is not None
        assert r2["status"] == r1["status"]
        # Balance should be deducted only once
        assert self.billing.get_balance("alice") == round(1.0 - 0.05, 4)

    def test_settle_no_user_in_reservation(self) -> None:
        """Corner case: reservation with no user_id."""
        self.billing._storage.dict_set(
            self.billing.NS_RESERVED, "bad-task", {"amount": 0.05}
        )
        result = self.billing.settle_task("bad-task", "worker-01", success=True)
        assert result is None  # should fail gracefully


# ── TransactionLedger ──────────────────────────────────────────────────────

class TestTransactionLedger:
    def setup_method(self) -> None:
        self.ledger, self.storage = make_ledger()

    def test_record_returns_tx_id(self) -> None:
        tx_id = self.ledger.record("deposit", "alice", 10.0, "Initial deposit")
        assert tx_id.startswith("txn-")

    def test_get_transaction(self) -> None:
        tx_id = self.ledger.record("deposit", "alice", 10.0, "Initial deposit")
        txn = self.ledger.get_transaction(tx_id)
        assert txn is not None
        assert txn["type"] == "deposit"
        assert txn["user_id"] == "alice"
        assert txn["amount"] == 10.0

    def test_get_transaction_nonexistent(self) -> None:
        assert self.ledger.get_transaction("no-such") is None

    def test_get_user_history(self) -> None:
        self.ledger.record("deposit", "alice", 10.0, "First")
        self.ledger.record("deposit", "alice", 5.0, "Second")
        history = self.ledger.get_user_history("alice")
        assert len(history) == 2
        # Most recent first
        assert history[0]["amount"] == 5.0

    def test_get_user_history_other_user(self) -> None:
        self.ledger.record("deposit", "alice", 10.0, "Alice")
        history = self.ledger.get_user_history("bob")
        assert len(history) == 0

    def test_get_all_transactions(self) -> None:
        self.ledger.record("deposit", "alice", 10.0, "First")
        self.ledger.record("deposit", "bob", 5.0, "Second")
        all_txns = self.ledger.get_all(limit=10)
        assert len(all_txns) == 2

    def test_get_all_respects_limit(self) -> None:
        for i in range(5):
            self.ledger.record("deposit", "alice", float(i), f"Txn {i}")
        all_txns = self.ledger.get_all(limit=3)
        assert len(all_txns) == 3

    def test_metadata_included(self) -> None:
        tx_id = self.ledger.record(
            "task_deduction", "alice", -0.05,
            "Task task-001 deduction",
            metadata={"task_id": "task-001", "worker_id": "worker-01"},
        )
        txn = self.ledger.get_transaction(tx_id)
        assert txn is not None
        assert txn["metadata"]["task_id"] == "task-001"
        assert txn["metadata"]["worker_id"] == "worker-01"


# ── Full lifecycle integration ────────────────────────────────────────────

class TestBillingFullLifecycle:
    """End-to-end: deposit → reserve → settle SUCCESS → verify split."""

    def setup_method(self) -> None:
        self.billing, _ = make_billing()

    def test_deposit_reserve_settle_lifecycle(self) -> None:
        # 1. Deposit
        self.billing.deposit("alice", 1.0)
        assert self.billing.get_balance("alice") == 1.0

        # 2. Reserve
        assert self.billing.reserve_credits("task-001", "alice") is True

        # 3. Settle SUCCESS
        receipt = self.billing.settle_task("task-001", "worker-01", success=True)
        assert receipt is not None
        assert receipt["status"] == "COMPLETED"

        # 4. Verify balances
        assert self.billing.get_balance("alice") == round(1.0 - 0.05, 4)
        assert self.billing.get_worker_balance("worker-01") == round(0.05 * 0.80, 4)
        assert self.billing.get_owner_balance() == round(0.05 * 0.20, 4)

    def test_deposit_reserve_settle_failed_lifecycle(self) -> None:
        self.billing.deposit("alice", 1.0)
        self.billing.reserve_credits("task-001", "alice")
        receipt = self.billing.settle_task("task-001", "worker-01", success=False)

        assert receipt is not None
        assert receipt["status"] == "REFUNDED"

        # Full refund — alice keeps everything
        assert self.billing.get_balance("alice") == 1.0
        assert self.billing.get_worker_balance("worker-01") == 0.0
        assert self.billing.get_owner_balance() == 0.0

    def test_insufficient_credits_prevents_reserve(self) -> None:
        self.billing.deposit("alice", 0.03)  # Less than COST_PER_TASK
        assert self.billing.reserve_credits("task-001", "alice") is False

    def test_exact_credit_balance_works(self) -> None:
        self.billing.deposit("alice", BillingEngine.COST_PER_TASK)
        assert self.billing.reserve_credits("task-001", "alice") is True
        receipt = self.billing.settle_task("task-001", "worker-01", success=True)
        assert receipt is not None
        assert receipt["status"] == "COMPLETED"
        assert self.billing.get_balance("alice") == 0.0

    def test_owner_id_configurable(self) -> None:
        billing2, _ = make_billing(owner_id="custom_owner")
        assert billing2.get_owner_balance() == 0.0
        billing2.deposit("custom_owner", 100.0)
        assert billing2.get_owner_balance() == 100.0
