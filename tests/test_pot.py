"""Tests for Proof-of-Task (PoT) generation, verification, and persistence.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from eth_account import Account

from src.chain.pot import POTManager, ProofOfTask
from src.gateway.storage import Storage


# ── Valid EVM test addresses (0x + 40 hex chars) ──────────────────────────────

WORKER_A = "0x1111111111111111111111111111111111111111"
WORKER_B = "0x2222222222222222222222222222222222222222"
EVIL = "0x3333333333333333333333333333333333333333"


# ── Fixtures ────────────────────────────────────────────────────────────────

def make_pot_manager() -> tuple[POTManager, Storage, str]:
    storage = Storage()
    gateway_key = Account.create().key.hex()
    pm = POTManager(storage=storage, gateway_signing_key=gateway_key)
    return pm, storage, gateway_key


# ── PoT Generation ──────────────────────────────────────────────────────────

class TestPotGeneration:
    def setup_method(self) -> None:
        self.pm, self.storage, self.key = make_pot_manager()

    def test_generate_returns_proof_of_task(self) -> None:
        pot = self.pm.generate_pot("task-001", WORKER_A)
        assert isinstance(pot, ProofOfTask)
        assert pot.task_id == "task-001"
        assert pot.worker_address == WORKER_A
        assert len(pot.signature) == 130  # 65 bytes * 2 hex chars, no 0x prefix

    def test_generate_different_tasks_different_signatures(self) -> None:
        pot1 = self.pm.generate_pot("task-001", WORKER_A)
        pot2 = self.pm.generate_pot("task-002", WORKER_A)
        assert pot1.signature != pot2.signature

    def test_generate_different_workers_different_signatures(self) -> None:
        pot1 = self.pm.generate_pot("task-001", WORKER_A)
        pot2 = self.pm.generate_pot("task-001", WORKER_B)
        assert pot1.signature != pot2.signature


# ── PoT Persistence ─────────────────────────────────────────────────────────

class TestPotPersistence:
    def setup_method(self) -> None:
        self.pm, self.storage, self.key = make_pot_manager()

    def test_get_pot_returns_none_for_missing(self) -> None:
        assert self.pm.get_pot("no-such-task") is None

    def test_get_pot_after_generate(self) -> None:
        generated = self.pm.generate_pot("task-001", WORKER_A)
        retrieved = self.pm.get_pot("task-001")
        assert retrieved is not None
        assert retrieved.task_id == generated.task_id
        assert retrieved.worker_address == generated.worker_address
        assert retrieved.signature == generated.signature

    def test_pot_survives_separate_instance(self) -> None:
        self.pm.generate_pot("task-001", WORKER_A)
        # New manager with same storage should find the PoT
        pm2 = POTManager(storage=self.storage, gateway_signing_key=self.key)
        retrieved = pm2.get_pot("task-001")
        assert retrieved is not None


# ── PoT Verification ────────────────────────────────────────────────────────

class TestPotVerification:
    def setup_method(self) -> None:
        self.pm, self.storage, self.key = make_pot_manager()
        self.gateway_acct = Account.from_key(self.key)

    def test_verify_valid_pot(self) -> None:
        pot = self.pm.generate_pot("task-001", WORKER_A)
        assert self.pm.verify_pot(pot, self.gateway_acct.address)

    def test_verify_wrong_gateway_rejected(self) -> None:
        pot = self.pm.generate_pot("task-001", WORKER_A)
        wrong_addr = Account.create().address
        assert not self.pm.verify_pot(pot, wrong_addr)

    def test_verify_tampered_task_id_rejected(self) -> None:
        pot = self.pm.generate_pot("task-001", WORKER_A, amount=50_000)
        tampered = ProofOfTask(
            task_id="task-999",
            worker_address=pot.worker_address,
            amount=pot.amount,
            signature=pot.signature,
        )
        assert not self.pm.verify_pot(tampered, self.gateway_acct.address)

    def test_verify_tampered_worker_rejected(self) -> None:
        pot = self.pm.generate_pot("task-001", WORKER_A, amount=50_000)
        tampered = ProofOfTask(
            task_id=pot.task_id,
            worker_address=EVIL,
            amount=pot.amount,
            signature=pot.signature,
        )
        assert not self.pm.verify_pot(tampered, self.gateway_acct.address)
