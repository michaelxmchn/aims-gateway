# AIMS Console 核心功能按钮与数据流白皮书

> **版本**: 1.0.0  
> **日期**: 2026-06-17  
> **扫描范围**: `static/console.html`（2971 行）+ `src/gateway/server.py`  
> **用途**: 为布局重构提供完整的交互资产清单与风险点记录

---

## 1 全景统计

| 类别 | 数量 |
|------|------|
| 总 `<button>` 元素 | **62** 个 |
| 带 onclick 的按钮 | 59 个 |
| 表单提交按钮 (onsubmit) | 3 个 |
| 非按钮 onclick 处理（div） | 1 个（复制 API Key） |
| `<form>` 表单 | 3 个 |
| JS 函数总数 | **~50** 个 |
| 调用的 API 端点 | **~25** 个 |

---

## 2 认证架构

### 2.1 `smartHeaders()` — 统一鉴权头生成（console.html:1232）

```
smartHeaders(body):
  ├─ MetaMask 已安装 → eip191SignBody(body) + getAuthHeaders(body, sig)
  │                    生成: X-Wallet-Address + X-Signature + X-Timestamp
  └─ MetaMask 未安装 → jwtHeaders()
                       生成: Authorization: Bearer <aims_jwt>
```

### 2.2 API Key 鉴权

`jwtHeaders()`（console.html:1222）—— 读取 `localStorage.aims_jwt`，适用于无 MetaMask 但有 JWT 令牌的场景。

### 2.3 后端鉴权 3 层

每个 `/api/*` 端点按优先级依次尝试：
1. **JWT Bearer**（`Authorization: Bearer <token>`）—— 用户登录后发放
2. **API Key**（`Bearer sk-aims-*`）—— 持久化密钥，适合程序化访问
3. **EIP-191 personal_sign**（`X-Wallet-Address` + `X-Signature` + `X-Timestamp`）—— MetaMask 签名

---

## 3 7 大核心操作像素级分析

### 3.1 🚀 发布新任务 (Publish Task)

| 属性 | 值 |
|------|-----|
| **HTML 元素** | `<form onsubmit="publishTask(event)">`（行 530），`<button id="publishBtn">`（行 550） |
| **JS 函数** | `window.publishTask(event)`（行 1740） |
| **API 路由** | `POST /api/tasks/publish`（server.py 行 1970） |
| **鉴权** | `smartHeaders(body)` → EIP-191 优先，降级 JWT |
| **请求体** | `{skill_id, params, user_id, developer_premium, max_budget, compute_tier, task_name, description, is_custom, credit_score_required}` |
| **后端校验链** | Circuit Breaker(503) → Registry(404) → Schema(400) → Free Trial(402) → Balance(402) → Budget(400) → Auto-seed → Broker publish → Vault create |
| **返回** | `{task_id, status: "PENDING", vault_address, vault_status: "unfunded"}` |
| **前端渲染** | 显示 task_id + escrow 金额，展开 vault 扫码付款面板 |

**依赖前置条件**：钱包已连接（`walletAddress != ""`）+ Skill 列表已加载（`fetchDiscovery()` 成功）

---

### 3.2 ⚡ Boost 提高奖金

| 属性 | 值 |
|------|-----|
| **HTML 元素** | `<input id="boostAmount">` + `<button onclick="boostReward()" id="boostBtn">`（行 595） |
| **JS 函数** | `window.boostReward()`（行 2091） |
| **API 路由** | `POST /api/tasks/{task_id}/boost-reward`（server.py 行 1868） |
| **请求体** | `{"amount": <float>}` |
| **后端校验** | Vault 存在(404) → 状态 `funded`(409) → 累加 balance/budget/total_boosted |
| **返回** | `{status, task_id, vault_address, balance, boost_amount, total_boosted, message}` |

**🔴 已知风险**：
- `_currentVaultTaskId` 在 Tab 切换时丢失，导致点击无反应
- 需要 vault 处于 `funded` 状态（先模拟/实际付款）

