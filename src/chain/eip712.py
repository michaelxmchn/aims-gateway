"""EIP-712 typed data structures and signing/verification helpers.

Uses ``eth_account`` for encoding and verification so the implementation
matches what wallets (MetaMask, Rabby) produce.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from eth_account import Account
from eth_typing import HexStr

logger = logging.getLogger(__name__)

# ── EIP-712 Domain ───────────────────────────────────────────────────────────

AIMS_DOMAIN: dict[str, Any] = {
    "name": "AIMS Gateway",
    "version": "1",
    "chainId": int(os.getenv("AIMS_CHAIN_ID", "8453")),  # Base mainnet
}

# ── Type definitions ─────────────────────────────────────────────────────────

RUN_REQUEST_TYPES: dict[str, list[dict[str, str]]] = {
    "EIP712Domain": [
        {"name": "name", "type": "string"},
        {"name": "version", "type": "string"},
        {"name": "chainId", "type": "uint256"},
    ],
    "AIMSRunRequest": [
        {"name": "skillId", "type": "string"},
        {"name": "paramsHash", "type": "bytes32"},
        {"name": "nonce", "type": "uint256"},
        {"name": "deadline", "type": "uint256"},
    ],
}

SUBMIT_REQUEST_TYPES: dict[str, list[dict[str, str]]] = {
    "EIP712Domain": [
        {"name": "name", "type": "string"},
        {"name": "version", "type": "string"},
        {"name": "chainId", "type": "uint256"},
    ],
    "AIMSSubmitRequest": [
        {"name": "taskId", "type": "string"},
        {"name": "resultHash", "type": "bytes32"},
        {"name": "nonce", "type": "uint256"},
        {"name": "deadline", "type": "uint256"},
    ],
}

DEPOSIT_REQUEST_TYPES: dict[str, list[dict[str, str]]] = {
    "EIP712Domain": [
        {"name": "name", "type": "string"},
        {"name": "version", "type": "string"},
        {"name": "chainId", "type": "uint256"},
    ],
    "AIMSDepositRequest": [
        {"name": "amount", "type": "uint256"},
        {"name": "nonce", "type": "uint256"},
        {"name": "deadline", "type": "uint256"},
    ],
}


# ── Signing ──────────────────────────────────────────────────────────────────


def _strip_domain(types: dict[str, list[dict[str, str]]]) -> dict[str, list[dict[str, str]]]:
    """Return a copy of *types* without the ``EIP712Domain`` key.

    The 3-argument form of ``sign_typed_data`` / ``encode_typed_data``
    requires that ``message_types`` does *not* include ``EIP712Domain``.
    """
    return {k: v for k, v in types.items() if k != "EIP712Domain"}


def sign_eip712_message(
    private_key: str,
    types: dict[str, list[dict[str, str]]],
    domain: dict[str, Any],
    value: dict[str, Any],
) -> str:
    """Sign an EIP-712 typed data message with the given private key.

    Returns the hex-encoded signature string (132 chars, ``0x``-prefixed).
    """
    signed = Account.sign_typed_data(
        private_key=private_key,
        domain_data=domain,
        message_types=_strip_domain(types),
        message_data=value,
    )
    return signed.signature.hex()  # type: ignore[return-value]


# ── Verification ─────────────────────────────────────────────────────────────


def verify_eip712_signature(
    types: dict[str, list[dict[str, str]]],
    domain: dict[str, Any],
    value: dict[str, Any],
    signature: str,
    expected_signer: str,
) -> bool:
    """Recover the signer from an EIP-712 signature and compare to *expected_signer*.

    Uses ``encode_typed_data`` + ``recover_message`` (``recover_typed_data``
    is unavailable in eth_account 0.13.x).

    Returns ``True`` if recovered signer matches (case-insensitive).
    """
    try:
        from eth_account.messages import encode_typed_data

        signable = encode_typed_data(
            domain_data=domain,
            message_types=_strip_domain(types),
            message_data=value,
        )
        recovered = Account.recover_message(signable, signature=signature)
        return recovered.lower() == expected_signer.lower()
    except Exception as exc:
        logger.warning("EIP-712 verification failed: %s", exc)
        return False


# ── Value builders ───────────────────────────────────────────────────────────


def make_run_request_value(
    skill_id: str,
    params: dict[str, Any],
    nonce: int,
    deadline: int,
) -> dict[str, Any]:
    """Build the *value* dict for an ``AIMSRunRequest``.

    The ``paramsHash`` is ``keccak256(json.dumps(params, sort_keys=True))``.
    """
    from eth_utils import keccak

    params_json = json.dumps(params, sort_keys=True, default=str)
    params_hash = keccak(text=params_json)
    return {
        "skillId": skill_id,
        "paramsHash": params_hash,
        "nonce": nonce,
        "deadline": deadline,
    }


def make_submit_request_value(
    task_id: str,
    result_data: dict[str, Any],
    nonce: int,
    deadline: int,
) -> dict[str, Any]:
    """Build the *value* dict for an ``AIMSSubmitRequest``."""
    from eth_utils import keccak

    result_json = json.dumps(result_data, sort_keys=True, default=str)
    result_hash = keccak(text=result_json)
    return {
        "taskId": task_id,
        "resultHash": result_hash,
        "nonce": nonce,
        "deadline": deadline,
    }


def make_deposit_request_value(
    amount: int,
    nonce: int,
    deadline: int,
) -> dict[str, Any]:
    """Build the *value* dict for an ``AIMSDepositRequest``."""
    return {
        "amount": amount,
        "nonce": nonce,
        "deadline": deadline,
    }
