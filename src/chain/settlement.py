"""Chain Settlement — Layer 0.

Interface to the AIMS Agent Gateway contract on Base.
Provides the ``contract`` property that lazily initialises either an
``InMemorySettlementContract`` (local dev / testing) or a
``Web3SettlementContract`` (production) based on environment variables.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from src.chain.contract_client import (
    InMemorySettlementContract,
    SettlementContractClient,
    Web3SettlementContract,
)

logger = logging.getLogger(__name__)


@dataclass
class SettlementReceipt:
    """Result of a batch submission to the chain."""

    tx_hash: str
    block_number: int
    record_count: int


@dataclass
class UserIdentity:
    """Maps a user's email/identity to their on-chain wallet."""

    email: str
    wallet_address: str = ""
    registered_at: float = field(default_factory=time.time)


class ChainSettlement:
    """Interface to the AIMS Agent Gateway contract on Base.

    Maintains a ``user_identity_map`` for convenience.
    """

    def __init__(self, rpc_url: str, contract_addr: Optional[str] = None) -> None:
        self._rpc_url = rpc_url
        self._contract_addr = contract_addr
        self._user_identity_map: Dict[str, UserIdentity] = {}
        self._contract: Optional[SettlementContractClient] = None

    # ── Contract Client (lazy-init) ─────────────────────────────────────

    @property
    def contract(self) -> SettlementContractClient:
        """Lazily-initialised settlement contract client.

        Uses ``InMemorySettlementContract`` when ``AIMS_CONTRACT_ADDRESS``
        is the sentinel value (``0x0...01``), otherwise uses
        ``Web3SettlementContract`` with the configured RPC and gateway key.
        """
        if self._contract is not None:
            return self._contract

        contract_addr = self._contract_addr or os.getenv(
            "AIMS_CONTRACT_ADDRESS",
            "0x0000000000000000000000000000000000000001",
        )
        gateway_key = os.getenv("AIMS_GATEWAY_PRIVATE_KEY", "")
        treasury = os.getenv("AIMS_TREASURY", "")

        # Sentinel address → in-memory mock
        if contract_addr == "0x0000000000000000000000000000000000000001":
            gateway_address = "0xGateway000000000000000000000000000000000001"
            if gateway_key:
                from eth_account import Account
                gateway_address = Account.from_key(gateway_key).address

            self._contract = InMemorySettlementContract(
                gateway_address=gateway_address,
                treasury=treasury or "0xTreasury00000000000000000000000000000000001",
            )
            logger.info(
                "Using InMemorySettlementContract (gateway=%s treasury=%s)",
                gateway_address, treasury,
            )
        else:
            self._contract = Web3SettlementContract(
                rpc_url=self._rpc_url,
                contract_address=contract_addr,
                gateway_private_key=gateway_key,
                treasury=treasury,
            )
            logger.info(
                "Using Web3SettlementContract (contract=%s)", contract_addr,
            )

        return self._contract

    # ── Identity Map ────────────────────────────────────────────────────

    def register_identity(self, email: str, wallet_address: str = "") -> UserIdentity:
        """Register or retrieve a user identity (email → wallet binding)."""
        if email in self._user_identity_map:
            existing = self._user_identity_map[email]
            if wallet_address:
                existing.wallet_address = wallet_address
            return existing

        identity = UserIdentity(email=email, wallet_address=wallet_address)
        self._user_identity_map[email] = identity
        logger.info("IDENTITY registered: email=%s wallet=%s", email, wallet_address)
        return identity

    def get_identity(self, email: str) -> Optional[UserIdentity]:
        return self._user_identity_map.get(email)

    def resolve_wallet(self, email: str) -> str:
        identity = self._user_identity_map.get(email)
        return identity.wallet_address if identity else ""

    @property
    def identity_count(self) -> int:
        return len(self._user_identity_map)

    # ── Chain Operations (stubs) ────────────────────────────────────────

    def submit_batch(
        self, merkle_root: bytes, record_count: int,
    ) -> SettlementReceipt:
        """Submit a Merkle root + count to the chain contract.  MVP stub."""
        logger.info(
            "[STUB] submit_batch: root=%s count=%d",
            merkle_root.hex()[:16], record_count,
        )
        return SettlementReceipt(
            tx_hash=f"0x{merkle_root.hex()[:32]}",
            block_number=0,
            record_count=record_count,
        )

    def query_balance(self, address: str) -> int:
        """Query the deposited balance via the contract client."""
        return self.contract.get_user_balance(address)