---

### 3.3 🔑 生成新 API Key

| 属性 | 值 |
|------|-----|
| **HTML 元素** | `<input id="apiKeyLabel">` + `<button onclick="createApiKey()">`（行 827） |
| **JS 函数** | `window.createApiKey()`（行 2874） |
| **API 路由** | `POST /api/auth/api-keys`（server.py 行 3697） |
| **鉴权** | `jwtHeaders()` → `Authorization: Bearer <jwt>` |
| **请求体** | `{"label": "..."}` |
| **后端校验** | `_require_user()` → JWT cookie/header → `generate_api_key()` |
| **返回** | `{api_key: "sk-aims-...", key_prefix, label}` |

**✅ 状态**：已验证飞通过。此前曾因 SyntaxError 导致 `createApiKey` 未定义，现已修复。

---

### 3.4 ❌ 撤销 API Key

| 属性 | 值 |
|------|-----|
| **HTML 元素** | 动态渲染 `<button onclick="revokeApiKey(${k.id})">`（行 2867） |
| **JS 函数** | `window.revokeApiKey(keyId)`（行 2899） |
| **API 路由** | `DELETE /api/auth/api-keys/{key_id}`（server.py 行 3713） |
| **鉴权** | `jwtHeaders()` |
| **后端校验** | `_require_user()` → `revoke_api_key(key_id, user_id)` → 校验所有权 |
| **返回** | `{status: "revoked", key_id}` 或 404 |

**流程**：confirm 弹窗确认 → DELETE → toast + 刷新列表。低风险。

---

### 3.5 👥 保存贡献者分账

| 属性 | 值 |
|------|-----|
| **HTML 元素** | 动态行 + `<button onclick="saveContributors()">`（行 807） |
| **JS 函数** | `window.saveContributors()`（行 2179） |
| **API 路由** | `POST /api/developer/set-contributors`（server.py 行 1617） |
| **请求体** | `{skill_name, wallet_address, co_contributors: [{wallet, share_pct}]}` |
| **后端校验** | Integration 记录存在(404) → Skill 名匹配(404) → 存储 |
| **返回** | `{status: "ok", wallet, skill, co_contributors, total_share_pct, message}` |

**🟡 已知风险**：
- 必须先 One-Click Integration（否则 404）
- DOM 动态行在页面重绘后可能丢失

---

### 3.6 📥 申领任务

| 属性 | 值 |
|------|-----|
| **HTML 元素** | 动态 `<button onclick="claimTask(taskId, creditReq, isCustom)">`（行 1846） |
| **JS 函数** | `window.claimTask(taskId, creditReq, isCustom)`（行 1857） |
| **API 路由（两步）** | `GET /api/worker/credit-score/{wallet}` + `POST /api/tasks/claim-specific` |
| **请求体（第二步）** | `{task_id, worker_id, credit_score}` |
| **后端校验** | Credit score 门控（custom 任务需分数达标）→ Broker claim |
| **返回** | `ClaimResponse` 或 403（信用分不足） |

**🟡 已知风险**：
- 信用分查询 `catch(e){}` 静默失败 → `creditScore=0` → custom 任务必然被阻止
- 需要先 Connect Wallet

---

### 3.7 💰 模拟/实际付款

| 属性 | 值 |
|------|-----|
| **HTML 元素** | `<button onclick="simulateVaultPayment()" id="vaultPayBtn">`（行 582） |
| **JS 函数** | `window.simulateVaultPayment()`（行 2034） |
| **API 路由** | `POST /api/tasks/{task_id}/simulate-fiat-payment`（server.py 行 1817） |
| **请求体** | `{}`（空 JSON） |
| **后端校验** | Vault 存在(404) → 状态 `unfunded`(409) → 设为 `funded` |
| **返回** | `{status: "funded", task_id, vault_address, balance, message}` |

