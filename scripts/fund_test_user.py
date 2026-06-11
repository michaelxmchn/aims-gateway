#!/usr/bin/env python3
"""Fund a test user with MockUSDC and deposit into AIMSAgentGateway.

Usage:
    python3 scripts/fund_test_user.py

This script:
  1. Mints MockUSDC to the test user
  2. Approves the AIMSAgentGateway contract
  3. Deposits into the contract

Uses Hardhat Account #1 as the test user (known dev key).
"""

import os
import sys

from eth_account import Account
from web3 import Web3

# ── Configuration ──────────────────────────────────────────────────────────
RPC_URL = "http://127.0.0.1:8545"
CONTRACT_ADDRESS = os.getenv("AIMS_CONTRACT_ADDRESS", "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512")
USDC_ADDRESS = os.getenv("AIMS_USDC_ADDRESS", "0x5FbDB2315678afecb367f032d93F642f64180aa3")

# Hardhat Account #1 — test user
USER_PRIVATE_KEY = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
DEPOSIT_AMOUNT = 10 * 10**6  # 10.0 USDC (6 decimals)
MINT_AMOUNT = 100 * 10**6    # 100.0 USDC

# MockERC20 ABI (minimal: mint, approve, balanceOf, decimals)
MOCK_ERC20_ABI = [
    {"inputs": [{"name": "to", "type": "address"}, {"name": "amount", "type": "uint256"}], "name": "mint", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"name": "spender", "type": "address"}, {"name": "amount", "type": "uint256"}], "name": "approve", "outputs": [{"name": "", "type": "bool"}], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"name": "account", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "stateMutability": "view", "type": "function"},
]

# AIMSAgentGateway ABI (minimal: deposit)
GATEWAY_ABI = [
    {"inputs": [{"name": "amount", "type": "uint256"}], "name": "deposit", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"name": "", "type": "address"}], "name": "balances", "outputs": [{"name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
]


def main():
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    if not w3.is_connected():
        print("ERROR: Cannot connect to Hardhat node at", RPC_URL)
        sys.exit(1)

    user_acct = Account.from_key(USER_PRIVATE_KEY)
    user_addr = user_acct.address
    print(f"Test user address: {user_addr}")

    mock_usdc = w3.eth.contract(address=Web3.to_checksum_address(USDC_ADDRESS), abi=MOCK_ERC20_ABI)
    gateway = w3.eth.contract(address=Web3.to_checksum_address(CONTRACT_ADDRESS), abi=GATEWAY_ABI)

    # 1. Check existing balance
    existing = mock_usdc.functions.balanceOf(user_addr).call()
    print(f"Current MockUSDC balance: {existing / 10**6:.2f}")

    if existing < MINT_AMOUNT:
        # Mint MockUSDC to user
        mint_tx = mock_usdc.functions.mint(user_addr, MINT_AMOUNT).build_transaction({
            "from": user_addr,
            "nonce": w3.eth.get_transaction_count(user_addr),
            "gas": 100_000,
            "maxPriorityFeePerGas": w3.eth.max_priority_fee,
        })
        signed = user_acct.sign_transaction(mint_tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt.status != 1:
            print("ERROR: Mint tx failed")
            sys.exit(1)
        print(f"Minted {MINT_AMOUNT / 10**6:.2f} MockUSDC (tx: {tx_hash.hex()[:42]}...)")

    # 2. Approve gateway contract
    approve_tx = mock_usdc.functions.approve(
        Web3.to_checksum_address(CONTRACT_ADDRESS), MINT_AMOUNT
    ).build_transaction({
        "from": user_addr,
        "nonce": w3.eth.get_transaction_count(user_addr),
        "gas": 100_000,
        "maxPriorityFeePerGas": w3.eth.max_priority_fee,
    })
    signed = user_acct.sign_transaction(approve_tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    if receipt.status != 1:
        print("ERROR: Approve tx failed")
        sys.exit(1)
    print(f"Approved contract to spend MockUSDC (tx: {tx_hash.hex()[:42]}...)")

    # 3. Deposit into gateway contract
    deposit_tx = gateway.functions.deposit(DEPOSIT_AMOUNT).build_transaction({
        "from": user_addr,
        "nonce": w3.eth.get_transaction_count(user_addr),
        "gas": 100_000,
        "maxPriorityFeePerGas": w3.eth.max_priority_fee,
    })
    signed = user_acct.sign_transaction(deposit_tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    if receipt.status != 1:
        print("ERROR: Deposit tx failed")
        sys.exit(1)
    print(f"Deposited {DEPOSIT_AMOUNT / 10**6:.2f} USDC into contract (tx: {tx_hash.hex()[:42]}...)")

    # 4. Verify deposit
    onchain_balance = gateway.functions.balances(user_addr).call()
    print(f"On-chain balance: {onchain_balance / 10**6:.6f} USDC")
    assert onchain_balance >= DEPOSIT_AMOUNT, "Deposit verification failed!"

    print("\n✓ Test user funded successfully!")
    print(f"  Address: {user_addr}")
    print(f"  Private key: {USER_PRIVATE_KEY}")
    print(f"  Balance: {onchain_balance / 10**6:.6f} USDC")


if __name__ == "__main__":
    main()
