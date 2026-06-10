"""Tests for EIP-712 typed data signing and verification.

Uses ephemeral ``eth_account`` wallets — no external signer required.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from eth_account import Account

from src.chain.eip712 import (
    AIMS_DOMAIN,
    RUN_REQUEST_TYPES,
    SUBMIT_REQUEST_TYPES,
    DEPOSIT_REQUEST_TYPES,
    make_run_request_value,
    make_submit_request_value,
    make_deposit_request_value,
    sign_eip712_message,
    verify_eip712_signature,
)


# ── Fixtures ────────────────────────────────────────────────────────────────

def make_wallet():
    acct = Account.create()
    return acct.key.hex(), acct.address


# ── Sign / Recover ──────────────────────────────────────────────────────────

class TestSignAndVerify:
    def setup_method(self) -> None:
        self.key, self.addr = make_wallet()

    def test_sign_and_verify_run_request(self) -> None:
        value = make_run_request_value(
            skill_id="amazon_scraper",
            params={"url": "https://example.com"},
            nonce=0,
            deadline=int(time.time()) + 3600,
        )
        sig = sign_eip712_message(self.key, RUN_REQUEST_TYPES, AIMS_DOMAIN, value)
        assert len(sig) == 130  # 65 bytes * 2 hex chars = 130, no 0x prefix

        assert verify_eip712_signature(
            RUN_REQUEST_TYPES, AIMS_DOMAIN, value, sig, self.addr,
        )

    def test_sign_and_verify_submit_request(self) -> None:
        value = make_submit_request_value(
            task_id="task-0001",
            result_data={"status": "done"},
            nonce=1,
            deadline=int(time.time()) + 3600,
        )
        sig = sign_eip712_message(self.key, SUBMIT_REQUEST_TYPES, AIMS_DOMAIN, value)
        assert verify_eip712_signature(
            SUBMIT_REQUEST_TYPES, AIMS_DOMAIN, value, sig, self.addr,
        )

    def test_sign_and_verify_deposit_request(self) -> None:
        value = make_deposit_request_value(
            amount=50_000,
            nonce=2,
            deadline=int(time.time()) + 3600,
        )
        sig = sign_eip712_message(self.key, DEPOSIT_REQUEST_TYPES, AIMS_DOMAIN, value)
        assert verify_eip712_signature(
            DEPOSIT_REQUEST_TYPES, AIMS_DOMAIN, value, sig, self.addr,
        )

    def test_wrong_signer_rejected(self) -> None:
        _, wrong_addr = make_wallet()
        value = make_run_request_value("test", {}, 0, int(time.time()) + 3600)
        sig = sign_eip712_message(self.key, RUN_REQUEST_TYPES, AIMS_DOMAIN, value)
        assert not verify_eip712_signature(
            RUN_REQUEST_TYPES, AIMS_DOMAIN, value, sig, wrong_addr,
        )

    def test_tampered_value_rejected(self) -> None:
        value = make_run_request_value("test", {}, 0, int(time.time()) + 3600)
        sig = sign_eip712_message(self.key, RUN_REQUEST_TYPES, AIMS_DOMAIN, value)
        tampered = dict(value, nonce=99)
        assert not verify_eip712_signature(
            RUN_REQUEST_TYPES, AIMS_DOMAIN, tampered, sig, self.addr,
        )


# ── Value builders ──────────────────────────────────────────────────────────

class TestValueBuilders:
    def test_params_hash_deterministic(self) -> None:
        v1 = make_run_request_value("test", {"a": 1, "b": 2}, 0, 1000)
        v2 = make_run_request_value("test", {"b": 2, "a": 1}, 0, 1000)
        assert v1["paramsHash"] == v2["paramsHash"]

    def test_params_hash_changes_with_data(self) -> None:
        v1 = make_run_request_value("test", {"a": 1}, 0, 1000)
        v2 = make_run_request_value("test", {"a": 2}, 0, 1000)
        assert v1["paramsHash"] != v2["paramsHash"]

    def test_result_hash_deterministic(self) -> None:
        v1 = make_submit_request_value("task-1", {"x": 10, "y": 20}, 0, 1000)
        v2 = make_submit_request_value("task-1", {"y": 20, "x": 10}, 0, 1000)
        assert v1["resultHash"] == v2["resultHash"]

    def test_deposit_value_structure(self) -> None:
        value = make_deposit_request_value(50_000, 5, 2000)
        assert value["amount"] == 50_000
        assert value["nonce"] == 5
        assert value["deadline"] == 2000
