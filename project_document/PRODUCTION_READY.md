<!-- AIMS Protocol | Version 1.0.0 | Last Updated: 2026-06-15 | Hermes-Verified -->

# Production Readiness — Base Mainnet Migration Checklist

> **Audience**: DevOps / Platform Engineering  
> **Status**: Pre-Migration Review  
> **Target**: Base Mainnet (chain ID 8453)

---

## 1. Smart Contracts

### 1.1 Deploy Fresh Contracts (NEVER reuse testnet deployments)

| Contract | Action | Verification |
|---|---|---|
| `AIMSAgentGateway.sol` | Deploy with `PLATFORM_OWNER` = production multisig | `forge verify` on Basescan |
| `AIMS_Settlement.sol` | Deploy with canonical USDC address | `forge verify` on Basescan |
| `AIMSAgentGateway.sol` | Set `trusted_forwader` to production gateway address | Etherscan write |

### 1.2 Post-Deployment Verification

```bash
# Verify contract source on Basescan
forge verify-contract <address> contracts/AIMSAgentGateway.sol \
  --chain 8453 --etherscan-api-key $BASESCAN_KEY

# Check immutable values
cast call <gateway> "platformOwner()" --rpc-url https://mainnet.base.org
cast call <gateway> "usdc()" --rpc-url https://mainnet.base.org

# Confirm USDC matches canonical Base Mainnet address
# Canonical Base USDC: 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913
```

### 1.3 Contract Ownership & Upgrades

- **`PLATFORM_OWNER`** must be a **3/5 Gnosis Safe multisig** (not an EOA)
- Upgrade authority (if using UUPS) → same multisig
- Proxy admin (if using Transparent) → separate 2/3 multisig
- **Emergency pause** role → gateway hot wallet (revocable)

---

## 2. USDC Addresses

| Network | USDC (Native) | USDC.e (Bridged) |
|---|---|---|
| **Base Mainnet** | `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` | Do NOT use |
| Base Sepolia (test) | `0x036CbD53842c5426634E7929541eC231392a2859` | — |

**Important**: Use **native Base USDC** (Circle-issued) only. Bridged USDC.e has different
decimals and cannot be mixed. Verify `decimals()` returns `6`.

---

## 3. Gateway Deployment

### 3.1 Environment Variables (`production` profile)

```bash
# ── Required ──────────────────────────────────────────────────────────
AIMS_GATEWAY_PRIVATE_KEY=<gateway-hot-wallet-private-key>
AIMS_CONTRACT_ADDRESS=<deployed-AIMSAgentGateway-address>
AIMS_RPC_URL=https://mainnet.base.org
AIMS_SIGNING_SECRET=<high-entropy-random-hex-64-chars>
REDIS_URL=redis://:<password>@<redis-host>:6379/0

# ── Optional but recommended ──────────────────────────────────────────
AIMS_CONTRACT_DEPLOY_BLOCK=<block-of-deploy-tx>  # for event listener
AIMS_TREASURY_ADDRESS=<multisig-address>
AIMS_PLG_SUBSIDY_POOL_AMOUNT=100000                # $100 USDC (6 decimals)
OPENAI_API_KEY=<key>                               # AI Judge
```

### 3.2 Gateway Hot Wallet Security

- **NEVER** reuse the Hardhat dev key: `0xac0974...`
- Generate fresh: `openssl rand -hex 32`
- Store as **Fly.io secret** (never in env files):
  ```bash
  fly secrets set AIMS_GATEWAY_PRIVATE_KEY=$(openssl rand -hex 32)
  fly secrets set AIMS_SIGNING_SECRET=$(openssl rand -hex 32)
  ```
- Hot wallet should hold minimal ETH (< 0.1 ETH) — just enough for gas
- All settlement funds are held in the contract, not the hot wallet
- Rotate key quarterly via `rotateGatewayKey()` on the contract

### 3.3 Redis Security

- **Mandatory**: `redis://:<password>@...` with a 64-char random password
- Separate Redis instance per environment (production / staging)
- Enable TLS if using managed Redis (Upstash, Redis Cloud)
- `rename-command FLUSHALL ""` in redis.conf to prevent accidental wipe

---

## 4. Worker Node Security

### 4.1 DRM Black Box Verification

Before deploying workers to production, verify the DRM pipeline:

