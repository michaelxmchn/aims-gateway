"""Canary watermark — anti-piracy middleware for task settlement.

Generates an ECDSA-signed ``_canary_token`` per task (timestamp + random hash),
injected into the task payload at publish time.  On submission, the gateway
verifies the token is present, correctly signed, and not replayed.

Piracy detection flow:
  MISSING_CANARY_TOKEN   → result_data has no ``_canary_token``
  CANARY_TOKEN_MISMATCH  → token value doesn't match what was issued
  CANARY_BAD_SIGNATURE   → ECDSA recover doesn't match gateway address
  CANARY_REPLAY_ATTACK   → same task_id submitted twice with valid token

On any failure the worker is blacklisted and settlement is blocked with
outcome ``FORBIDDEN_PIRACY``.
"""

from __future__ import annotations

import logging
import os
import time

from eth_account import Account
from eth_utils import keccak

from src.gateway.storage import Storage

logger = logging.getLogger(__name__)

CANARY_TOKEN_NS = "canary:token"
CANARY_USED_NS = "canary:used"
CANARY_BLACKLIST_NS = "canary:blacklist"


class CanaryManager:
    """ECDSA-signed watermark generation, verification, and replay protection."""

    def __init__(
        self,
        storage: Storage,
        gateway_signing_key: str,
        gateway_address: str = "",
    ) -> None:
        self._storage = storage
        self._key = gateway_signing_key
        # Derive gateway address from key if not explicitly provided
        if not gateway_address and gateway_signing_key:
            acct = Account.from_key(gateway_signing_key)
            self._gateway_address = acct.address
        else:
            self._gateway_address = gateway_address

    # ── Token generation ──────────────────────────────────────────────────

    def generate_token(self) -> str:
        """Produce an ECDSA-signed canary token.

        Format: ``canary:<timestamp_ms>:<random_hex>:<hex_signature>``

        The signature is over ``keccak256("canary:<ts>:<rand>")`` using
        the gateway's private key, so the gateway address can verify it.
        """
        ts = int(time.time() * 1000)
        rand = os.urandom(16).hex()
        payload = f"canary:{ts}:{rand}"
        payload_hash = keccak(text=payload)
        signed = Account.unsafe_sign_hash(payload_hash, self._key)
        return f"{payload}:{signed.signature.hex()}"

    def record_task(self, task_id: str, token: str) -> None:
        """Persist the canary token issued for *task_id*."""
        self._storage.set(f"{CANARY_TOKEN_NS}:{task_id}", token)
        logger.debug("Canary recorded: task=%s token=…%s", task_id, token[-16:])

    # ── Verification ──────────────────────────────────────────────────────

    def verify_token(self, task_id: str, result_data: dict) -> dict:
        """Verify ``_canary_token`` in *result_data*.

        Returns ``{"valid": True, "reason": ""}`` on success, or
        ``{"valid": False, "reason": "<REASON>"}`` on failure.
        """
        stored = self._storage.get(f"{CANARY_TOKEN_NS}:{task_id}")
        if not stored:
            # Task was published before canary system was active — allow.
            return {"valid": True, "reason": "NO_CANARY_ISSUED"}

        submitted = result_data.get("_canary_token", "")
        if not submitted:
            return {"valid": False, "reason": "MISSING_CANARY_TOKEN"}

        if submitted != stored:
            return {"valid": False, "reason": "CANARY_TOKEN_MISMATCH"}

        # Verify ECDSA signature
        parts = stored.rsplit(":", 1)
        if len(parts) != 2:
            return {"valid": False, "reason": "CANARY_TOKEN_MALFORMED"}

        payload, sig = parts
        payload_hash = keccak(text=payload)
        try:
            recovered = Account._recover_hash(payload_hash, signature=sig)
            if recovered.lower() != self._gateway_address.lower():
                return {"valid": False, "reason": "CANARY_BAD_SIGNATURE"}
        except Exception as exc:
            return {"valid": False, "reason": f"CANARY_VERIFY_FAILED:{exc}"}

        # Replay protection — one-use per task_id
        used_key = f"{CANARY_USED_NS}:{task_id}"
        if self._storage.get(used_key):
            return {"valid": False, "reason": "CANARY_REPLAY_ATTACK"}

        self._storage.set(used_key, True)
        return {"valid": True, "reason": ""}

    # ── Worker blacklist ──────────────────────────────────────────────────

    def blacklist_worker(self, worker_id: str) -> None:
        """Permanently blacklist a worker for piracy."""
        self._storage.set(f"{CANARY_BLACKLIST_NS}:{worker_id}", True)
        logger.warning("CANARY_BLACKLIST: worker=%s", worker_id)

    def is_blacklisted(self, worker_id: str) -> bool:
        """Check if a worker has been blacklisted for piracy."""
        return bool(self._storage.get(f"{CANARY_BLACKLIST_NS}:{worker_id}", False))
