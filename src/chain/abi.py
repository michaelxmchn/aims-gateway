"""Contract ABI, addresses, and constants for the AIMS Agent Gateway contract.

Provides the ABI fragment for ``AIMSAgentGateway.sol`` plus USDC constants.
In production, deploy ``contracts/AIMSAgentGateway.sol`` and paste the
full compilation ABI here.  The fragment below covers all functions the
gateway and workers call.
"""

from __future__ import annotations

import json
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

# ── Settlement split (mirrors Solidity constants) ────────────────────────────

BPS_DENOM = 10_000
DEVELOPER_BPS = 7_000   # 70 %
WORKER_BPS = 2_500       # 25 %
TREASURY_BPS = 500       # 5 %

# ── Full ABI for AIMSAgentGateway ────────────────────────────────────────────

AIMS_AGENT_GATEWAY_ABI: list[dict] = [
    # ── events ──
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "taskId", "type": "bytes32"},
            {"indexed": True, "name": "skillIdHash", "type": "bytes32"},
            {"indexed": True, "name": "consumer", "type": "address"},
            {"indexed": False, "name": "worker", "type": "address"},
            {"indexed": False, "name": "totalAmount", "type": "uint256"},
            {"indexed": False, "name": "workerShare", "type": "uint256"},
            {"indexed": False, "name": "developerShare", "type": "uint256"},
            {"indexed": False, "name": "treasuryShare", "type": "uint256"},
        ],
        "name": "TaskSettled",
        "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "taskId", "type": "bytes32"},
            {"indexed": True, "name": "consumer", "type": "address"},
            {"indexed": False, "name": "amount", "type": "uint256"},
            {"indexed": False, "name": "reason", "type": "string"},
        ],
        "name": "TaskRefunded",
        "type": "event",
    },
    # ── view ──
    {
        "inputs": [{"name": "", "type": "address"}],
        "name": "balances",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "user", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "", "type": "bytes32"}],
        "name": "taskStatus",
        "outputs": [{"name": "", "type": "uint8"}],
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
        "inputs": [],
        "name": "accumulatedTreasuryFees",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "", "type": "bytes32"}],
        "name": "usedCompoundNonces",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "skillIdHash", "type": "bytes32"}],
        "name": "developers",
        "outputs": [{"name": "", "type": "address"}],
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
    {
        "inputs": [{"name": "skillIdHash", "type": "bytes32"}],
        "name": "getDeveloper",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "taskId", "type": "bytes32"}],
        "name": "getTaskSettlement",
        "outputs": [
            {"name": "worker", "type": "address"},
            {"name": "developer", "type": "address"},
            {"name": "totalAmount", "type": "uint256"},
            {"name": "workerShare", "type": "uint256"},
            {"name": "developerShare", "type": "uint256"},
            {"name": "treasuryShare", "type": "uint256"},
            {"name": "settledAt", "type": "uint256"},
            {"name": "status", "type": "uint8"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "nonce", "type": "uint256"}, {"name": "taskId", "type": "bytes32"}],
        "name": "isCompoundNonceUsed",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "party", "type": "address"}],
        "name": "getPendingPayout",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "getTreasuryFees",
        "outputs": [{"name": "", "type": "uint256"}],
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
        "inputs": [{"name": "amount", "type": "uint256"}],
        "name": "withdraw",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "skillIdHash", "type": "bytes32"},
            {"name": "developer", "type": "address"},
        ],
        "name": "registerDeveloper",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "taskId", "type": "bytes32"},
            {"name": "user", "type": "address"},
            {"name": "worker", "type": "address"},
            {"name": "skillIdHash", "type": "bytes32"},
            {"name": "totalAmount", "type": "uint256"},
            {"name": "nonce", "type": "uint256"},
            {"name": "deadline", "type": "uint256"},
            {"name": "gatewaySignature", "type": "bytes"},
        ],
        "name": "settleTask",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "taskId", "type": "bytes32"},
            {"name": "user", "type": "address"},
            {"name": "amount", "type": "uint256"},
            {"name": "reason", "type": "string"},
        ],
        "name": "refundTask",
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
    {
        "inputs": [
            {"name": "taskId", "type": "bytes32"},
            {"name": "gatewaySignature", "type": "bytes"},
        ],
        "name": "claimDeveloperReward",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "claimTreasuryFees",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"name": "newGateway", "type": "address"}],
        "name": "setGateway",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]