```bash
# 1. Obfuscate entry point
aims-cli publish --entry-point src/skills/amazon_scraper/logic.py

# 2. Verify dist.zip contains ONLY:
#    - wrapper.so          (PyArmor-obfuscated binary)
#    - logic.enc           (AES-256-GCM encrypted source)
#    No plaintext .py files should leak

# 3. Worker can execute without reading source
python -c "
from aimscore.drm import decrypt_and_execute
result = decrypt_and_execute('dist/logic.enc', 'dist/wrapper.so')
print('DRM OK:', result)
"
```

### 4.2 Hardening Checklist

| Check | Requirement | Verification |
|---|---|---|
| Worker runs as **non-root** user | `uid 1000` in Docker | `whoami` in container |
| All filesystem writes go to `/tmp` | No persistent storage | `docker diff` |
| Outbound traffic restricted | Worker → gateway only | egress firewall rule |
| No shell access | `ENTRYPOINT` binary only | `docker exec` test |
| Secret zeroing | Keys in env vars, not files | `env` check |
| Payload sandboxing | DRM wrapper validates input schema | integration test |
| No network sniffing | `CAP_NET_RAW` dropped | `docker run --cap-drop=ALL` |

### 4.3 Worker Wallet Isolation

Each worker must have a unique EVM wallet with:

- Separate private key (never shared across workers)
- Key provisioned via `AIMS_WORKER_KEY` environment variable (secret)
- Worker wallet holds **0 ETH** — it does not sign transactions, only PoT receipts
- Worker wallet registration in the contract must use the **same** address

```bash
# Generate a fresh worker key
openssl rand -hex 32 | xargs -I{} sh -c 'echo "0x{}"'
```

---

## 5. Cluster Deployment (Docker Compose → Production)

### 5.1 docker-compose.yml Check

Review `docker-compose.yml` before production deployment:

- [ ] All `worker-node-*` containers use **different** `AIMS_WORKER_KEY` values
- [ ] `AIMS_GATEWAY_PRIVATE_KEY` is **never** in `.env` — always injected by platform
- [ ] Redis password is set and not the default
- [ ] `AIMS_RPC_URL` points to **Base Mainnet** (not localhost or testnet)
- [ ] Health checks configured for all services
- [ ] Volume mounts for `./dist/` exist and contain valid DRM artifacts
- [ ] `restart: unless-stopped` is set (production resilience)

### 5.2 Fly.io Production Launch (Alternative to Docker Compose)

```bash
# Gateway service
fly launch --name aims-gateway-prod --region sin
fly secrets set AIMS_GATEWAY_PRIVATE_KEY=... AIMS_SIGNING_SECRET=...
fly secrets set REDIS_URL=redis://... AIMS_RPC_URL=https://mainnet.base.org
fly deploy

# Attach Redis (Upstash)
fly redis create --name aims-redis-prod --region sin
fly redis attach aims-redis-prod

# Scale
fly scale count 2   # 2 gateway replicas
fly scale memory 512
```

### 5.3 Monitoring & Alerting

| Metric | Source | Alert threshold |
|---|---|---|
| Circuit Breaker OPEN | `GET /api/admin/circuit-breaker` | PagerDuty immediate |
| Task failure rate | `GET /api/health` → `tasks_failed / tasks_total` | > 5% / 5 min |
| Gateway HTTP 5xx rate | Fly.io metrics | > 1% / 1 min |
| USDC contract balance | `contract.usdc_balance()` call | < $100 |
| Worker liveness | `POST /api/workers/heartbeat` | > 3 missed / worker |
| Redis memory | Upstash dashboard | > 80% used |
| AI Judge latency | `JudgeEngine.score()` timing | > 10s p95 |

---

## 6. Deployment Runbook

### 6.1 Pre-Flight (T-48h)

- [ ] Deploy contracts to Base Mainnet via multisig
- [ ] Verify contract source on Basescan
- [ ] Fund multisig with initial ETH for gas
- [ ] Transfer 100 USDC to contract for PLG subsidy pool
- [ ] Generate and store gateway hot wallet key
- [ ] Generate 3 worker keys (one per replica)
- [ ] Build and verify DRM-dist skills (`aims-cli publish`)
- [ ] Set all Fly.io secrets

### 6.2 Launch Sequence

