<!-- AIMS Protocol Master Index | Version 1.0.0 | Last Updated: 2026-06-09 | Hermes-Verified -->

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
    "scheme": "HMAC-SHA256",
    "headers": { "X-Signature": "...", "X-Timestamp": "...", "X-User-ID": "..." }
  }
}
```

---

### 2. HMAC-SHA256 Authentication
- **Spec**: Every `POST` to `/api/*` (except upload) requires HMAC headers
- **Reference**: `src/gateway/server.py` lines 44–146, `AIMS_AGENT_BOOTSTRAP.md` §HMAC Authentication
- **Algorithm**: `HMAC-SHA256(secret, utf8(body) + "|" + str(timestamp) + "|" + user_id)`

**Example Signing (Python):**
```python
import hmac, hashlib, time
secret = b"AIMS_MOCK_SECRET_2026"
body = b'{"skill_id":"amazon_scraper","params":{"search_term":"RTX 5090"},"user_id":"alice"}'
ts = str(int(time.time()))
msg = body + b"|" + ts.encode() + b"|" + b"alice"
sig = hmac.new(secret, msg, hashlib.sha256).hexdigest()
```

**Example Request Headers:**
```
X-Signature: <hex-encoded HMAC-SHA256>
X-Timestamp: 1712345678
X-User-ID: alice
```

**Replay Protection:** Timestamp must be within 300s of server time.

---

### 3. Run API (Task Execution)
- **Spec**: `POST /api/run` — validate params, create escrow, enqueue task
- **Reference**: `src/gateway/server.py` lines 879–932
- **Auth**: HMAC-SHA256

**Example Request:**
```json
{
  "skill_id": "amazon_scraper",
  "params": { "search_term": "RTX 5090", "max_results": 5 },
  "user_id": "alice",
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
| 402 | Insufficient user balance |
| 404 | skill_id not found in registry |

---

### 4. Pipeline Execution (Task Chaining)
- **Spec**: Multi-step tasks where output of skill A feeds skill B
- **Reference**: `src/gateway/broker.py` lines 33–46 (BrokerTask), 238–305 (complete_task)
- **Reference**: `src/gateway/server.py` lines 323–420 (submit_task pipeline handling)
- **Auth**: HMAC-SHA256 (per step)

**Example Request:**
```json
{
  "skill_id": "amazon_scraper",
  "params": { "search_term": "RTX 5090" },
  "user_id": "alice",
  "pipeline": ["amazon_scraper", "data_analyzer"]
}
```

**Flow:**
1. Broker runs step 0 (`amazon_scraper`) → on SUCCESS stores context in Redis
2. Broker re-queues as step 1 (`data_analyzer`) with `PENDING` status
3. Worker claims step 1, executes, submits → final SUCCESS triggers escrow settlement

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
  "unused_refund": 1.965
}
```

---

### 5. Worker Heartbeat
- **Spec**: `POST /api/workers/heartbeat` — keep worker registered as active
- **Reference**: `src/gateway/server.py` lines 423–439
- **Auth**: HMAC-SHA256

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
4. HMAC-SHA256 sign request   → X-Signature, X-Timestamp, X-User-ID
5. POST /api/run              → receive task_id
6. Poll GET /api/tasks/{id}/status → SUCCESS/FAILED
```

**Python Client:**
```python
from bootstrap_helper import AIMSClient
client = AIMSClient()
skills = client.discover()
result = client.run_skill("amazon_scraper", {"search_term": "RTX 5090"}, user_id="alice")
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
# 5. POST /api/run with HMAC-signed headers
# 6. Poll until SUCCESS/FAILED
```

---

*Maintained by Claude Code. Update this index when adding or changing protocols.*