**🔴 已知风险**：
- `_currentVaultTaskId` 在 Tab 切换时丢失（与 Boost 共享同一变量）
- `smartHeaders({})` 对空对象签名 — 用户可能不理解 MetaMask 签名弹窗

---

## 4 完整按钮清单

### 4.1 全局/导航

| 按钮 | 行 | 函数 | API/行为 | 风险 |
|------|-----|------|---------|------|
| Connect Wallet | 371 | `connectWallet()` | MetaMask + `/api/auth/pre-check` | 低 |
| Google Login | 373 | `toast('coming soon')` | 静态占位 | 无 |
| Apple Login | 377 | `toast('coming soon')` | 静态占位 | 无 |
| Consumer Tab | 408 | `switchRole('consumer')` | 纯 DOM | 无 |
| Developer Tab | 411 | `switchRole('developer')` | 纯 DOM + 加载数据 | 无 |
| Worker Tab | 414 | `switchRole('worker')` | 纯 DOM | 无 |

### 4.2 Consumer Tab — 调用 Skill

| 按钮 | 行 | 函数 | API | 风险 |
|------|-----|------|-----|------|
| Execute & Settle | 489 | `invokeSkill(event)` | `POST /api/run` + `GET /api/tasks/{id}/status` | 低 |
| Refresh Balance | 458 | `refreshBalance()` | `GET /api/wallet/balance` | 低 |
| Free Trial 按钮 | 490 | 设 billingMode=trial | 纯 DOM | 无 |
| Refresh Credit | 520 | `fetchCreditScore()` | `GET /api/worker/credit-score/{wallet}` | 低 |
| Metered 模式 | 610 | `switchBillingMode('pay_per_task')` | 纯 DOM | 无 |
| Subscription 模式 | 611 | `switchBillingMode('subscription')` | 纯 DOM | 无 |
| Free Trial 模式 | 612 | `switchBillingMode('trial')` | 纯 DOM | 无 |
| Buyout License | 615 | `openBuyoutModal()` | 纯 DOM | 无 |
| Clear Log | 628 | `clearLog()` | 纯 DOM | 无 |

### 4.3 Consumer Tab — 充值/提现/法币

| 按钮 | 行 | 函数 | API | 风险 |
|------|-----|------|-----|------|
| 10 USDC | 644 | `rechargeReserves(10)` | `POST /api/wallet/deposit` | 低 |
| 25 USDC | 645 | `rechargeReserves(25)` | 同上 | 低 |
| 50 USDC | 646 | `rechargeReserves(50)` | 同上 | 低 |
| 100 USDC | 647 | `rechargeReserves(100)` | 同上 | 低 |
| 250 USDC | 648 | `rechargeReserves(250)` | 同上 | 低 |
| 500 USDC | 649 | `rechargeReserves(500)` | 同上 | 低 |
| Custom Deposit | 653 | `rechargeReserves(parseFloat(...))` | 同上 | 低 |
| $25 Credit Card | 658 | `fiatDeposit(25)` | `POST /api/wallet/fiat-deposit` | 低 |
| $50 Credit Card | 659 | `fiatDeposit(50)` | 同上 | 低 |
| $100 Credit Card | 660 | `fiatDeposit(100)` | 同上 | 低 |
| Withdraw | 668 | `withdrawFunds()` | `POST /api/wallet/withdraw` | 低 |

### 4.4 Consumer Tab — 历史账本

| 按钮 | 行 | 函数 | API | 风险 |
|------|-----|------|-----|------|
| All (Audit) | 690 | `fetchAudit('')` | `GET /api/admin/audit` | 🟡 可能需 admin |
| Settlements | 691 | `fetchAudit('settle')` | 同上 | 🟡 可能需 admin |
| Refunds | 692 | `fetchAudit('refund')` | 同上 | 🟡 可能需 admin |
| Search Audit | 697 | `fetchAudit(filter)` | 同上 | 🟡 可能需 admin |
| User History All | 710 | `fetchHistory('')` | `GET /api/wallet/history` | 低 |
| Deposits | 711 | `fetchHistory('deposit')` | 同上 | 低 |
| Withdrawals | 712 | `fetchHistory('withdraw')` | 同上 | 低 |
| Tasks | 713 | `fetchHistory('task_deduction')` | 同上 | 低 |

