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

---

## AIMS 2.0 系统业务与功能梳理报告

> **生成时间**: 2026-06-16
> **链上合约**: AIMSAgentGateway @ 0x2489Ebcf0115fa6829A553395386977C6e5F03d9
> **底链**: Base Mainnet (chain ID 8453)
> **部署**: Docker Compose 3-node cluster, offline images

### 1. 核心定位

AIMS 2.0 是一个 **AI Agent 自动化技能引擎**，定位为去中心化的任务调度与链上结算网络。本质是一个将 AI 技能执行与区块链价值结算深度耦合的生产系统。

**三层价值主张:**
1. **技能市场** — 开发者上传技能逻辑 (Python)，按调用付费
2. **去中心化执行** — 3 个 Worker 节点竞争抢单执行
3. **链上结算** — 70/25/5 分账，Proof-of-Task 凭证领取

### 2. 核心业务流程 (端到端)

| Step | 环节 | 说明 |
|---|---|---|
| 1 | **用户提交任务** | EIP-191 personal_sign 签署请求体 → `POST /api/run` |
| 2 | **网关预处理** | Canary 水印注入 → 熔断器检查 → 任务入队 (Redis) → 许可证检查 |
| 3 | **AI Judge 合规评分** | DeepSeek v4 Flash 从 Correctness/Completeness/Quality 评分 0-100 |
| 4 | **Worker 抢单执行** | 3 Worker 轮询 claim → 执行技能逻辑 → submit result |
| 5 | **链上结算** | Judge ≥ 80 → settleTask (70/25/5) + PoT 凭证; < 80 → refundTask + SSE 红警 |
| 6 | **审计追踪** | BillingEngine._audit_ledger → `GET /api/admin/audit` |

### 3. 商业模式矩阵

| 维度 | Metered | Subscription | Free Trial | Buyout |
|---|---|---|---|---|
| 计费方式 | 按次扣费 | 月付配额 | 零元试用 | 一次性买断 |
| 收入确认 | 即时 | 订阅周期 | 转化漏斗 | 永久许可 |
| 典型场景 | 低频工具 | 高频 SaaS | 新客获客 | 企业部署 |

### 4. 安全架构

| 层级 | 机制 | 说明 |
|---|---|---|
| **认证** | EIP-191 personal_sign | X-Wallet-Address + X-Signature + X-Timestamp (±300s) |
| **反盗版** | Canary 三层防御 | ECDSA 签名注入 → 验签 + 重放检测 → FORBIDDEN_PIRACY 熔断 |
| **资产隔离** | Treasury Isolation | 大号 (Treasury) 持有资产, 小号 (Gas 中继) 仅 0.015 ETH |
| **熔断** | 三阶智能熔断器 | CLOSED → HALF_OPEN (3次失败) → OPEN (6次), 120s 自愈 |
| **隔离** | Worker 生产隔离 | read_only rootfs + tmpfs + cap_drop:ALL + no-new-privileges |
| **防重放** | 滑动窗口限流 | 100 req/60s + Timestamp ±300s |

### 5. E2E 联调测试结果 (2026-06-16)

| Task ID | Worker | Skill | Judge Score | Settlement | Status |
|---|---|---|---|---|---|
| task-0001 | worker-001 | amazon_scraper | — | — | SUCCESS |
| task-0002 | worker-002 | amazon_scraper | — | — | SUCCESS |
| task-0003 | worker-002 | amazon_scraper | 85 | SETTLED | SUCCESS |
| task-0004 | worker-002 | amazon_scraper | 85 | SETTLED | SUCCESS |
| task-0005 | worker-002 | amazon_scraper | 85 | SETTLED | SUCCESS |
| task-0006 | worker-002 | amazon_scraper | ≥80 | SETTLED | SUCCESS |

**全链路验证通过:** User POST → EIP-191 Auth → Gateway Dispatch → Worker Claim → Execute → Judge Scoring → On-chain Settlement

### 6. 风险控制矩阵

| 风险 | 控制措施 |
|---|---|
| Worker 作恶 (虚假结果) | Canary 水印 + AI Judge 评分 |
| Gas 费耗尽 (小号) | Treasury Isolation, 仅 0.015 ETH |
| Judge 不可用 (DeepSeek 宕机) | 确定性回退 + 熔断自愈 |
| 重放攻击 | Timestamp 窗口 + 限流器 |
| Worker 私钥泄露 | 仅 Gas 权限, 0 资产风险 |
| 版权侵权 | Licensing + Encrypted Source |

### 7. 快速运维命令

```bash
# 查看集群状态
docker-compose -f docker-compose.prod.yml ps

# 查看 Gateway 日志
docker-compose -f docker-compose.prod.yml logs -f gateway-server

# 查看 Worker 日志 (指定节点)
docker-compose -f docker-compose.prod.yml logs -f worker-node-2

# 触发 E2E 业务测试
python3 scripts/test_trigger_biz.py

# 紧急全网暂停
curl -X POST http://localhost:8000/api/admin/emergency-pause \
  -H "Content-Type: application/json" \
  -d '{"key": "admin-emergency-key-2026"}'

# 熔断器状态快照
curl http://localhost:8000/api/admin/circuit-breaker

# 审计追踪
curl http://localhost:8000/api/admin/audit

# Redis 队列深度
docker exec aims-prod-redis redis-cli -a '${REDIS_PASSWORD}' LLEN task_queue
```
