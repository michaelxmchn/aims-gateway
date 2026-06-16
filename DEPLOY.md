# AIMS 2.0 — Base Mainnet Production Deployment

> **Deployed**: 2026-06-16
> **Chain**: Base Mainnet (chain ID 8453)
> **Gateway**: `http://localhost:8000`

---

## Contract

| Field | Value |
|---|---|
| **AIMSAgentGateway** | `0x2489Ebcf0115fa6829A553395386977C6e5F03d9` |
| **USDC** | `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` |
| **Gateway Oracle** | `0xEF131aF48000E5d28ecFDa43bbc7cbA12f132216` |
| **Treasury** | `0x08c9Fd0A915f2b0856353850B8ADEA943F226BCf` |

### Architecture

- **gateway()** — 部署小号钱包，`AIMS_GATEWAY_PRIVATE_KEY` 控制，负责 ECDSA 签名验证
- **treasury()** — 用户 OKX 安全钱包，收取协议手续费（70/25/5 分账中的 5% 协议费）
- **USDC** — Base 原生 Circle-issued USDC（6 decimals）

---

## Cluster Topology

```
┌──────────────┐     ┌─────────────────┐     ┌──────────────┐
│  Redis       │◄────│  Gateway Server  │────►│  Base Mainnet │
│  (coordinator)│     │  (FastAPI +      │     │  (chain 8453) │
│  port 6379   │     │   AI Judge)      │     │               │
└──────────────┘     │  port 8000       │     └──────────────┘
                     └────────┬────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
     ┌────────┴──────┐ ┌─────┴───────┐ ┌─────┴──────┐
     │ Worker Node 1 │ │ Worker Node 2│ │ Worker Node 3│
     │ wallet-isolatd│ │ wallet-isolatd│ │ wallet-isolatd│
     │ no-shell      │ │ no-shell     │ │ no-shell     │
     └───────────────┘ └──────────────┘ └──────────────┘
```

### Services

| Container | Image | Role |
|---|---|---|
| `aims-prod-redis` | `redis:7-alpine` | AOF-persistent task coordinator |
| `aims-prod-gateway` | `aims-gateway:latest` | FastAPI + circuit breaker + AI Judge |
| `aims-prod-worker-1` | `aims-gateway:latest` | DePIN worker (wallet-isolated) |
| `aims-prod-worker-2` | `aims-gateway:latest` | DePIN worker (wallet-isolated) |
| `aims-prod-worker-3` | `aims-gateway:latest` | DePIN worker (wallet-isolated) |

### Worker Wallets

| Worker | Address | Private Key Env |
|---|---|---|
| worker-001 | `0x473aC968906e90DcD5EA9A31eebd988CfF157bEb` | `AIMS_WORKER_1_KEY` |
| worker-002 | `0x71f76ae783A9DE4a6f5d2729EC3318FF973E0689` | `AIMS_WORKER_2_KEY` |
| worker-003 | `0x720C842D3b1448976E584e6acb8914ee4c41a571` | `AIMS_WORKER_3_KEY` |

---

## Security Hardening

| Layer | Measure |
|---|---|
| **Redis** | `requirepass` 64-char password, no `FLUSHALL`, AOF persistence |
| **Gateway** | Runs as `uid 1000`, `cap_drop: ALL` + `NET_BIND_SERVICE` only |
| **Worker** | `read_only` rootfs, `tmpfs` for `/tmp`, `no-new-privileges`, no stdin/tty |
| **Smart Contract** | ECDSA gateway signature verification, nonce+taskId anti-replay, 3-phase circuit breaker |

---

## Environment Variables (export before deploy)

```bash
export AIMS_GATEWAY_PRIVATE_KEY="<gateway-signing-key>"
export AIMS_CONTRACT_ADDRESS="0x2489Ebcf0115fa6829A553395386977C6e5F03d9"
export AIMS_RPC_URL="https://base-mainnet.g.alchemy.com/v2/<key>"
export AIMS_SIGNING_SECRET="<64-char-hex>"
export REDIS_PASSWORD="<64-char-password>"
export OPENAI_API_KEY="sk-..."
```

Worker-specific (per node):
```bash
export AIMS_WORKER_1_WALLET="0x..."
export AIMS_WORKER_1_KEY="<private-key>"
```

---

## Common Maintenance Commands

```bash
# View all services
docker ps --filter "name=aims-prod"

# Gateway logs
docker logs -f aims-prod-gateway

# Worker logs (per node)
docker logs -f aims-prod-worker-1

# Circuit breaker status
curl -s http://localhost:8000/api/admin/circuit-breaker | jq .

# Health check
curl -s http://localhost:8000/api/health | jq .

# Restart gateway (zero-downtime for workers)
docker compose -f docker-compose.prod.yml restart gateway-server

# Full cluster restart
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d

# Check Redis AOF
docker exec aims-prod-redis redis-cli -a "$REDIS_PASSWORD" info persistence

# Emergency pause
curl -X POST http://localhost:8000/api/admin/emergency-pause

# Reset circuit breaker
curl -X POST http://localhost:8000/api/admin/reset

# Rebuild gateway image
docker build -t aims-gateway:latest .
docker compose -f docker-compose.prod.yml up -d gateway-server
```
