"""Wallet / Session Key Manager — Layer 0.

Manages ERC-4337/EIP-7702 embedded wallet and Session Keys.
Session Keys give the AI agent scoped auto-signing capability —
without them, every skill execution would require a wallet popup.
"""

from __future__ import annotations

import time
import uuid
import logging
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SessionKey:
    """A scoped auto-signing key granted to the AI agent."""

    key_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    scopes: List[str] = field(default_factory=list)
    expiry: float = 0.0
    revoked: bool = False

    @property
    def is_valid(self) -> bool:
        return not self.revoked and time.time() < self.expiry


class SessionKeyManager:
    """Creates, caches, and revokes session keys."""

    def __init__(self) -> None:
        self._keys: dict[str, SessionKey] = {}

    def create(self, scopes: List[str], ttl_seconds: int = 3600) -> SessionKey:
        key = SessionKey(
            scopes=scopes,
            expiry=time.time() + ttl_seconds,
        )
        self._keys[key.key_id] = key
        logger.info("Session key created: id=%s scopes=%s expires=%s", key.key_id, scopes, key.expiry)
        return key

    def revoke(self, key_id: str) -> bool:
        key = self._keys.get(key_id)
        if key is None:
            return False
        key.revoked = True
        logger.info("Session key revoked: id=%s", key_id)
        return True

    def is_valid(self, key_id: str) -> bool:
        key = self._keys.get(key_id)
        if key is None:
            return False
        return key.is_valid
