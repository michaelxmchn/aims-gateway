"""Wallet / Session Key Manager — Layer 0.

Manages ERC-4337/EIP-7702 embedded wallet and Session Keys.
Session Keys give the AI agent scoped auto-signing capability —
without them, every skill execution would require a wallet popup.

Uses ECDSA key pairs (``eth_account.Account.create()``) for wallet
identity rather than UUID-based session keys.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from eth_account import Account
from eth_account.signers.local import LocalAccount

from src.chain.eip712 import sign_eip712_message

logger = logging.getLogger(__name__)


@dataclass
class Wallet:
    """An ECDSA wallet with address + private key.

    Created via ``Wallet.generate()`` for ephemeral dev wallets or
    ``Wallet.from_key(private_key)`` for imported keys.
    """

    address: str
    private_key: str

    @classmethod
    def generate(cls) -> Wallet:
        acct: LocalAccount = Account.create()
        return cls(address=acct.address, private_key=acct.key.hex())

    @classmethod
    def from_key(cls, private_key: str) -> Wallet:
        acct: LocalAccount = Account.from_key(private_key)
        return cls(address=acct.address, private_key=acct.key.hex())

    def sign_typed_data(
        self,
        types: dict[str, list[dict[str, str]]],
        domain: dict[str, Any],
        value: dict[str, Any],
    ) -> str:
        """Sign an EIP-712 typed data message with this wallet's key.

        Returns the hex-encoded signature string.
        """
        return sign_eip712_message(self.private_key, types, domain, value)


@dataclass
class SessionKey:
    """A scoped auto-signing key granted to the AI agent."""

    key_id: str
    wallet: Wallet
    scopes: list[str] = field(default_factory=list)
    expiry: float = 0.0
    revoked: bool = False

    @property
    def is_valid(self) -> bool:
        return not self.revoked and time.time() < self.expiry


class SessionKeyManager:
    """Creates, caches, and revokes session keys backed by ECDSA wallets."""

    def __init__(self) -> None:
        self._keys: dict[str, SessionKey] = {}

    def create(self, scopes: list[str], ttl_seconds: int = 3600) -> SessionKey:
        wallet = Wallet.generate()
        key = SessionKey(
            key_id=wallet.address,
            wallet=wallet,
            scopes=scopes,
            expiry=time.time() + ttl_seconds,
        )
        self._keys[key.key_id] = key
        logger.info(
            "Session key created: id=%s scopes=%s expires=%s",
            key.key_id, scopes, key.expiry,
        )
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
