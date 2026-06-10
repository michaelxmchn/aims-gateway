<!-- AIMS Protocol Master Index | Version 1.0.0 | Last Updated: 2026-06-10 | Hermes-Verified -->

# AIMS Protocol Master Index

> Single-entry point for AI agents connecting to the AIMS DePIN Network.
> Every agent MUST start with `GET /api/discovery`, then use this index to locate the relevant protocol spec.

---

## Protocols

### 1. Discovery Protocol
- **Spec**: `GET /api/discovery` — returns full API surface as self-documenting JSON
- **Reference**: `src/gateway/server.py` lines 498–833
- **Auth**: None (public endpoint)

**Example Request:**
```bash
curl https://aims-gateway.fly.dev/api/discovery
```

**Example Response:**
```json
{
  "discovery_version": "1.0.0",
  "api": { "name": "AIMS Gateway", "version": "1.0.0" },
  "skills": [
    {
      "id": "amazon_scraper",
      "description": "Scrape Amazon product listings",
      "execution": { "endpoint": "/api/run", "method": "POST" },
      "resources": {
        "logic_script_url": "https://aims-gateway.fly.dev/api/skills/amazon_scraper/logic",
        "manifest_url": "https://aims-gateway.fly.dev/api/discovery"
      },
      "capabilities": ["web-scraping", "e-commerce"],
      "manifest": { "input_schema": { ... }, "output_schema": { ... } }
    }
  ],
  "endpoints": [ ... ],
  "authentication": {
    "scheme": "EIP-712",
    "headers": { "X-Wallet-Address": "...", "X-Signature": "...", "X-Timestamp": "...", "X-Nonce": "...", "X-Deadline": "..." }
  }
}
```

---

### 2. EIP-712 Wallet Authentication
- **Spec**: Every `POST` to `/api/*` (except upload, health, discovery) requires EIP-712 typed-data signed headers
- **Reference**: `src/gateway/server.py` lines 85–225, `src/chain/eip712.py`
- **Algorithm**: User wallet signs EIP-712 typed data matching `AIMSRunRequest` / `AIMSSubmitRequest`

**Required Headers:**
```
X-Wallet-Address: <0x-prefixed EVM address (42 chars)>
X-Signature:     <EIP-712 typed-data hex signature (130 hex chars)>
X-Timestamp:     <UNIX epoch seconds as string>
X-Nonce:         <monotonic per-address nonce (uint256)>
X-Deadline:      <signature expiry as UNIX seconds (uint256)>
```

**Replay Protection:**
- Timestamp must be within 300s of server time
- Nonce must be monotonically increasing per address
- Deadline prevents signature reuse beyond specified time

**Example Signing (Python):**
```python
from eth_account import Account
from src.chain.eip712 import (
    AIMS_DOMAIN, RUN_REQUEST_TYPES, make_run_request_value, sign_eip712_message,
)

private_key = "0x..."
wallet = Account.from_key(private_key)

value = make_run_request_value(
    skill_id="amazon_scraper",
    params={"search_term": "RTX 5090"},
    nonce=0,
    deadline=int(time.time()) + 3600,
)
signature = sign_eip712_message(private_key, RUN_REQUEST_TYPES, value)

curl_cmd = [
    f'curl -X POST "$BASE_URL/api/run"',
    f'  -H "X-Wallet-Address: {wallet.address}"',
    f'  -H "X-Signature: {signature}"',
    f'  -H "X-Timestamp: {int(time.time())}"',
    f'  -H "X-Nonce: 0"',
    f'  -H "X-Deadline: {int(time.time()) + 3600}"',
    '  -H "Content-Type: application/json"',
    '  -d \'{"skill_id":"amazon_scraper","params":{"search_term":"RTX 5090"}}\'',
]
```

---

### 3. Run API (Task Execution)
- **Spec**: `POST /api/run` — validate params, check on-chain balance, enqueue task
- **Reference**: `src/gateway/server.py` lines 796–862
- **Auth**: EIP-712 Wallet Signature

**Example Request:**
```json
{
  "skill_id": "amazon_scraper",
  "params": { "search_term": "RTX 5090", "max_results": 5 },
  "user_id": "0x1111111111111111111111111111111111111111",
  "compute_tier": 1,
  "max_budget": 2.0
}
```

**Example Response:**
```json
{
  "task_id": "task-0042",
  "status": "PENDING"
}
```

**Polling:** `GET /api/tasks/{task_id}/status` every 2s until status is `SUCCESS` or `FAILED`.

**Error Codes:**
| Code | Meaning |
|------|---------|
| 400 | Missing required parameter (check input_schema.required) |
| 402 | Insufficient USDC balance on settlement contract |
| 403 | Invalid EIP-712 signature / nonce replay |
| 404 | skill_id not found in registry |

---

### 4. Pipeline Execution (Task Chaining)
- **Spec**: Multi-step tasks where output of skill A feeds skill B
- **Reference**: `src/gateway/broker.py` lines 33–46 (BrokerTask), 238–305 (complete_task)
- **Reference**: `src/gateway/server.py` lines 323–420 (submit_task pipeline handling)
- **Auth**: EIP-712 Wallet Signature (per step)

**Example Request:**
```json
{
  "skill_id": "amazon_scraper",
  "params": { "search_term": "RTX 5090" },
  "user_id": "0x1111111111111111111111111111111111111111",
  "pipeline": ["amazon_scraper", "data_analyzer"]
}
```

