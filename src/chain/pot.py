"""Proof-of-Task (PoT) — gateway-signed task completion receipts.

A PoT is an ECDSA signature produced by the gateway over
``keccak256(abi.encodePacked(taskId, partyAddress, amount))``.
The contract verifies this via ``ECDSA.recover``.

Workers present their PoT to ``claimReward()`` for their 25 % share.
Developers present theirs to ``claimDeveloperReward()`` for their 70 % share.

Hash format
-----------
The signed message uses bytes-level concatenation to match the
Solidity ``abi.encodePacked`` behaviour::

    message = keccak256(abi.encodePacked(
        keccak256(task_id_str),     # bytes32
        party_address_bytes,         # 20 bytes
        amount_bytes                 # uint256 → 32 bytes big-endian
    ))
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Optional

from eth_account import Account
from eth_utils import keccak, to_canonical_address

from src.gateway.storage import Storage

logger = logging.getLogger(__name__)

NS_POT = "chain:pot"


@dataclass
class ProofOfTask:
    """A signed proof that *party_address* completed *task_id*."""

    task_id: str
    party_address: str  # Worker or Developer
    amount: int  # USDC atomic units (6 decimals)
    signature: str  # hex-encoded ECDSA signature, 0x-prefixed

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "party_address": self.party_address,
            "amount": self.amount,
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ProofOfTask:
        return cls(
            task_id=data["task_id"],
            party_address=data["party_address"],
            amount=data.get("amount", 0),
            signature=data["signature"],
        )


def _compute_pot_hash(task_id: str, party_address: str, amount: int) -> bytes:
    """Compute the hash that the gateway signs.

    Matches Solidity::

        keccak256(abi.encodePacked(
            keccak256(task_id_str),     # bytes32
            party_address,              # address → 20 bytes
            amount                       # uint256 → 32 bytes big-endian
        ))
    """
    task_id_bytes = keccak(text=task_id)  # bytes32
    party_bytes = to_canonical_address(party_address)  # 20 bytes
    amount_bytes = amount.to_bytes(32, 'big')  # uint256 → 32 bytes big-endian
    return keccak(task_id_bytes + party_bytes + amount_bytes)


class POTManager:
    """Generates, persists, and verifies Proof-of-Task receipts.

    The manager uses two components:
      * An ECDSA signing key (the gateway's private key) for generation.
      * The shared ``Storage`` backend for persistence so PoTs survive
        restarts and can be fetched by workers/developers via the API.
    """

    def __init__(self, storage: Storage, gateway_signing_key: str) -> None:
        self._storage = storage
        self._signing_key = gateway_signing_key

    # ── Generation ──────────────────────────────────────────────────────

    def generate_pot(
        self, task_id: str, party_address: str, amount: int = 0,
    ) -> ProofOfTask:
        """Create and persist a PoT for the given task + party.

        The signature is over ``keccak256(task_id) ++ party_address ++ amount``
        using the gateway's ECDSA key (``Account.unsafe_sign_hash``).
        """
        message_hash = _compute_pot_hash(task_id, party_address, amount)
        signed = Account.unsafe_sign_hash(message_hash, self._signing_key)
        signature = signed.signature.hex()

        pot = ProofOfTask(
            task_id=task_id,
            party_address=party_address,
            amount=amount,
            signature=signature,
        )

        # Persist with compound key (task_id + party_address) so both
        # worker and developer PoTs can coexist.
        key = f"{NS_POT}:{task_id}:{party_address.lower()}"
        self._storage.set(key, json.dumps(pot.to_dict()))
        logger.debug(
            "PoT generated: task=%s party=%s amount=%d sig=%s…",
            task_id, party_address, amount, signature[:16],
        )
        return pot

    # ── Retrieval ───────────────────────────────────────────────────────

    def get_pot(self, task_id: str, party_address: str = "") -> Optional[ProofOfTask]:
        """Retrieve a PoT by task ID and optional party address.

        If ``party_address`` is empty, tries the worker key first (legacy).
        """
        if party_address:
            key = f"{NS_POT}:{task_id}:{party_address.lower()}"
            raw = self._storage.get(key)
            if raw:
                return self._deserialize(raw, task_id)

        # Fallback to bare task_id key (legacy format)
        raw = self._storage.get(f"{NS_POT}:{task_id}")
        if raw:
            return self._deserialize(raw, task_id)
        return None

    @staticmethod
    def _deserialize(raw: str, task_id: str) -> Optional[ProofOfTask]:
        try:
            data = json.loads(raw)
            return ProofOfTask.from_dict(data)
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("Corrupt PoT data for task %s: %s", task_id, exc)
            return None

    # ── Verification ────────────────────────────────────────────────────

    def verify_pot(
        self, pot: ProofOfTask, expected_gateway_address: str,
    ) -> bool:
        """Off-chain verification: recover the signer and compare addresses."""
        try:
            message_hash = _compute_pot_hash(
                pot.task_id, pot.party_address, pot.amount,
            )
            recovered = Account._recover_hash(
                message_hash, signature=pot.signature,
            )
            return recovered.lower() == expected_gateway_address.lower()
        except Exception as exc:
            logger.warning("PoT verification failed: %s", exc)
            return False
