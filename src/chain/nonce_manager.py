"""Per-address monotonic nonce tracking.

Nonces prevent replay attacks by ensuring each signed message can only be
processed once.  The manager stores the *next expected nonce* for each
address in the shared ``Storage`` backend, so state survives restarts.
"""

from __future__ import annotations

import logging

from src.gateway.storage import Storage

logger = logging.getLogger(__name__)

NS_NONCE = "chain:nonce"


class NonceManager:
    """Per-address monotonic nonce tracking.

    Nonces start at ``0`` and MUST strictly increment by 1 each time.
    The manager transparently handles both Redis and in-memory ``Storage``.
    """

    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    # ── Query ────────────────────────────────────────────────────────────────

    def get_next_nonce(self, address: str) -> int:
        """Return the next expected nonce for *address*.

        Returns ``0`` if no nonce has ever been consumed for this address.
        """
        addr = address.lower()
        val = self._storage.dict_get(NS_NONCE, addr, 0)
        return int(val)

    def has_nonce_been_used(self, address: str, nonce: int) -> bool:
        """Check whether a specific nonce has already been consumed."""
        addr = address.lower()
        current = self.get_next_nonce(addr)
        return nonce < current

    # ── Mutation ─────────────────────────────────────────────────────────────

    def mark_used(self, address: str, nonce: int) -> None:
        """Advance the nonce counter to ``nonce + 1``.

        Only advances if ``nonce == current`` — stale nonces are silently
        ignored (caller should check ``has_nonce_been_used`` first).
        """
        addr = address.lower()
        current = self.get_next_nonce(addr)
        if nonce == current:
            self._storage.dict_set(NS_NONCE, addr, current + 1)
            logger.debug("Nonce consumed: %s → %d", addr, nonce)
        else:
            logger.warning(
                "Stale nonce for %s: got %d, expected %d", addr, nonce, current
            )

    def consume(self, address: str) -> int:
        """Atomically get the current nonce and increment it.

        Returns the nonce that was consumed (before increment).
        """
        addr = address.lower()
        current = self.get_next_nonce(addr)
        self._storage.dict_set(NS_NONCE, addr, current + 1)
        logger.debug("Nonce consumed: %s → %d", addr, current)
        return current