```bash
# Step 1: Smoke test on testnet first
docker compose -f docker-compose.yml up -d   # points to Base Sepolia
python scripts/demo_day_master.py --gateway http://localhost:8000
docker compose down -v

# Step 2: Point to mainnet env vars
fly secrets set AIMS_RPC_URL=https://mainnet.base.org
fly secrets set AIMS_CONTRACT_ADDRESS=<mainnet-deployed-address>
fly secrets unset AIMS_CONTRACT_ADDRESS  # revert if wrong

# Step 3: Deploy gateway
fly deploy --ha

# Step 4: Deploy workers (separate Fly machines or Docker hosts)
docker compose -f docker-compose.yml up -d worker-node-1 worker-node-2 worker-node-3

# Step 5: Verify health
curl -s https://aims-gateway-prod.fly.dev/api/health | jq .
curl -s https://aims-gateway-prod.fly.dev/api/admin/circuit-breaker | jq .

# Step 6: Monitor for 15 minutes
watch -n 30 "curl -s https://aims-gateway-prod.fly.dev/api/health"
```

### 6.3 Rollback Plan

If issues are detected within the first hour:

```bash
# Rollback gateway
fly deploy --image aims-gateway:<previous-version>

# Emergency pause (rejects all new tasks)
curl -X POST https://aims-gateway-prod.fly.dev/api/admin/emergency-pause

# After fix: resume
curl -X POST https://aims-gateway-prod.fly.dev/api/admin/reset
```

---

## 7. Cost Projections (Base Mainnet)

| Item | Estimated Monthly Cost | Notes |
|---|---|---|
| Fly.io gateway (512 MB × 2) | ~$35 | 2 replicas, auto-scaling |
| Fly.io Redis (Upstash 250 MB) | ~$15 | Includes backup |
| Fly.io workers (3 × 256 MB) | ~$30 | 3 worker nodes |
| Base Mainnet gas (contract calls) | ~$5–20 | ~5000 tx/month @ 0.0001 ETH/gas |
| Basescan API | Free | 5 req/s rate limit |
| OpenAI API (AI Judge) | ~$10–50 | ~5000 scores/month |
| **Total** | **~$95–150/mo** | Excludes USDC settlement volume |

---

## 8. Security Contact

- **Emergency**: `security@aimsprotocol.io` (SLA 15 min)
- **Bug Bounty**: Immunefi program (up to $50,000 USDC)
- **Admin Multisig**: `0x...` (3/5 Gnosis Safe on Base)

---

## 9. Appendices

### A. Mainnet Addresses (Pre-Flight Placeholders)

| Component | Address | Notes |
|---|---|---|
| AIMSAgentGateway | `0x...` | Deploy T-48h |
| AIMS_Settlement | `0x...` | Deploy T-48h |
| USDC (Base) | `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` | Canonical |
| Admin multisig | `0x...` | 3/5 Gnosis Safe |
| Gateway hot wallet | `0x...` | Generated T-24h |

### B. CLI Commands (Production)

```bash
# Check contract USDC balance
cast call <usdc> "balanceOf(address)(uint256)" <contract> \
  --rpc-url https://mainnet.base.org

# Deposit USDC to contract (user-facing via console)
cast send <contract> "wallet_deposit(uint256)" 1000000 \
  --rpc-url https://mainnet.base.org --private-key $USER_KEY

# Claim PoT reward
cast send <contract> "claimReward(bytes,bytes)" <pot> <sig> \
  --rpc-url https://mainnet.base.org --private-key $WORKER_KEY
```

## 10. Mainnet Monitoring — Hardcore Dashboards

### 10.1 Redis AOF — Trace Every $0.05 USDC Flow

After a real user task settles, the Redis AOF log records every escrow hold,
settlement, and refund.  Monitor live:

```bash
# Attach to Redis CLI
docker exec -it aims-prod-redis redis-cli -a "${REDIS_PASSWORD}"

# Inside redis-cli — list all keys
KEYS task:*
KEYS wallet:*
KEYS settlement:*

# Get task status
HGETALL task:task-0001          # → status, worker, user, amount

# Get wallet balance
GET wallet:0xUserAddress:usdt   # → raw balance (6 decimals)

# Count total settlements
SCARD settlement:ledger         # → total settled task count

# Monitor live stream (10 sec sample)
MONITOR | head -50              # every command hitting Redis
```

