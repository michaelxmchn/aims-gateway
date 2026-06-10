"""Web3 gateway utilities — EIP-191/EIP-712 signature verification and settlement proof generation.

Wraps ``eth_account`` and ``eth_utils`` to provide the two cryptographic
operations the AIMS gateway needs:

1. **verify_signature** — recover the signer from an EIP-191 (personal_sign)
   or EIP-712 typed-data signature so the gateway middleware can validate
   incoming requests.

2. **generate_settlement_proof** — produce the gateway's ECDSA signature
   over a ``{task_id, worker_address, amount}`` tuple, which the worker
   presents to ``claimReward()`` on-chain.
"""

from __future__ import annotations

import logging
from typing import Any

from eth_account import Account
from eth_account.messages import SignableMessage, encode_defunct, encode_typed_data
from eth_utils import keccak, to_canonical_address

logger = logging.getLogger(__name__)


# ── EIP-191 (personal_sign) verification ─────────────────────────────────────


def verify_personal_sign(
    address: str,
    message: str,
    signature: str,
) -> bool:
    """Verify an EIP-191 ``personal_sign`` signature.

    Recovers the signer from a signature over the raw *message* string.
    Useful for lightweight wallet verification where EIP-712 typed data
    is not required.

    Args:
        address:   Expected EVM signer (``0x``-prefixed, 42 chars).
        message:   The plain-text message that was signed.
        signature: Hex-encoded ECDSA signature (``0x``-prefixed, 132 chars).

    Returns:
        ``True`` if the recovered signer matches *address*.
    """
    try:
        signable: SignableMessage = encode_defunct(text=message)
        recovered = Account.recover_message(signable, signature=signature)
        return recovered.lower() == address.lower()
    except Exception as exc:
        logger.warning("EIP-191 verification failed: %s", exc)
        return False


# ── EIP-712 typed-data verification ─────────────────────────────────────────


def verify_eip712_signature(
    domain_data: dict[str, Any],
    message_types: dict[str, list[dict[str, str]]],
    message_data: dict[str, Any],
    signature: str,
    expected_signer: str,
) -> bool:
    """Verify an EIP-712 typed-data signature.

    Wraps ``encode_typed_data`` + ``Account.recover_message`` to support
    structured data signing (matching MetaMask / ethers.js ``_signTypedData``).

    Args:
        domain_data:     The EIP-712 domain dict (name, version, chainId).
        message_types:   The type definitions (without ``EIP712Domain``).
        message_data:    The actual field values matching the primary type.
        signature:       Hex-encoded signature (``0x``-prefixed).
        expected_signer: The address that should have signed.

    Returns:
        ``True`` if the recovered signer matches *expected_signer*.
    """
    try:
        signable = encode_typed_data(
            domain_data=domain_data,
            message_types=message_types,
            message_data=message_data,
        )
        recovered = Account.recover_message(signable, signature=signature)
        return recovered.lower() == expected_signer.lower()
    except Exception as exc:
        logger.warning("EIP-712 verification failed: %s", exc)
        return False


# ── Gateway settlement proof generation ──────────────────────────────────────


def _compute_settlement_message_hash(
    task_id_bytes: bytes,
    worker_address: str,
    amount: int,
) -> bytes:
    """Compute ``keccak256(abi.encodePacked(taskId, worker, amount))``.

    Matches the Solidity ``AIMSSettlement._verifyWorkerBinding`` message
    format so a signature produced here can be verified on-chain.
    """
    worker_bytes = to_canonical_address(worker_address)
    amount_bytes = amount.to_bytes(32, "big")
    return keccak(task_id_bytes + worker_bytes + amount_bytes)


def generate_settlement_proof(
    task_id: str,
    worker_address: str,
    amount: int,
    gateway_signing_key: str,
) -> str:
    """Sign a settlement proof that the worker can present to ``claimReward``.

    The signature is over ``keccak256(abi.encodePacked(taskId, worker, amount))``
    matching the Solidity contract's PoT verification.

    Args:
        task_id:             Unique task identifier (string).
        worker_address:      EVM address of the task worker.
        amount:              The exact worker payout (80 % of settlement, 6-dec
                             USDC atomic units).
        gateway_signing_key: The gateway's ECDSA private key (hex, with or
                             without ``0x`` prefix).

    Returns:
        Hex-encoded ECDSA signature string (``0x``-prefixed, 132 chars).
    """
    task_id_bytes = keccak(text=task_id)
    worker_bytes = to_canonical_address(worker_address)
    amount_bytes = amount.to_bytes(32, "big")
    message_hash = keccak(task_id_bytes + worker_bytes + amount_bytes)

    signed = Account.unsafe_sign_hash(message_hash, gateway_signing_key)
    return signed.signature.hex()


def verify_settlement_proof(
    task_id: str,
    worker_address: str,
    amount: int,
    signature: str,
    expected_gateway_address: str,
) -> bool:
    """Off-chain verification of a settlement proof (PoT).

    Recomputes the hash and recovers the signer, matching the on-chain
    ``ECDSA.recover`` path.

    Args:
        task_id:                 Task identifier string.
        worker_address:          EVM address of the worker.
        amount:                  Worker payout in atomic USDC (6 decimals).
        signature:               Hex-encoded ECDSA signature.
        expected_gateway_address: The gateway's EVM address.

    Returns:
        ``True`` if the recovered signer matches *expected_gateway_address*.
    """
    try:
        task_id_bytes = keccak(text=task_id)
        worker_bytes = to_canonical_address(worker_address)
        amount_bytes = amount.to_bytes(32, "big")
        message_hash = keccak(task_id_bytes + worker_bytes + amount_bytes)
        recovered = Account._recover_hash(message_hash, signature=signature)
        return recovered.lower() == expected_gateway_address.lower()
    except Exception as exc:
        logger.warning("Settlement proof verification failed: %s", exc)
        return False