### 4.5 Consumer Tab — 任务发布与 Vault

| 按钮 | 行 | 函数 | API | 风险 |
|------|-----|------|-----|------|
| Publish to Market | 550 | `publishTask(event)` | `POST /api/tasks/publish` | 低 |
| **Simulate Fiat Payment** | 582 | `simulateVaultPayment()` | `POST /api/tasks/{id}/simulate-fiat-payment` | 🔴 `_currentVaultTaskId` |
| Check Status | 583 | `pollVaultStatus()` | `GET /api/tasks/{id}/vault-status` | 🔴 `_currentVaultTaskId` |
| **Boost Reward** | 595 | `boostReward()` | `POST /api/tasks/{id}/boost-reward` | 🔴 `_currentVaultTaskId` |
| Refresh Health+Balance | 698 | `fetchHealth();refreshBalance()` | 双 API | 低 |

### 4.6 Consumer Tab — Task Market 动态按钮

| 按钮 | 行 | 函数 | 风险 |
|------|-----|------|------|
| ⚡ Boost from Market | 1845 | `boostFromMarket(taskId)`（纯 DOM 滚动） | 低 |
| **Claim** | 1846 | `claimTask(taskId, creditReq, isCustom)`（两步 API） | 🟡 静默 catch |

### 4.7 Developer Tab

| 按钮 | 行 | 函数 | API | 风险 |
|------|-----|------|-----|------|
| Refresh Credit | 761 | `fetchCreditScore()` | `GET /api/worker/credit-score/{wallet}` | 低 |
| **One-Click Integrate** | 784 | `oneClickIntegrate(event)` | `POST /api/developer/integrate` | 需 Connect Wallet |
| Refresh Integration | 786 | `fetchIntegrationStatus()` | `GET /api/developer/integration/{wallet}` | 低 |
| + Add Contributor | 806 | `addContributorRow()` | 纯 DOM | 无 |
| **Save Split Config** | 807 | `saveContributors()` | `POST /api/developer/set-contributors` | 🟡 需先集成 |
| **+ Generate New Key** | 827 | `createApiKey()` | `POST /api/auth/api-keys` | 已验证通过 |
| Refresh Keys | 828 | `fetchApiKeys()` | `GET /api/auth/api-keys` | 低 |
| Revoke Key | 2867 | `revokeApiKey(keyId)` | `DELETE /api/auth/api-keys/{id}` | 低 |
| Refresh Task Market | 842 | `fetchPendingTasks()` | `GET /api/tasks/pending` | 低 |
| Upload Skill | 871 | `uploadSkill()` | `POST /api/skills/upload` (FormData) | 🟡 ZIP 上传 |
| Remove Contributor | 2150 | `removeContributorRow(idx)` | 纯 DOM | 无 |

### 4.8 Worker Tab

| 按钮 | 行 | 函数 | API | 风险 |
|------|-----|------|-----|------|
| Start Node | 903 | `startWorkerSim()` | 15s heartbeat interval | 低 |
| Heartbeat | 904 | `sendHeartbeat()` | `POST /api/workers/heartbeat` | 低 |
| Refresh Health | 956 | `fetchHealth()` | `GET /api/health` | 低 |
| Refresh Discovery | 961 | `fetchDiscovery()` | `GET /api/discovery` | 低 |

### 4.9 模态框按钮

| 按钮 | 行 | 函数 | API | 风险 |
|------|-----|------|-----|------|
| Use Free Trial | 317 | `closeDepositModal(); set billingMode=trial` | 纯 DOM | 无 |
| Dismiss | 323 | `closeDepositModal()` | 纯 DOM | 无 |
| Deposit 50 USDC | 324 | `handleDeposit()` | `POST /api/wallet/deposit` | 低 |
| Cancel (Buyout) | 347 | `closeBuyoutModal()` | 纯 DOM | 无 |
| **Purchase Perpetual License** | 348 | `confirmBuyout()` | `POST /api/licensing/request-key` | 🟡 需 task 特定状态 |

