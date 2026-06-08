"""Chain Settlement — Layer 0.

Interface to the Base smart contract for batch settlement.
Maps to the two on-chain operations:
  ① submit_batch — counter +1, transfer points
  ② query_balance — read current balance

Also manages the user_identity_map (email → wallet address mapping)
and the Stripe fiat on-ramp webhook stub.

For MVP this is a stub that logs the intended transaction.
Real implementation requires web3.py + deployed contract on Base.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class SettlementReceipt:
    """Result of a batch submission to the chain."""

    tx_hash: str
    block_number: int
    record_count: int


# ── User Identity Map ──────────────────────────────────────────────────────


@dataclass
class UserIdentity:
    """Maps a user's email/identity to their on-chain wallet and session."""

    email: str
    wallet_address: str = ""
    session_key_id: str = ""
    registered_at: float = field(default_factory=time.time)


class ChainSettlement:
    """Interface to the AIMS settlement contract on Base.

    Maintains a ``user_identity_map`` (email → wallet) for fiat on-ramp
    flow and session-to-wallet binding.
    """

    def __init__(self, rpc_url: str, contract_addr: Optional[str] = None) -> None:
        self._rpc_url = rpc_url
        self._contract_addr = contract_addr
        self._user_identity_map: Dict[str, UserIdentity] = {}

    # ── Identity Map ────────────────────────────────────────────────────

    def register_identity(self, email: str, wallet_address: str = "",
                          session_key_id: str = "") -> UserIdentity:
        """Register or retrieve a user identity (email → wallet binding)."""
        if email in self._user_identity_map:
            existing = self._user_identity_map[email]
            if wallet_address:
                existing.wallet_address = wallet_address
            if session_key_id:
                existing.session_key_id = session_key_id
            return existing

        identity = UserIdentity(
            email=email,
            wallet_address=wallet_address,
            session_key_id=session_key_id,
        )
        self._user_identity_map[email] = identity
        logger.info(
            "IDENTITY registered: email=%s wallet=%s session=%s",
            email, wallet_address, session_key_id,
        )
        return identity

    def get_identity(self, email: str) -> Optional[UserIdentity]:
        """Look up a user identity by email."""
        return self._user_identity_map.get(email)

    def resolve_wallet(self, email: str) -> str:
        """Resolve an email to a wallet address, or empty if unknown."""
        identity = self._user_identity_map.get(email)
        return identity.wallet_address if identity else ""

    @property
    def identity_count(self) -> int:
        return len(self._user_identity_map)

    # ── Stripe Fiat On-Ramp Stub ────────────────────────────────────────

    def simulate_stripe_webhook(self, email: str, usdt_amount: float,
                                 ledger: Any) -> Dict[str, Any]:
        """Simulate a Stripe payment webhook — fiat → USDT on-ramp.

        In production, Stripe sends a ``payment_intent.succeeded`` event
        to a webhook endpoint after the user completes checkout. This stub
        seeds the user's MockLedger balance with USDT.

        Returns a structured event payload mimicking Stripe's format.
        """
        identity = self.register_identity(email)
        wallet = identity.wallet_address or f"0x{email.encode('utf-8').hex()[:40]}"

        ledger.seed_usdt(email, usdt_amount)

        event = {
            "id": f"evt_{int(time.time())}",
            "type": "payment_intent.succeeded",
            "created": int(time.time()),
            "data": {
                "object": {
                    "id": f"pi_{int(time.time())}",
                    "amount": int(usdt_amount * 100),  # cents
                    "currency": "usd",
                    "status": "succeeded",
                    "metadata": {"email": email},
                },
            },
        }

        logger.info(
            "STRIPE WEBHOOK [SIMULATED] → %s +$%.2f USDT  (wallet=%s  event=%s)",
            email, usdt_amount, wallet, event["id"],
        )
        return event

    # ── Chain Operations (stubs) ───────────────────────────────────────

    def submit_batch(
        self,
        merkle_root: bytes,
        record_count: int,
    ) -> SettlementReceipt:
        """Submit a Merkle root + count to the chain contract.

        MVP stub: logs and returns a mock receipt. Real implementation
        calls contract.submitBatch(bytes32 merkleRoot, uint256 count).
        """
        logger.info(
            "[STUB] submit_batch: root=%s count=%d contract=%s",
            merkle_root.hex()[:16],
            record_count,
            self._contract_addr,
        )
        # TODO: web3 contract interaction
        return SettlementReceipt(
            tx_hash=f"0x{merkle_root.hex()[:32]}",
            block_number=0,
            record_count=record_count,
        )

    def query_balance(self, address: str) -> int:
        """Query the point balance for an address.

        MVP stub: returns 0. Real implementation calls
        contract.balances(address).
        """
        # TODO: web3 contract interaction
        return 0
