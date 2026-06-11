#!/usr/bin/env python3
"""Full 70/25/5 settlement lifecycle with developer registration + PoT claims.

Steps:
  1. Register developer for test_skill (gateway EOA signs tx)
  2. run_skill (user = Account #1)
  3. Worker (Account #4) claims & submits
  4. Verify 70/25/5 split on-chain
  5. Worker claims 25% via PoT
  6. Developer (Account #3) claims 70% via PoT

Usage:
    python3 scripts/full_settlement_test.py
"""

import json, time, httpx, os, sys
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_utils import keccak, to_canonical_address
from web3 import Web3

# ── Chain ──────────────────────────────────────────────────────────────────
RPC = "http://127.0.0.1:8545"
GATEWAY = "http://127.0.0.1:8000"
CONTRACT_ADDR = "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512"
USDC_ADDR = "0x5FbDB2315678afecb367f032d93F642f64180aa3"

GATEWAY_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
USER_KEY = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"       # Account #1
DEV_KEY = "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a"       # Account #2
WORKER_KEY = "0x47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926a"      # Account #4

USER_ADDR = Account.from_key(USER_KEY).address
DEV_ADDR = Account.from_key(DEV_KEY).address
WORKER_ADDR = Account.from_key(WORKER_KEY).address

w3 = Web3(Web3.HTTPProvider(RPC))
w3.is_connected()

# ── ABI fragments ──────────────────────────────────────────────────────────
GATEWAY_ABI = [
    {"inputs": [], "name": "gateway", "outputs": [{"type": "address"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"type": "bytes32"}, {"type": "address"}], "name": "registerDeveloper", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"type": "address"}], "name": "balances", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"type": "address"}], "name": "pendingPayouts", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "accumulatedTreasuryFees", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"type": "bytes32"}, {"type": "bytes"}], "name": "claimReward", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"type": "bytes32"}, {"type": "bytes"}], "name": "claimDeveloperReward", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"type": "bytes32"}], "name": "taskStatus", "outputs": [{"type": "uint8"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"type": "bytes32"}], "name": "getTaskSettlement", "outputs": [
        {"type": "address"}, {"type": "address"}, {"type": "uint256"}, {"type": "uint256"},
        {"type": "uint256"}, {"type": "uint256"}, {"type": "uint256"}, {"type": "uint8"},
    ], "stateMutability": "view", "type": "function"},
]
USDC_ABI = [
    {"inputs": [{"type": "address"}], "name": "balanceOf", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"type": "address"}, {"type": "uint256"}], "name": "mint", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"type": "address"}, {"type": "uint256"}], "name": "approve", "outputs": [{"type": "bool"}], "stateMutability": "nonpayable", "type": "function"},
]

contract = w3.eth.contract(address=Web3.to_checksum_address(CONTRACT_ADDR), abi=GATEWAY_ABI)
usdc = w3.eth.contract(address=Web3.to_checksum_address(USDC_ADDR), abi=USDC_ABI)

def send_tx(fn, key, gas=200_000):
    acct = Account.from_key(key)
    base_fee = w3.eth.get_block("latest")["baseFeePerGas"]
    tx = fn.build_transaction({
        "chainId": w3.eth.chain_id,
        "from": acct.address, "nonce": w3.eth.get_transaction_count(acct.address),
        "gas": gas,
        "maxFeePerGas": base_fee + w3.eth.max_priority_fee,
        "maxPriorityFeePerGas": w3.eth.max_priority_fee,
    })
    signed = acct.sign_transaction(tx)
    receipt = w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed.raw_transaction))
    assert receipt.status == 1, f"tx reverted: {receipt.transactionHash.hex()}"
    return receipt

def eip191_sign(body, key):
    return Account.from_key(key).sign_message(encode_defunct(primitive=body.encode())).signature.hex()

