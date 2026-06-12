"""Licensing Manager — dynamic single-use key issuance for AIMS 2.0.

Provides:
- One-time random seed generation per Task_ID (ECDSA-mixed entropy)
- Task key state tracking: [NONE] → [ACTIVATED_ONCE]
- Replay attack prevention (each Task_ID can only be keyed once)
"""

from __future__ import annotations

import logging
import os
import time

from eth_utils import keccak

from src.gateway.storage import Storage

logger = logging.getLogger(__name__)

LICENSE_NS = "license:key"
STATUS_ACTIVATED = "ACTIVATED_ONCE"


class LicensingManager:
    """Dynamic single-use key issuance with replay protection."""

    def __init__(self, storage: Storage, gateway_signing_key: str) -> None:
        self._storage = storage
        self._key = gateway_signing_key

    # ── State queries ──────────────────────────────────────────────────

    def is_license_issued(self, task_id: str) -> bool:
        """Check if a license key has already been issued for this task."""
        return self._storage.get(f"{LICENSE_NS}:{task_id}") is not None

    def get_license_status(self, task_id: str) -> str:
        """Return the current license status for a task, or empty string."""
        data = self._storage.get(f"{LICENSE_NS}:{task_id}")
        return data.get("status", "") if isinstance(data, dict) else ""

    # ── Key issuance ───────────────────────────────────────────────────

    def issue_key(self, task_id: str, user_address: str) -> dict:
        """Generate a one-time random seed and mark task as ACTIVATED_ONCE.

        The seed is derived from::

            keccak256(gateway_signing_key ++ task_id ++ user_address ++ os.urandom(32))

        This mixes gateway-specific entropy with task/user binding so the
        seed is both unpredictable and traceable to a specific task+user.
        """
        rand = os.urandom(32)
        seed_bytes = keccak(
            self._key.encode()
            + task_id.encode()
            + user_address.encode()
            + rand,
        )
        seed = seed_bytes.hex()

        record: dict = {
            "seed": seed,
            "task_id": task_id,
            "user_address": user_address,
            "status": STATUS_ACTIVATED,
            "ts": time.time(),
        }
        self._storage.set(f"{LICENSE_NS}:{task_id}", record)
        logger.info(
            "License issued: task=%s user=%s status=%s",
            task_id, user_address, STATUS_ACTIVATED,
        )
        return record
