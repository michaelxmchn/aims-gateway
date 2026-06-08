"""Chain Settlement — Layer 0.

Interface to the Base smart contract for batch settlement.
Maps to the two on-chain operations:
  ① submit_batch — counter +1, transfer points
  ② query_balance — read current balance

For MVP this is a stub that logs the intended transaction.
Real implementation requires web3.py + deployed contract on Base.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SettlementReceipt:
    """Result of a batch submission to the chain."""

    tx_hash: str
    block_number: int
    record_count: int


class ChainSettlement:
    """Interface to the AIMS settlement contract on Base."""

    def __init__(self, rpc_url: str, contract_addr: Optional[str] = None) -> None:
        self._rpc_url = rpc_url
        self._contract_addr = contract_addr

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