---

## 5 API 端点完整映射

### 5.1 控制台调用端点（console.html → server.py）

| 前端 fetch URL | Method | server.py 行 | 功能 |
|---------------|--------|-------------|------|
| `/api/health` | GET | 2545 | 健康检查 |
| `/api/discovery` | GET | 968 | 自动发现技能列表 |
| `/api/wallet/balance` | GET | 2382 | 查询钱包余额 |
| `/api/wallet/deposit` | POST | 2341 | USDC 充值 |
| `/api/wallet/withdraw` | POST | 2398 | USDC 提现 |
| `/api/wallet/fiat-deposit` | POST | 2451 | 法币充值（mock Stripe） |
| `/api/wallet/history` | GET | 2496 | 交易历史 |
| `/api/run` | POST | 2946 | 执行 Skill |
| `/api/auth/pre-check` | POST | 3105 | EIP-191 信标验证 |
| `/api/auth/api-keys` | GET/POST/DELETE | 3697/3705/3713 | API Key 管理 |
| `/api/tasks/pending` | GET | 1452 | PENDING 任务列表 |
| `/api/tasks/publish` | POST | 1970 | 发布任务 |
| `/api/tasks/claim-specific` | POST | 1463 | 抢单 |
| `/api/tasks/{id}/status` | GET | 3074 | 任务状态轮询 |
| `/api/tasks/{id}/simulate-fiat-payment` | POST | 1817 | 模拟付款 |
| `/api/tasks/{id}/boost-reward` | POST | 1868 | 加价 |
| `/api/tasks/{id}/vault-status` | GET | 1929 | Vault 状态查询 |
| `/api/worker/credit-score/{wallet}` | GET | 1509 | 信用分查询 |
| `/api/workers/heartbeat` | POST | 2526 | Worker 心跳 |
| `/api/developer/integrate` | POST | 1536 | 一键接入 |
| `/api/developer/integration/{wallet}` | GET | 1601 | 接入状态 |
| `/api/developer/set-contributors` | POST | 1617 | 贡献者分账 |
| `/api/licensing/request-key` | POST | 2694 | 买断授权 |
| `/api/skills/upload` | POST | 2608 | 上传 Skill ZIP |
| `/api/admin/audit` | GET | 2513 | 审计账本 |
| `/api/v2/feed/stream` | GET | 246 | SSE 实时结算流 |

### 5.2 未在 Console 中调用的相关端点

| API 路由 | Method | 功能 |
|---------|--------|------|
| `/api/commerce/subscription` | POST | 订阅购买 |
| `/api/commerce/buyout` | POST | 买断购买 |
| `/api/commerce/pricing/{skill_id}` | GET/POST | 定价查询/设置 |
| `/api/commerce/pools` | GET | 资金池状态 |
| `/api/commerce/phase` | GET/POST | 收入阶段查询/切换 |
| `/api/commerce/seed-plg` | POST | PLG 国库种子 |
| `/api/commerce/spend/{wallet}/{skill_id}` | GET | 消费追踪 |
| `/api/admin/setup` | POST | 测试数据种子 |
| `/api/admin/judge` | POST | AI Judge 测试 |
| `/api/admin/listener` | GET | 链监听器状态 |
| `/api/admin/circuit-breaker` | GET | 熔断器状态 |
| `/api/admin/emergency-pause` | POST | 全网紧急暂停 |
| `/api/admin/reset` | POST | 全局重置 |
| `/api/tasks/claim` | POST | 通用抢单 |
| `/api/tasks/submit` | POST | 提交结果 |
| `/api/tasks/{id}/pot` | GET | PoT 查询 |
| `/api/skill/task-action` | POST | 统一任务动作 |
| `/api/skills/register-developer` | POST | 注册开发者 |
| `/api/skills/register-metadata` | POST | 注册元数据 |
| `/api/worker/credit-score` | POST | 设置信用分 |