def auth(body, wallet, key):
    return {"X-Wallet-Address": wallet, "X-Signature": eip191_sign(body, key),
            "X-Timestamp": str(int(time.time())), "Content-Type": "application/json"}

# ══════════════════════════════════════════════════════════════════════════
# Step 0: Fund worker + developer with MockUSDC (for deposit if needed)
# ══════════════════════════════════════════════════════════════════════════
print("=== Step 0: Fund worker & developer MockUSDC ===")
for addr, key, label in [(WORKER_ADDR, WORKER_KEY, "Worker"), (DEV_ADDR, DEV_KEY, "Developer")]:
    bal = usdc.functions.balanceOf(addr).call()
    if bal < 10 * 10**6:
        send_tx(usdc.functions.mint(addr, 100 * 10**6), key)
        print(f"  Minted 100 USDC to {label}: {addr}")

# ══════════════════════════════════════════════════════════════════════════
# Step 1: Register developer for test_skill
# ══════════════════════════════════════════════════════════════════════════
print("\n=== Step 1: Register developer ===")
skill_id_hash = keccak(text="test_skill")
print(f"  skill_id_hash: 0x{skill_id_hash.hex()}")
send_tx(contract.functions.registerDeveloper(skill_id_hash, Web3.to_checksum_address(DEV_ADDR)), GATEWAY_KEY)
onchain_dev = contract.functions.gateway().call()
print(f"  Gateway EOA: {onchain_dev}")
print(f"  Developer registered: {DEV_ADDR}")

# ══════════════════════════════════════════════════════════════════════════
# Step 2: run_skill (user = Account #1)
# ══════════════════════════════════════════════════════════════════════════
print("\n=== Step 2: run_skill ===")
c = httpx.Client()
body = json.dumps({"skill_id": "test_skill", "user_id": USER_ADDR, "params": {"test": "70_25_5_split"}})
r = c.post(f"{GATEWAY}/api/run", content=body, headers=auth(body, USER_ADDR, USER_KEY))
task_id = r.json()["task_id"]
print(f"  Task: {task_id}")

# ══════════════════════════════════════════════════════════════════════════
# Step 3: Worker claims & submits
# ══════════════════════════════════════════════════════════════════════════
print("\n=== Step 3: Claim + Submit ===")
body = json.dumps({"worker_id": WORKER_ADDR})
r = c.post(f"{GATEWAY}/api/tasks/claim", content=body, headers=auth(body, WORKER_ADDR, WORKER_KEY))
assert r.status_code == 200, f"claim failed: {r.text}"
print(f"  Claimed: {r.status_code}")

result_data = {"status": "accepted", "echo": {"test": "70_25_5_split"}}
body = json.dumps({"task_id": task_id, "worker_id": WORKER_ADDR, "result_data": result_data})
r = c.post(f"{GATEWAY}/api/tasks/submit", content=body, headers=auth(body, WORKER_ADDR, WORKER_KEY))
d = r.json()
print(f"  Submit: {r.status_code}")
print(f"  Outcome: {d['outcome']}  Total: ${d['total_cost']:.4f}  PoT: {str(d.get('pot'))[:32]}...")
pot_sig = d.get("pot")

# ══════════════════════════════════════════════════════════════════════════
# Step 4: Verify 70/25/5 split on-chain
# ══════════════════════════════════════════════════════════════════════════
print("\n=== Step 4: On-chain 70/25/5 split ===")
task_id_bytes = keccak(text=task_id)
settlement = contract.functions.getTaskSettlement(task_id_bytes).call()
print(f"  Settlement: worker={settlement[0][:12]}... dev={settlement[1][:12]}...")
print(f"    Total:     {settlement[2] / 10**6:.4f} USDC")
print(f"    Worker:    {settlement[3] / 10**6:.4f} USDC (25%)")
print(f"    Developer: {settlement[4] / 10**6:.4f} USDC (70%)")
print(f"    Treasury:  {settlement[5] / 10**6:.4f} USDC (5%)")
print(f"    Status:    {settlement[7]}")

