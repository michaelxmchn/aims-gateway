"""Proof-of-Task (PoT) — gateway-signed task completion receipts.

A PoT is an ECDSA signature produced by the gateway over
``keccak256(abi.encodePacked(taskId, workerAddress, amount))``.
Workers present this to the on-chain contract to claim their 80 % reward.

Hash format
-----------
The signed message uses **bytes-level concatenation** to match the
Solidity ``abi.encodePacked`` behaviour:

    message = keccak256(abi.encodePacked(
        keccak256(task_id_str),     # bytes32
        worker_address_bytes,       # 20 bytes
        amount                      # uint256 → 32 bytes big-endian
    ))

This ensures a signature produced by the Python gateway can be verified
on-chain via ``ECDSA.recover()``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Optional

from eth_account import Account
from eth_utils import keccak, to_bytes, to_canonical_address

from src.gateway.storage import Storage

logger = logging.getLogger(__name__)

NS_POT = "chain:pot"


@dataclass
class ProofOfTask:
    """A signed proof that *worker_address* completed *task_id*."""

    task_id: str
    worker_address: str
    amount: int  # USDC atomic units (6 decimals)
    signature: str  # hex-encoded ECDSA signature, 0x-prefixed

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "worker_address": self.worker_address,
            "amount": self.amount,
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ProofOfTask:
        return cls(
            task_id=data["task_id"],
            worker_address=data["worker_address"],
            amount=data.get("amount", 0),
            signature=data["signature"],
        )


def _compute_pot_hash(task_id: str, worker_address: str, amount: int) -> bytes:
    """Compute the hash that the gateway signs.

    Matches Solidity::

        keccak256(abi.encodePacked(
            keccak256(task_id_str),     # bytes32
            worker_address,              # address → 20 bytes
            amount                       # uint256 → 32 bytes big-endian
        ))
    """
    task_id_bytes = keccak(text=task_id)  # bytes32
    worker_bytes = to_canonical_address(worker_address)  # 20 bytes
    amount_bytes = amount.to_bytes(32, 'big')  # uint256 → 32 bytes big-endian
    return keccak(task_id_bytes + worker_bytes + amount_bytes)


class POTManager:
    """Generates, persists, and verifies Proof-of-Task receipts.

    The manager uses two components:
      * An ECDSA signing key (the gateway's private key) for generation.
      * The shared ``Storage`` backend for persistence so PoTs survive
        restarts and can be fetched by workers via the API.
    """

    def __init__(self, storage: Storage, gateway_signing_key: str) -> None:
        self._storage = storage
        self._signing_key = gateway_signing_key

    # ── Generation ─────────────────────────────────────────────────────────

    def generate_pot(
        self, task_id: str, worker_address: str, amount: int = 0
    ) -> ProofOfTask:
        """Create and persist a PoT for the given task + worker.

        The signature is over the bytes-level concatenation of
        ``keccak256(task_id) ++ worker_address ++ amount`` using the
        gateway's ECDSA key (``Account.unsafe_sign_hash``).
        """
        message_hash = _compute_pot_hash(task_id, worker_address, amount)
        signed = Account.unsafe_sign_hash(message_hash, self._signing_key)
        signature = signed.signature.hex()

        pot = ProofOfTask(
            task_id=task_id,
            worker_address=worker_address,
            amount=amount,
            signature=signature,
        )

        # Persist
        key = f"{NS_POT}:{task_id}"
        self._storage.set(key, json.dumps(pot.to_dict()))
        logger.debug(
            "PoT generated: task=%s worker=%s amount=%d sig=%s…",
            task_id, worker_address, amount, signature[:16],
        )
        return pot

    # ── Retrieval ──────────────────────────────────────────────────────────

    def get_pot(self, task_id: str) -> Optional[ProofOfTask]:
        """Retrieve a previously stored PoT by task ID."""
        key = f"{NS_POT}:{task_id}"
        raw = self._storage.get(key)
        if raw is None:
            return None
        try:
            data = json.loads(raw)
            return ProofOfTask.from_dict(data)
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("Corrupt PoT data for task %s: %s", task_id, exc)
            return None

    # ── Verification ───────────────────────────────────────────────────────

    def verify_pot(
        self, pot: ProofOfTask, expected_gateway_address: str
    ) -> bool:
        """Off-chain verification: recover the signer and compare addresses.

        Recomputes the hash from the PoT fields and recovers the signer
        via ``eth_account.Account._recover_hash``.  This mirrors the
        on-chain ``ECDSA.recover()`` path.
        """
        try:
            message_hash = _compute_pot_hash(
                pot.task_id, pot.worker_address, pot.amount
            )
            recovered = Account._recover_hash(
                message_hash, signature=pot.signature
            )
            return recovered.lower() == expected_gateway_address.lower()
        except Exception as exc:
            logger.warning("PoT verification failed: %s", exc)
            return False
