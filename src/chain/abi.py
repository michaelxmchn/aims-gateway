"""Contract ABI fragments, addresses, and constants for the AIMS Settlement contract.

In production, deploy ``contracts/AIMS_Settlement.sol`` with a Solidity
compiler and copy the generated ABI here.  The fragment below covers all
functions the gateway uses.  For a full ABI use a compilation artifact.
"""

from __future__ import annotations

import os

# ── USDC ─────────────────────────────────────────────────────────────────────

USDC_DECIMALS: int = 6  # USDC uses 6 decimal places on most chains (incl. Base)

# ── Contract addresses ───────────────────────────────────────────────────────

# Default to a sentinel that signals "use mock" during local development.
AIMS_CONTRACT_ADDRESS: str = os.getenv(
    "AIMS_CONTRACT_ADDRESS",
    "0x0000000000000000000000000000000000000001",
)

USDC_ADDRESS: str = os.getenv("USDC_ADDRESS", "")

# ── Minimal ABI for the gateway's interaction with AIMSSettlement ────────────
# Functions the gateway calls directly: balanceOf, settleTask, deposit,
# claimReward, claimOwnerFees, and the view functions.

AIMS_SETTLEMENT_ABI: list[dict] = [
    # ── view ──
    {
        "inputs": [{"name": "", "type": "address"}],
        "name": "balances",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "", "type": "address"}],
        "name": "pendingPayouts",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "", "type": "uint256"}],
        "name": "usedNonces",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "", "type": "bytes32"}],
        "name": "settledTasks",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "", "type": "bytes32"}],
        "name": "claimedTasks",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "gateway",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    # ── write ──
    {
        "inputs": [{"name": "amount", "type": "uint256"}],
        "name": "deposit",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "taskId", "type": "bytes32"},
            {"name": "user", "type": "address"},
            {"name": "worker", "type": "address"},
            {"name": "amount", "type": "uint256"},
            {"name": "nonce", "type": "uint256"},
        ],
        "name": "settleTask",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "taskId", "type": "bytes32"},
            {"name": "gatewaySignature", "type": "bytes"},
        ],
        "name": "claimReward",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]