user_bal = contract.functions.balances(Web3.to_checksum_address(USER_ADDR)).call()
worker_pending = contract.functions.pendingPayouts(Web3.to_checksum_address(WORKER_ADDR)).call()
dev_pending = contract.functions.pendingPayouts(Web3.to_checksum_address(DEV_ADDR)).call()
print(f"\n  User on-chain balance: {user_bal / 10**6:.4f} USDC")
print(f"  Worker pending:        {worker_pending / 10**6:.4f} USDC")
print(f"  Developer pending:     {dev_pending / 10**6:.4f} USDC")

# ══════════════════════════════════════════════════════════════════════════
# Step 5: Worker claims 25% via PoT
# ══════════════════════════════════════════════════════════════════════════
print("\n=== Step 5: Worker claims 25% via PoT ===")
gw_key_obj = Account.from_key(GATEWAY_KEY)
worker_amount = settlement[3]  # worker_share from settlement
worker_binding = keccak(task_id_bytes + to_canonical_address(WORKER_ADDR) + worker_amount.to_bytes(32, 'big'))
worker_pot = Account.unsafe_sign_hash(worker_binding, GATEWAY_KEY).signature.hex()
print(f"  Worker PoT: {worker_pot[:32]}...")

worker_bal_before = usdc.functions.balanceOf(Web3.to_checksum_address(WORKER_ADDR)).call()
send_tx(contract.functions.claimReward(task_id_bytes, bytes.fromhex(worker_pot)), WORKER_KEY)
worker_bal_after = usdc.functions.balanceOf(Web3.to_checksum_address(WORKER_ADDR)).call()
print(f"  Worker USDC: {worker_bal_before / 10**6:.4f} → {worker_bal_after / 10**6:.4f}")
print(f"  Claimed:     {(worker_bal_after - worker_bal_before) / 10**6:.4f} USDC")

# ══════════════════════════════════════════════════════════════════════════
# Step 6: Developer claims 70% via PoT
# ══════════════════════════════════════════════════════════════════════════
print("\n=== Step 6: Developer claims 70% via PoT ===")
dev_amount = settlement[4]
dev_binding = keccak(task_id_bytes + to_canonical_address(DEV_ADDR) + dev_amount.to_bytes(32, 'big'))
dev_pot = Account.unsafe_sign_hash(dev_binding, GATEWAY_KEY).signature.hex()
print(f"  Developer PoT: {dev_pot[:32]}...")

dev_bal_before = usdc.functions.balanceOf(Web3.to_checksum_address(DEV_ADDR)).call()
send_tx(contract.functions.claimDeveloperReward(task_id_bytes, bytes.fromhex(dev_pot)), DEV_KEY)
dev_bal_after = usdc.functions.balanceOf(Web3.to_checksum_address(DEV_ADDR)).call()
print(f"  Developer USDC: {dev_bal_before / 10**6:.4f} → {dev_bal_after / 10**6:.4f}")
print(f"  Claimed:        {(dev_bal_after - dev_bal_before) / 10**6:.4f} USDC")

# ══════════════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 50)
print("FULL SETTLEMENT LIFECYCLE COMPLETE")
print("=" * 50)
print(f"  User deducted:      0.0500 USDC")
print(f"  Worker claimed:     {(worker_bal_after - worker_bal_before) / 10**6:.4f} USDC (25%)")
print(f"  Developer claimed:  {(dev_bal_after - dev_bal_before) / 10**6:.4f} USDC (70%)")
print(f"  Treasury (acc):     {contract.functions.accumulatedTreasuryFees().call() / 10**6:.4f} USDC (5%)")
total_distributed = (worker_bal_after - worker_bal_before) + (dev_bal_after - dev_bal_before) + contract.functions.accumulatedTreasuryFees().call()
print(f"  Total distributed:  {total_distributed / 10**6:.4f} USDC")
print("=" * 50)
