#!/usr/bin/env python3
"""End-to-end Web3 settlement test for AIMS Gateway.

Tests: run_skill → claim → execute → submit → on-chain settlement.

Usage:
    python3 scripts/e2e_web3_test.py
"""

import json
import time
import httpx
from eth_account import Account
from eth_account.messages import encode_defunct

# ── Configuration ──────────────────────────────────────────────────────────
GATEWAY_URL = "http://127.0.0.1:8000"

# Hardhat Account #1 — Test User (has 10 USDC deposited on-chain)
USER_KEY = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
USER_ADDR = Account.from_key(USER_KEY).address

# Hardhat Account #2 — Worker
WORKER_KEY = "0x5de4111afa1a4b94908f83103eb1f15f0f8b1c7e3f5d8e8e3b7c5e8f4e2d8b0"
WORKER_ADDR = Account.from_key(WORKER_KEY).address

print(f"User address:   {USER_ADDR}")
print(f"Worker address: {WORKER_ADDR}")


def eip191_sign(body: str, key: str) -> str:
    """Sign body with EIP-191 personal_sign."""
    msg = encode_defunct(primitive=body.encode())
    signed = Account.from_key(key).sign_message(msg)
    return signed.signature.hex()


def auth_headers(body: str, wallet: str, key: str) -> dict:
    """Build EIP-191 auth headers."""
    return {
        "X-Wallet-Address": wallet,
        "X-Signature": eip191_sign(body, key),
        "X-Timestamp": str(int(time.time())),
        "Content-Type": "application/json",
    }


# ── Step 1: run_skill ─────────────────────────────────────────────────────
print("\n=== Step 1: run_skill ===")
body = json.dumps({
    "skill_id": "test_skill",
    "user_id": USER_ADDR,
    "params": {"test": "hello_web3"},
})
headers = auth_headers(body, USER_ADDR, USER_KEY)

with httpx.Client() as client:
    r = client.post(f"{GATEWAY_URL}/api/run", content=body, headers=headers)
    print(f"Status: {r.status_code}")
    if r.status_code != 200:
        print(f"Error: {r.text}")
        exit(1)
    data = r.json()
    task_id = data["task_id"]
    print(f"Task created: {task_id}")

# ── Step 2: Verify task is PENDING ────────────────────────────────────────
print("\n=== Step 2: Check task status ===")
with httpx.Client() as client:
    r = client.get(f"{GATEWAY_URL}/api/tasks/{task_id}/status")
    print(f"Status: {r.status_code} - {r.json()}")

# ── Step 3: Worker claims the task ────────────────────────────────────────
print("\n=== Step 3: Worker claims task ===")
claim_body = json.dumps({"worker_id": WORKER_ADDR})
claim_headers = auth_headers(claim_body, WORKER_ADDR, WORKER_KEY)

with httpx.Client() as client:
    r = client.post(f"{GATEWAY_URL}/api/tasks/claim", content=claim_body, headers=claim_headers)
    print(f"Status: {r.status_code}")
    if r.status_code == 204:
        print("No task available to claim")
        exit(1)
    elif r.status_code != 200:
        print(f"Error: {r.text}")
        exit(1)
    data = r.json()
    print(f"Claimed: {json.dumps(data, indent=2)[:300]}")

# ── Step 4: Execute the skill (simulate) ──────────────────────────────────
print("\n=== Step 4: Execute skill ===")
result_data = {"status": "accepted", "echo": {"test": "hello_web3"}}
print(f"Result: {json.dumps(result_data)}")

# ── Step 5: Worker submits result ─────────────────────────────────────────
print("\n=== Step 5: Submit result ===")
submit_body = json.dumps({
    "task_id": task_id,
    "worker_id": WORKER_ADDR,
    "result_data": result_data,
})
submit_headers = auth_headers(submit_body, WORKER_ADDR, WORKER_KEY)

with httpx.Client() as client:
    r = client.post(f"{GATEWAY_URL}/api/tasks/submit", content=submit_body, headers=submit_headers)
    print(f"Status: {r.status_code}")
    data = r.json()
    print(f"Submit response: {json.dumps(data, indent=2)}")

    if r.status_code == 200:
        outcome = data.get("outcome", "UNKNOWN")
        total = data.get("total_cost", 0)
        developer = data.get("developer_payout", 0)
        platform = data.get("platform_tax", 0)
        pot = data.get("pot")
        print(f"\n=== Settlement Result ===")
        print(f"Outcome:         {outcome}")
        print(f"Total cost:      ${total:.4f} USDC")
        print(f"Developer:       ${developer:.4f} USDC (70%)")
        print(f"Platform tax:    ${platform:.4f} USDC (5%)")
        print(f"PoT signature:   {pot[:32] if pot else 'NONE'}...")
    else:
        print(f"Error: {data}")

# ── Step 6: Check post-task balances ──────────────────────────────────────
print("\n=== Step 6: Post-task balances ===")
with httpx.Client() as client:
    r = client.get(f"{GATEWAY_URL}/api/wallet/balance?user_id={USER_ADDR}")
    print(f"User balance: {r.json()}")

print("\n✓ Test complete")