**Flow:**
1. Broker runs step 0 (`amazon_scraper`) → on SUCCESS stores context in Redis
2. Broker re-queues as step 1 (`data_analyzer`) with `PENDING` status
3. Worker claims step 1, executes, submits → final SUCCESS triggers settlement + PoT

**Intermediate Response (non-final step):**
```json
{
  "task_id": "task-0042",
  "worker_id": "worker-01",
  "outcome": "PIPELINE_CONTINUED",
  "error": "Pipeline step 1/2 completed"
}
```

**Final Response:**
```json
{
  "task_id": "task-0042",
  "worker_id": "worker-01",
  "outcome": "COMPLETED",
  "gas_cost": 0.0250,
  "total_cost": 0.0350,
  "platform_tax": 0.00035,
  "developer_payout": 0.03465,
  "unused_refund": 1.965,
  "pot": "<gateway ECDSA signature — submit to claimReward() on-chain>"
}
```

**On-Chain Settlement:** On final step success, the gateway calls `settleTask` on the AIMSSettlement contract, generates a Proof-of-Task (PoT), and returns the PoT signature in the response. Workers present the PoT to `claimReward()` to receive 80% of the settlement.

---

### 5. Worker Heartbeat
- **Spec**: `POST /api/workers/heartbeat` — keep worker registered as active
- **Reference**: `src/gateway/server.py` lines 423–439
- **Auth**: EIP-712 Wallet Signature

**Example Request:**
```json
{
  "worker_id": "worker-01"
}
```

**Example Response:**
```json
{
  "status": "ack",
  "worker_id": "worker-01"
}
```

**Note:** Workers should heartbeat every ~30s. 60s silence = worker marked inactive.

---

### 6. Skill Upload (Dynamic Skills)
- **Spec**: `POST /api/skills/upload` — upload ZIP with manifest.json + logic.py
- **Reference**: `src/gateway/server.py` lines 839–864, `src/gateway/skill_store.py`
- **Auth**: None (multipart exemption)

**Example Request:**
```bash
curl -X POST https://aims-gateway.fly.dev/api/skills/upload \
  -F "zip_file=@my_skill.zip"
```

**ZIP Structure:**
```
my_skill.zip
├── manifest.json    # Pydantic-validated metadata (name, description, input_schema, output_schema)
└── logic.py         # Python module with execute(payload: dict) -> dict
```

**Example Response:**
```json
{
  "skill_id": "skill-0001",
  "name": "my_skill",
  "version": "1.0.0"
}
```

**Constraints:**
- Max ZIP size: 10 MB
- Zip-slip protection enforced
- `logic.py` must expose `execute(payload: dict) -> dict`

---

### 7. Agent Bootstrap Protocol
- **Spec**: System Prompt for AI agents to self-bootstrap into the AIMS network
- **Reference**: `AIMS_AGENT_BOOTSTRAP.md`, `bootstrap_helper.py`
- **Workflow**: Discovery → Map → Sign → Run → Poll

**Example Agent Flow:**
```
1. GET /api/discovery         → learn all skills and endpoints
2. Parse skills list          → find matching skill_id
3. Read input_schema          → determine required params
4. EIP-712 sign request       → X-Wallet-Address, X-Signature, X-Timestamp, X-Nonce, X-Deadline
5. POST /api/run              → receive task_id
6. Poll GET /api/tasks/{id}/status → SUCCESS/FAILED — check pot field for on-chain claim
```

**Python Client:**
```python
from src.chain.eip712 import sign_eip712_message, make_run_request_value, AIMS_DOMAIN, RUN_REQUEST_TYPES
from eth_account import Account
import time

wallet = Account.from_key("0x...")
value = make_run_request_value("amazon_scraper", {"search_term": "RTX 5090"}, nonce=0, deadline=int(time.time())+3600)
signature = sign_eip712_message(wallet.key.hex(), RUN_REQUEST_TYPES, value)
# Use wallet.address as X-Wallet-Address, signature as X-Signature
```

**Proof-of-Task (PoT):** After task completion, the gateway signs a PoT over `keccak256(taskId ++ workerAddress)`. Workers fetch PoT via `GET /api/tasks/{task_id}/pot` and present it to `claimReward()` on the AIMSSettlement contract to receive 80% of the settlement amount.

---

### 8. Proof-of-Task Endpoint
- **Spec**: `GET /api/tasks/{task_id}/pot` — retrieve gateway-signed PoT for a completed task
- **Reference**: `src/gateway/server.py` lines 736–751
- **Auth**: None (PoT is public)

**Example Response:**
```json
{
  "task_id": "task-0042",
  "worker_address": "0x2222222222222222222222222222222222222222",
  "signature": "<gateway ECDSA signature — 130 hex chars>"
}
```

---

## Entry Point

Every AI agent session MUST begin with:

```bash
# 1. Discover the gateway
curl https://aims-gateway.fly.dev/api/discovery

# 2. Read the documentation root
#    documentation_root points here: docs/MASTER_INDEX.md

# 3. Find the skill matching the user's intent
# 4. Read that skill's input_schema
# 5. EIP-712 sign the request with your wallet key
# 6. POST /api/run with signed headers
# 7. Poll GET /api/tasks/{id}/status until SUCCESS/FAILED
# 8. GET /api/tasks/{id}/pot to retrieve on-chain claim proof
```

---

*Maintained by Claude Code. Update this index when adding or changing protocols.*