---

## 6 数据流模式

### 6.1 完整请求生命周期

```
用户点击按钮
  → JS 函数（参数收集 + 前端校验）
    → smartHeaders(body) 或 jwtHeaders()
      → fetch(API_URL, {method, headers, body})
        → server.py 路由处理
          → middleware 鉴权
          → 业务逻辑（database.py / broker.py / billing.py）
          → JSON 响应
      → 前端解析响应
    → DOM 更新 + toast 通知
```

### 6.2 认证降级策略

```
smartHeaders(body):
  1. if window.ethereum:
     signature = await signer.signMessage(body)
     return {X-Wallet-Address, X-Signature, X-Timestamp, Content-Type}
  2. else if localStorage.aims_jwt:
     return {Authorization: "Bearer <jwt>", Content-Type: "application/json"}
  3. else:
     return {Content-Type: "application/json"}  // 服务端决定
```

---

## 7 已知风险与修复建议

### 🔴 高风险

| # | 风险 | 影响按钮 | 修复建议 |
|---|------|---------|---------|
| R1 | `_currentVaultTaskId` Tab 切换丢失 | `simulateVaultPayment`, `boostReward`, `pollVaultStatus` | 在 `switchRole()` 中保存/恢复 `_currentVaultTaskId` |
| R2 | SyntaxError 导致整个 `<script>` 块不执行 | **所有 62 个按钮** | 已修复。使用 `node --check` 或 Prettier 做 CI 语法校验 |

### 🟡 中风险

| # | 风险 | 影响按钮 | 修复建议 |
|---|------|---------|---------|
| R3 | `claimTask` 信用分查询 `catch{}` 静默失败 | Claim 按钮 | `catch(e) { console.warn("credit score fetch:", e.message) }` |
| R4 | Admin audit 端点无角色校验 | Audit 按钮 | 添加 JWT 鉴权或 admin role check |
| R5 | Buyout 需要特定 task 状态 | Purchase Perpetual License | 前端添加状态检查和友好提示 |
| R6 | `saveContributors` DOM 动态行不稳定 | Save Split Config | 改为内存数组维护贡献者数据 |

### 🟢 低风险 / 信息性

| # | 风险 | 说明 |
|---|------|------|
| R7 | `smartHeaders({})` 对空 JSON 签名 | 用户可能不解 MetaMask 弹窗，可加 toast 提示"正在签名…" |
| R8 | Wallet 未连接时功能性按钮 pre-check | 大部分按钮已有 `if (!walletAddress)` guard |
| R9 | JWT 过期（7天） | 登录有效期有限，过期需重新登录 |

---

## 8 历史修复记录

| 日期 | 修复 | 影响 |
|------|------|------|
| 2026-06-17 | `const net` 重复声明 → `const currentNet` | 修复 SyntaxError，恢复所有按钮定义 |
| 2026-06-17 | `invokeSkill()` 多余 `}` 删除 | 第二个 SyntaxError 修复 |
| 2026-06-17 | 5 函数追加 `smartHeaders()` JWT fallback | 无 MetaMask 时按钮不再无反应 |
| 2026-06-17 | `fetchCreditScore`/`fetchIntegrationStatus` 静默 catch → `console.warn` | 调试可见性提升 |
| 2026-06-17 | `fetchDiscovery` `devSettlements` null guard | 消除 Console 初始化报错 |
| 2026-06-17 | API_BASE 默认值空字符串 | 修复 Fly.io 生产环境 API 相对路径 |
| 2026-06-17 | EXEMPT_PATHS + `_get_jwt_user_id()` | 修复 API Key 端点 401 |

---

*本文档由 Claude Code 自动生成，基于 `static/console.html` 和 `src/gateway/server.py` 的静态代码分析。*