### 10.2 PLG Zero-CAC Grayscale Tracking

Track the Universal First-Task-Free PLG pipeline in production:

```bash
# Check free trial usage per wallet
curl -s http://localhost:8000/api/admin/trials | jq '.'

# Expected output:
# {
#   "0xUserAddress": { "amazon_scraper": { "usage_count": 1, "eligible": false } }
# }

# Check PLG subsidy pool remaining
curl -s http://localhost:8000/api/admin/pools | jq '.plg_pool'

# Monitor real-time SSE settlement feed (watch live)
curl -Ns http://localhost:8000/api/v2/feed/stream

# Each event shows: action=settle, user, worker, developer split amounts
```

### 10.3 AI Judge (DeepSeek) Scoring Audit

Every task scored by DeepSeek leaves an audit trail:

```bash
# Check judge health
curl -s http://localhost:8000/api/admin/judge | jq '.'

# Verify model is deepseek-chat
# Expected: {"model": "deepseek-chat", "status": "ready", ...}

# Recent verdicts (last 100)
curl -s http://localhost:8000/api/admin/judge/verdicts?limit=5 | jq '.'

# DeepSeek latency check (p95 should be < 5s)
curl -s http://localhost:8000/api/health | jq '.judge_latency_ms'
```

### 10.4 Circuit Breaker — Always CLOSED

```bash
# Snapshot every 30 seconds
watch -n 30 'curl -s http://localhost:8000/api/admin/circuit-breaker | jq .'

# Healthy output:
# { "state": "CLOSED", "consecutive_fails": 0, "degraded_fails": 0 }
```

### 10.5 Audit Ledger — Full Settlement History

```bash
# All settlements (paginated)
curl -s "http://localhost:8000/api/admin/audit?limit=10" | jq '.'

# Filter by specific task
curl -s "http://localhost:8000/api/admin/audit?task_id=task-0042" | jq '.'

# Aggregate stats
curl -s "http://localhost:8000/api/admin/audit" | \
  python3 -c "import sys,json; data=json.load(sys.stdin); print(f'Tasks: {len(data.get(\"ledger\",[]))}')"
```

### 10.6 Production Watchdog — One-Liner Health Board

```bash
# Paste into production terminal for a Bloomberg-style dashboard
while true; do
  clear
  echo "=== AIMS MAINNET DASHBOARD ==="
  echo "Time: $(date -u +%H:%M:%S) UTC"
  echo ""
  curl -s http://localhost:8000/api/health | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'Gateway:      {\"UP\" if d.get(\"gateway\",\"\")==\"healthy\" else \"DOWN\"}')
print(f'Chain:        {d.get(\"chain_status\",\"unknown\")}')
print(f'CB State:     {d.get(\"circuit_breaker\",{}).get(\"state\",\"unknown\")}')
print(f'Tasks:        {d.get(\"tasks_total\",0)} total / {d.get(\"tasks_pending\",0)} pending')
print(f'Judge Model:  {d.get(\"judge_model\",\"unknown\")}')
print(f'Pool USDC:    {d.get(\"plg_pool\",\"?\")}')
"
  sleep 10
done
```

---

### C. Environment Variable Reference

| Variable | Required | Default | Production Value |
|---|---|---|---|
| `AIMS_GATEWAY_PRIVATE_KEY` | Yes | — | Fly.io secret |
| `AIMS_CONTRACT_ADDRESS` | Yes | `0x000...0001` | Mainnet deployed |
| `AIMS_RPC_URL` | Yes | `http://localhost:8545` | `https://mainnet.base.org` |
| `AIMS_SIGNING_SECRET` | Yes | `AIMS_MOCK_SECRET_2026` | 64-char hex |
| `REDIS_URL` | Yes | `None` (in-memory) | Upstash TLS |
| `AIMS_GATEWAY_URL` | Workers | `https://api.aimsgateway.com` | `https://aims-gateway-prod.fly.dev` |
| `AIMS_WORKER_ID` | Workers | `worker-001` | Per-replica unique |
| `AIMS_WORKER_KEY` | Workers | — | Per-replica unique |
| `AIMS_PLG_SUBSIDY_POOL_AMOUNT` | No | `0` | `100000` ($100) |
| `OPENAI_API_KEY` | No | — | For AI Judge |
