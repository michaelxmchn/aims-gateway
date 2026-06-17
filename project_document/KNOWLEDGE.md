<!-- AIMS Protocol | Version 1.0.0 | Last Updated: 2026-06-13 | Hermes-Verified -->

# 项目知识库

> **格式要求**: 严格遵循 `.claude/output-styles/markdown-focused.md` 格式规范

## 代码模式

### 路由鉴权分层策略
- **公开路由**：`/`（着陆页）、`/docs`、`/api/discovery`、`/api/health` — 无需任何认证，用户首访可见
- **JWT 保护路由**：`/console`（Web3 面板）— 缺失 JWT 时 302 重定向至 `/login`
- **API 三层鉴权**：所有 `/api/*` 端点按优先级依次尝试 JWT Bearer → API Key（`sk-aims-` 前缀）→ EIP-191 personal_sign 头部
- **商业动线设计**：用户通过 `/` 了解产品 → 点击 "Launch App" → 进入 `/console` 触发 JWT 检查 → 无令牌则重定向至 `/login` → 注册/登录后自动跳回 `/console`
- **EXEMPT_PATHS 端点 JWT 自解析**：`/api/auth/me`、`/api/auth/api-keys` 等端点在 EXEMPT_PATHS 中，middleware 跳过后 `request.state.user_id` 不会设置。使用 `_get_jwt_user_id()` helper 自行从 Cookie 或 Authorization header 解析 JWT 获取 user_id

### Console v2.1 Apple-style 单页仪表盘架构
- **`static/console.html`**（~778 行）— 单页仪表盘布局，无侧边栏、无 Tab 面板；顶部粘性状态栏（品牌/网络状态/区块/延迟/钱包连接）；Chart.js 可视化（revenueChart 折线图 + taskFlowChart 环形图 + System Health 红绿灯）；6 个操作卡片（Publish Task/Skills/Task Market/Auth & Settings/Activity/Worker Guide）点击触发 6 个全功能模态框；底部 Advanced Dev Mode 触发右侧抽屉面板
- **3 图表卡片**（`.dashboard-grid` 3 列）：Revenue 累计收益折线图 → `renderRevenueChart()` + 定时 `updateRevenueChart()` 模拟数据推送；Task Flow 环形图（Successful/Pending/Failed）；System Health 4 指标绿/红点（Gateway/Tasks OK/Workers/Treasury）+ `fetchHealth()` 刷新
- **6 业务模态框**：`bizModal-publish`（发布任务表单 + Task Vault + Boost ⚡ + Commerce Mode + 充值/提现）、`bizModal-skills`（Dev Stats 3 卡片 + Skill ZIP 上传 + One-Click Integration）、`bizModal-market`（Task Market 抢单池表格 + 刷新）、`bizModal-auth`（Profile/Password/Wallet/API Keys 四格面板）、`bizModal-activity`（Activity Log + Audit Ledger + User History）、`bizModal-worker`（Worker Node 3 卡片 + Co-Contributors + Canary Watermark）
- **Advanced Dev Mode 抽屉**（`devDrawer`）：右侧 480px 滑动面板，包含 Free Trial 状态、Credit Score 进度条+等级+AAA/AA/A/B/C 徽章、Invoke Skill 表单（技能选择/Payload/执行）、Settlement Feed 滚动列表、Skills 列表、Credit Score 条、CORS Docs、网络配置/节点路由配置
- **所有历史 DOM ID 保留**：每个旧 Tab 的 DOM ID 现在存在于对应模态框或抽屉中 — `getElementById()` 全局搜索仍能找到，`console-core.js` **零修改**
- **`static/css/console-v2.css`**（~665 行）— Deep Space 设计系统（`#0a0f1d` 背景，`#00dbe7` Electric Cyan 主色，`#ddb7ff` Neon Purple 次要）；`.app{display:flex;flex-direction:column;min-height:100vh}`（注意：必须使用 `column` 方向，否则 top-bar 与 dashboard-container 左右并排）；新增 `.dashboard-container`（全高滚动 1440px 居中）、`.dashboard-grid`/`.chart-card`/`.chart-container`（图表布局）、`.stats-row`（内联 6 指标行）、`.card-grid`/`.action-card`（hover 升起动画 + `box-shadow` 发光）、`.drawer`/`.drawer-overlay`（右侧抽屉 480px 滑入 `cubic-bezier` 动效）、`.modal-wide`/`.modal-scroll`（720px 宽模态 + 内部滚动）、1024px/768px 三档响应式断点
- **`static/js/console-core.js`**（~1715 行）— **零修改**，全部 52+ 业务函数通过 `getElementById()` 全局搜索找到模态框/抽屉中的元素正常工作；`switchSidebarTab()`/`switchRole()` 函数保留但无副作用（无对应 DOM 元素）
- **`static/js/docs-content.js`**（~44 行）— 平台文档文本，保持不变

### Tailwind CDN 已移除
- Tailwind Play CDN（`cdn.tailwindcss.com`）使用 `document.write` 动态注入脚本，在非初始页面加载场景下会导致 `"Unexpected token '}'"` 的页面错误
- 所有样式已完全由 `console-v2.css` 覆盖，无需 CDN
- 移除后消除该页面错误，实现 F12 Console 0 红色报错
- 保留 ethers.js CDN（必需，用于链上交互）
- **迁移原则**：`console.html` 保持纯骨架，所有逻辑在外部文件中，`DOMContentLoaded` 时填充文档文本

### Console DOM 元素空值防护
- **`getElementById()` 可能返回 null**：当 HTML 元素在特定 Tab（如 Developer Tab）才渲染时，跨 Tab 调用的 JS 函数需先 null 检查再访问
- **标准模式**：`const el = document.getElementById("xxx"); if (el) el.innerHTML = ...;` — 避免 `Cannot set properties of null (setting 'innerHTML')`
- **`fetchDiscovery()` 示例**：`devSettlements` div 仅在 Developer Tab 激活时存在于 DOM，`fetchDiscovery()` 在页面加载时被 `DOMContentLoaded` 调用，需 null guard 保护

### Bounty Adapter 多源聚合网关
- **`scripts/bounty_adapter.py`** — 从单一 Bountycaster 代理演进为 **MultiSourceAggregator**（`MultiSourceAggregator` 类），统一 `9812` 端口对外输出
- **Source A (Bountycaster)**：保留原有 `BountycasterClient` 轮询逻辑，`GET /api/v1/bounties/open` + `GET /api/v1/bounty/{hash}` 详情渲染
- **Source B (GitHub Bounties)**：新增 `GitHubBountyClient`，使用 GitHub Issues Search API 搜索 `(bounty OR reward OR "$" OR USDC) is:issue is:open`；`_extract_amount()` 多模式正则匹配从标题/正文提取赏金金额；支持 `GITHUB_TOKEN` 环境变量提升至 5000 req/hr（未设置时 60 req/hr）；3 页 90 条上限
- **`DedupEngine`**：按 `github_url` 去重，防止多平台挂单重复派单
- **`MIN_BOUNTY_USD = 10`**：硬编码开枪门槛，$10 以下任务直接过滤丢弃
- **绝对冷酷模式**：任务一旦进入 Docker 修复流程，连续重试 5 次依然报错 → 熔断放弃 → 自动切换下一单，严禁卡死或报警
- **统一输出格式**：`{id, title, description, github_url, url, repo_url, status, value_in_usdt, source}` 向 sniper 输出的标准 JSON 数组
- **Mock 数据**：6 条跨源 mock（3 Bountycaster + 3 GitHub Bounties），dry-run 46 条 Traces 41 ✅ 0 ⚠️ 0 🚨

### PyJWT 约束
- **`sub` 字段必须为 string**：PyJWT `decode()` 验签时要求 `sub` 是字符串，否则抛出 `Subject must be a string`。`create_jwt()` 中需 `str(user["id"])` 而非直接传 int。消费端用 `int(payload.get("sub"))` 转换回整数



### 认证模式
- **EIP-191 personal_sign 签名认证**：替代 HMAC-SHA256 和 EIP-712，所有 `/api/run`、`/api/tasks/claim`、`/api/tasks/submit`、`/api/wallet/*` POST 请求必须携带 3 个头部：
  - `X-Wallet-Address`（首选，推荐）或 `X-User-ID`（回退）：EVM 地址（0x + 40 hex）
  - `X-Signature`：EIP-191 personal_sign 签名（130 hex chars，无 0x 前缀）
  - `X-Timestamp`：UNIX 秒（300s 窗口防 replay）
- **Middleware 验证流程**：免认证路径跳过 → 调试日志打印 `Incoming headers` → 校验 EVM 地址格式 → 时间窗口（±300s）→ `encode_defunct(primitive=body)` → `Account.recover_message()` 恢复签名者 → 与 X-Wallet-Address 比对
- **大小写不敏感头部提取**：`_get_header()` 辅助函数依次尝试原始大小写 → `lower()` → `upper()` → 全量扫描匹配，应对 Fly.io/Nginx 等反向代理的头部大小写变换
- **调试友好 403**：缺失头部时，响应 body 包含 `detail`（列出具体缺失字段）和 `received_headers`（列出已接收到的所有 header key）
- **签名流程（客户端）**：`encode_defunct(primitive=body_bytes)` → `wallet.sign_message(signable_message)` → `signed.signature.hex()`（130 hex chars）
- **验签流程（服务端）**：`encode_defunct(primitive=body)` → `Account.recover_message(signable_message, signature=signature)` → 比对 recovered address 与 header
- **滑动窗口限流器**：`rate:limiter:{wallet_address}:{time // 60}` 键，`Storage.incr()` 原子递增，100 req/60s 阈值，120s TTL

### AIMS 链上架构模式
- **链上仅做两件事**：结算（扣分/加分）+ 计数器（+1 状态证明）
- **高频运行数据**：本地 Append-only Log 挡在前面，定期 Batch 上链
- **底链**：Base（EVM 兼容，低 Gas）
- **意图驱动路由**：万能入口 Skill 将用户需求拆解为 DAG 工作流，自动编排多个原子 Skill
- **Domain Detection**：通过关键词匹配将用户 Prompt 分类到 7 个领域（security/git/code/data/devops/writing/general）
- **Top-3 注入**：`get_top_for_domain()` 按 `Priority_Score = Frequency + (Staked × 10)` 排序，只注入匹配领域的前 3 个 Skill
- **EIP-191 personal_sign 认证**：用户钱包签署原始请求体 bytes，网关 middleware 通过 `encode_defunct` + `Account.recover_message` 恢复签名者比对 X-Wallet-Address，替代 EIP-712 typed data（更简单，无需 nonce/deadline）
- **Proof-of-Task (PoT)**：任务完成后网关 ECDSA 签署 `keccak256(taskId ++ workerAddress)`，Worker 持 PoT 调用合约 `claimReward()` 领取报酬
- **结算分账 (70/25/5)**：每笔成功任务按 70% 开发者 / 25% Worker / 5% Treasury 自动分配，开发者未注册时份额归 Treasury

### AIMS_GATEWAY_AUTH 信标验证
- **信标格式**：`AIMS_GATEWAY_AUTH:{wallet}:{skill_id}`，由 MetaMask 通过 `signer.signMessage(message)` 签署
- **`POST /api/auth/pre-check`**：免认证端点，接收 `{message, signature}`，使用 `encode_defunct` + `Account.recover_message` 恢复签名者并比对 `X-Wallet-Address`
- **前置验证**：在任务执行前调用，确保钱包持有者确认授权，日志记录验证结果

### SSE 实时结算流
- **`broadcast_settlement()`**：同步函数，由 `CommerceEngine._record()` 在线程池中调用，向线程安全 `deque(maxlen=200)` 附加结算事件
- **`_settlement_buffer_lock`**：`threading.Lock` 保护 deque 免受线程池并发写入
- **`GET /api/v2/feed/stream`**：异步 SSE 端点，每 2s 轮询 deque，以 `data: {json}\n\n` 格式推送新事件，空闲时发送 `: keepalive\n\n` 注释保持连接
- **前端消费**：`new EventSource('/api/v2/feed/stream')` 监听 `onmessage` 事件，解析 JSON 渲染至 UI 结算大屏；连接断开自动 5s 重连

### MetaMask 网络切换
- **Base Sepolia**：Chain ID `0x14a34`（84532），RPC `https://sepolia.base.org`，浏览器 `https://sepolia.basescan.org`
- **`wallet_switchEthereumChain`**：连接后检测当前网络，若非 Base Sepolia/Mainnet 则弹出 `confirm()` 询问是否切换；`wallet_addEthereumChain` 处理 4902 错误（链未添加）
- **合约部署底链**：Base（EVM 兼容，L2，低 Gas），USDC 6 位小数
- **部署脚本硬编码 PLATFORM_OWNER**：`scripts/deploy_settlement.js` 中 `PLATFORM_OWNER = "0x08c9fd0a915f2b0856353850b8adea943f226bcf"`（Solidity `immutable`，烧入合约字节码，永久不可更改）
- **Base 网络配置**：`hardhat.config.js` 包含 mainnet（chainId 8453）和 baseSepolia（chainId 84532）双网络，`DEPLOYER_PRIVATE_KEY` 环境变量注入

### AIMS CLI Schema 2×3 商业矩阵模式
- **MonetizationConfig 2×3 矩阵**：`function_type`（worker_collab/direct_skill）× `billing_mode`（pay_per_task/subscription/buyout），映射 Q1–Q5 象限
  - **Q1**（worker_collab + pay_per_task）：70% Developer / 25% Worker / 5% Platform
  - **Q2–Q5**（其他已验证组合）：95% Developer / 0% Worker / 5% Platform
- **风控熔断（Circuit Breaker）**：`MonetizationConfig._circuit_breaker_worker_buyout()` 使用 `@model_validator(mode="after")` 检测 `worker_collab + buyout` 组合，触发 `ValueError("【风控熔断】Worker协作模式依赖网络算力清算，禁止采用买断制！")`
- **三层校验链**：Pydantic v2 `mode="after"` 校验器按定义顺序执行 — (1) 熔断断路器 → (2) subscription 强制 rate_limit → (3) buyout 禁止 rate_limit
- **buyout（买断制）**：仅限 `direct_skill` 使用，无需 rate_limit_per_day，代表永久/终身许可证，publisher 审计表显示 "Perpetual (buyout)"

### Universal First-Task-Free PLG 协议
- **硬编码协议标准**：`AIMSConfig.enable_universal_free_trial` 通过 `@field_validator("enable_universal_free_trial")` 强制为 `True`，拒绝任何设置 `False` 的尝试
- **FreeTrialManager**（`src/gateway/trial.py`）：按 `(wallet_lower, skill_id)` 存储 `trial:{wallet}:{skill_id}` → int 使用计数器
  - `is_trial_eligible()`：使用量 < 1 返回 True
  - `consume_trial()`：原子递增，首次调用后在 `/api/run` 中触发
  - `enforce()`：统一入口 — 首次免费 → 计次；二次 → 按 billing_mode 验证支付证明；未通过 → `FreeTrialError` → HTTP 402
- **三种解锁模式**：
  - `pay_per_task`：二次之后由 `BillingEngine` 余额检查进行支付验证
  - `subscription`：`subscription:{wallet}:{skill_id}` → `{expires_at, ts}`，`time.time() < expires_at` 为有效
  - `buyout`：`buyout:{wallet}:{skill_id}` → `{purchased: True, ts}`，永久有效
- **网关集成**：`/api/run` 在 manifest 查找之后、余额检查之前插入 `_trial_manager.enforce()`，首次调用跳过余额检查（日志记录 `Free trial granted`）；`register_skill_metadata` 接受可选的 `monetization` 字典，持久化到 `skill:metadata:{skill_id}`；新增 `_get_skill_billing_mode()` 从存储中读取 billingMode，缺失时默认 `pay_per_task`

### 用户提现（Withdraw）流程
- **`POST /api/wallet/withdraw`**：EIP-191 认证 POST，请求体 `{user_id, amount}`，从用户余额扣除并记录 `tx_ledger` 条目（`type=withdraw`）
- **双模式扣减**：Web3 模式优先扣 `_local_deposits` 本地回退余额（因 on-chain withdraw 需用户自签）；InMemory 模式直接调 `_contract.withdraw()`
- **余额检查**：`get_user_balance() + _local_deposits` 合计校验，不足时返回 HTTP 402
- **前端入口**：`console.html` Recharge Reserves 面板底部 withdraw-row，输入金额 + `💸 Withdraw` 按钮

### 法币充值中继桥（Fiat/Stripe Bridge）
- **`POST /api/wallet/fiat-deposit`**：EIP-191 认证 POST，请求体 `{user_id, amount, card_token}`，mock Stripe 支付确认后自动 `deposit()` + `tx_ledger.record(type=deposit, method=stripe_mock)`
- **三档预设**：前端 `console.html` 提供 $25/$50/$100 Credit Card 按钮；后端始终成功（dev/test 模式），不调用真实 Stripe API
- **隔离原则**：法桥仅处理 USD→USDC 兑换，不接触链上合约的 `deposit()` 直接调用路径——用户真实的 MetaMask on-chain deposit 仍通过 `/api/wallet/deposit` 独立通道

### 用户历史账本（User History Ledger）
- **`GET /api/wallet/history?user_id=&limit=N`**：GET 免认证端点，代理至 `TransactionLedger.get_user_history()`，返回带 type/amount/timestamp/tx_id/description 的条目列表
- **`TransactionLedger`**（`src/gateway/ledger.py`）：`Storage` 持久化的 append-only 日志，`ledger:transactions:{tx_id}` 单条记录 + `ledger:user_txns:{user_id}` 反向索引（上限 200 条/用户）
- **自动入账路径**：`wallet_deposit` → `tx_ledger.record(type="deposit")`；`wallet_withdraw` → `tx_ledger.record(type="withdraw")`；`submit_task` → 计费结算（`type="task_deduction"`，由 `CommerceEngine`/`BillingEngine` 的 `_record()` 录入）
- **前端过滤**：`console.html` User History Ledger 面板支持 4 类过滤器（All/Deposits/Withdrawals/Tasks），`fetchHistory(typeFilter)` 通过 JS 端 filter 实现

### Console Vault 面板 Task ID 跨 Tab 保护模式
- **`_currentVaultTaskId` 作用域问题**：该变量在 `showVaultPanel()` 中设置，但在 Tab 切换（Consumer→Developer→Consumer）时会被清空，导致 vault 三个按钮（`simulateVaultPayment`、`boostReward`、`pollVaultStatus`）点击无反应
- **保护机制**：`switchRole()` 中添加 `_savedVaultTaskId` 备份变量，离开 Consumer Tab 时保存 `_currentVaultTaskId`，返回 Consumer Tab 时自动还原并通过 `vaultStatusBadge` DOM 元素更新 UI 状态提示
- **标准模式**：所有跨 Tab 需要持久化的状态变量应使用对应的 `_saved*` 备份模式，在 `switchRole()` 中统一管理

### Console 按钮白皮书
- **文件**：`project_document/AIMS_CONSOLE_BUTTON_WHITEPAPER.md`
- **内容**：62 按钮完整清单、50 JS 函数映射、25 API 端点映射、7 大核心操作像素级分析、认证架构（`smartHeaders` 降级链）、数据流全景、风险矩阵（🔴R1-R2 🟡R3-R6 🟢R7-R9）
- **用途**：为 Console 多标签页布局重构提供完整的交互资产清单与风险点记录

### AIMS 2.0 免质押政策（2026-06-16 生效）
- **核心原则**：Worker/卖方 **0 门槛加入**，彻底去除质押（Staking/Collateral）概念
- **前端 UI 净化**：所有 HTML 页面移除 "Worker Staking"、"质押余额"、"节点激活费"、"抵押金" 等元素和文案
- **防滥用替代机制**：
  - 纯 API/自动化脚本节点保留极低钱包余额验证（~0.1 USDC，仅验证不扣款），仅在后端执行，前端不展示为"质押惩罚"
  - 前端展示为 `防恶意 DDoS 验证`，非质押概念
- **质量保障**：AI Judge（LLM-as-a-Judge）评分 80/100 阈值 + 买方 Escrow 资金托管，替代传统质押抵押：
  - 卖家 0 门槛加入，靠 AI Judge 评分证明实力
  - 买家发单冻结 Escrow 防白嫖，AI Judge 仲裁失败自动退款
- **文档更新**：`index.html` Worker 角色卡 "3-strike collateral" → "Zero-barrier entry"；Worker 策略卡去除 staking 条款

### Hardhat 测试账户映射（关键）
- **Account #0 (Gateway EOA)**: `0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266` — 私钥: `0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80`
- **Account #1 (User)**: `0x70997970C51812dc3A010C7d01b50e0d17dc79C8` — 私钥: `0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d`
- **Account #2 (Developer)**: `0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC` — 私钥: `0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a`
- **Account #4 (Worker)**: `0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65` — 私钥: `0x47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926a`
- **重要**: Account #2 的常见错误私钥 `0x5de4111afa1a4b94908f83103eb1f15f0f8b1c7e3f5d8e8e3b7c5e8f4e2d8b0` 对应地址 `0x69BBBE8F...` **非** Account #2。末尾 `d8b0` → `ab365a` 才是正确值
- **Worker/Developer 需 ETH 付 Gas**：Account #2 和 #4 默认无 ETH，需从 Gateway EOA（Account #0）转账至少 1 ETH
- **MockERC20 mint 无访问控制**：任何人可调用 `mint(address, uint256)` 铸造测试 USDC

### Web3 链上结算模式
- **`ChainSettlement` 惰性初始化**：`settlement.py` 的 `contract` 属性根据 `AIMS_CONTRACT_ADDRESS` 环境变量自动选择实现 — sentinel `0x0...01` → `InMemorySettlementContract`（本地开发），真实地址 → `Web3SettlementContract`（生产/测试链）
- **`Web3SettlementContract`**：`contract_client.py` 中通过 web3.py v7 调用已部署的 `AIMSAgentGateway` Solidity 合约。读方法（`balances`、`pendingPayouts`）用 view 调用免 Gas，写方法（`settleTask`、`claimReward`）通过 `_send_tx()` 构建、签名（gateway EOA）并广播交易
- **`_send_tx()` 流程**：`fn_call.estimate_gas()` → `build_transaction()` → `acct.sign_transaction()` → `send_raw_transaction()` → `wait_for_transaction_receipt()`。使用 EIP-1559 费用市场（`maxPriorityFeePerGas`）
- **AIMSAgentGateway 合约**：`contracts/AIMSAgentGateway.sol` — 70/25/5 纯链上分账（`DEVELOPER_BPS=7000`/`WORKER_BPS=2500`/`TREASURY_BPS=500`），Gateway ECDSA 签名认证，Compound nonce（`keccak256(nonce, taskId)`）防重放，Task 生命周期状态机（None→Settled→Refunded/Claimed）
- **Hardhat 本地测试网**：`npx hardhat node` 启动 :8545，`npx hardhat run scripts/deploy_agent_gateway.cjs --network localhost` 部署。需注意 `--network hardhat` 使用内存网络而非持久节点
- **合约部署脚本**：`scripts/deploy_agent_gateway.cjs` — 同时部署 `MockERC20`（USDC，6 位小数）和 `AIMSAgentGateway`，Mint 1M MockUSDC 给 deployer，输出所有环境变量
- **测试用户预充值**：`scripts/fund_test_user.py` — Mint MockUSDC → Approve 合约 → Deposit 进入合约。使用 Hardhat 已知测试私钥
- **环境变量矩阵**：`AIMS_RPC_URL` / `AIMS_CONTRACT_ADDRESS` / `AIMS_USDC_ADDRESS` / `AIMS_GATEWAY_PRIVATE_KEY` / `AIMS_GATEWAY_ADDRESS` / `AIMS_TREASURY` 六项决定结算引擎行为
- **web3.py v7 兼容性**：`ContractFunction` 对象无 `estimate_transaction` 方法，使用 `estimate_gas()` 替代
- **`full_settlement_test.py`**：`scripts/full_settlement_test.py` — 完整结算生命周期验证。步骤：0) 给 Worker/Developer 铸造 MockUSDC；1) Gateway EOA 注册开发者到 skill；2) 用户调用 run_skill；3) Worker claim+submit；4) 链上核实 70/25/5 分账；5) Worker 通过 PoT 领取 25%；6) Developer 通过 PoT 领取 70%。已验证 0.05 USDC → 0.0125 Worker + 0.0350 Developer + 0.0025 Treasury 完整通路
### 审计追踪模式
- **`BillingEngine._audit_ledger`**：内存账本列表，记录每条状态流转。字段：`[ts, tx_hash, action, task_id, roles, amounts, detail]`
- **`_record()` 自动埋点**：`request_settlement()` 成功时自动记录 `action="settle"` 包含 user/worker/developer 角色和 70/25/5 分账金额；`request_refund()` 记录 `action="refund"`
- **`GET /api/admin/audit`** 查询端点，支持 `?task_id=<id>` 过滤和 `?limit=N` 控制条目数，同时返回 `summary` 聚合统计（总条目数、总金额、各 action 次数、最后一条记录）

### EIP-191 客户端签名模式（httpx 兼容）
- **关键注意事项**：不要使用 `httpx.post(json=body)` 配合预先计算的签名，因为 httpx 内部 JSON 序列化可能与 `json.dumps()` 产生不同字节。应使用 `body_bytes = json.dumps(body_dict).encode()` 先序列化 → 签名 → `httpx.post(content=body_bytes, headers={"Content-Type": "application/json"})`
- **`signed_post` 辅助函数模式**：`def signed_post(url, body_dict, wallet, key): body_bytes = json.dumps(body_dict).encode(); sig = Account.sign_message(encode_defunct(primitive=body_bytes), key).signature.hex(); return httpx.post(url, content=body_bytes, headers={"X-Wallet-Address": wallet, "X-Signature": sig, "X-Timestamp": str(int(time.time())), "Content-Type": "application/json"}, timeout=30)`
- **验证**：`content=body_bytes` 模式通过 200，`json=body` 模式返回 403（签名不匹配）

### PoT 检索模式
- **`GET /api/tasks/{id}/pot`** 获取 Proof-of-Task，用于 Worker/Developer 链上领取报酬
- **`?party=` 参数**：指定领取方 EVM 地址（0x 前缀），返回该地址对应的 PoT（含签名、金额、任务 ID）
- **无参数回退**：省略 `?party=` 时自动从 task status 查找 worker_id 并返回 Worker 的 PoT
- **Developer PoT**：显式传入 `?party=0xDeveloperAddress` 获取 70% 份额的 Developer PoT
- **PoT 存储 key**：`chain:pot:{task_id}:{party_address_lower}`，首次无参数调用会回退到 legacy key `chain:pot:{task_id}`（已弃用）

### 金丝雀（Canary）反盗版水印模式
- **`CanaryManager`**（`src/gateway/canary.py`）：ECDSA 签名水印系统，用于检测和阻止盗版 Worker 骗取结算
- **Token 生成**：`generate_token()` 产生 `canary:<timestamp_ms>:<random_hex>:<hex_signature>` 格式的 ECDSA 签名令牌，使用网关私钥签署 `keccak256()` 哈希
- **注入时机**：`POST /api/run` 在调用 `broker.publish_task()` 前将 `_canary_token` 注入 `req.params`，发布后调用 `record_task()` 持久化
- **Worker 透传**：Skill `logic.py` 需从 `params` 读取 `_canary_token` 并写入 `result_data`，以确保合法 Worker 携带水印返回
- **验证门**：`POST /api/tasks/submit` 在 JSON Schema 验证前调用 `verify_token()`，执行 ECDSA 签名恢复比对 + 重放检查
- **盗版熔断流程**：`MISSING_CANARY_TOKEN` / `CANARY_TOKEN_MISMATCH` / `CANARY_BAD_SIGNATURE` / `CANARY_REPLAY_ATTACK` → `FORBIDDEN_PIRACY` 阻止 70/25/5 分润 → `blacklist_worker()` 永久拉黑 → `complete_task("FAILED")`
- **Schema 剥离**：`_canary_token` 在 JSON Schema 验证前从 `result_data` 中剥离（`schema_input`），确保 stealth 字段不干扰 `output_schema` 校验
- **地址自动推导**：若 `gateway_address` 未显式提供，`CanaryManager` 构造时从 `gateway_signing_key` 通过 `Account.from_key()` 自动推导，消除 env 配置遗漏
- **存储 key**：`canary:token:{task_id}`（令牌记录）、`canary:used:{task_id}`（重放标记）、`canary:blacklist:{worker_id}`（黑名单）

### AIMS 2.0 轻量化路由与动态授权放钥模式
- **`LicensingManager`**（`src/gateway/licensing.py`）：基于网关私钥的单次随机种子密钥发放引擎
- **种子推导**：`keccak256(gateway_signing_key ++ task_id ++ user_address ++ os.urandom(32))` — 混合网关熵 + Task/User 绑定，确保种子既不可预测又可溯源
- **状态追踪**：`license:key:{task_id}` 存储记录含 `seed`/`task_id`/`user_address`/`status`/`ts`，`status` 为 `ACTIVATED_ONCE`（单次有效）
- **轻量化路由表**：`POST /api/skills/register-metadata` 记录 `skill_id`/`contributor_address`/`encrypted_source` 到 `skill:metadata:{skill_id}`，已注册时 409
- **请钥接口**：`POST /api/licensing/request-key` 三道强制校验：
  - **① Task 锁仓态**：通过 `broker.get_task_status()` 校验状态为 `CLAIMED` 或 `SUCCESS`（锁仓支付中）
  - **② EIP-191 钱包归属**：`X-Wallet-Address`（中间件已验签）与 `task_meta.user_id` 比较，不匹配 403
  - **③ 防重放**：`is_license_issued()` 检查 `license:key:{task_id}` 是否已存在，已发放 409
- **Discovery 集成**：新增 "Licensing & Routing" API 类别，暴露 `/api/skills/register-metadata` 和 `/api/licensing/request-key`

### aims-cli SDK 骨架模式（aims.config.json + 加密凭据）
- **`MonetizationConfig(BaseModel)`**（`src/cli/schema.py`）：2×2 收入矩阵引擎：
  - `function_type`：`Literal["worker_collab", "direct_skill"]` — Worker 协作网络 vs 本地直接执行
  - `billing_mode`：`Literal["pay_per_task", "subscription"]` — 按次计费 vs 订阅月费
  - `rate_limit_per_day`：`int | None` — 订阅模式下**强制必需**，`@model_validator` 检验
  - `quadrant_label()` 返回 Q1–Q4，`revenue_split()` 返回 `{developer, worker, platform}` 百分比
  - **收入矩阵**：Q1 (worker_collab+pay_per_task) = 70/25/5，Q2–Q4 = 95/0/5，Platform Treasury 恒 5%
- **`AIMSConfig(BaseModel)`**（`src/cli/schema.py`）：Pydantic v2 强类型 schema，8 个字段 + 嵌套 `MonetizationConfig`：
  - `skill_id` — 正则 `^[a-zA-Z][a-zA-Z0-9_-]*$`，1-64 字符
  - `version` — SemVer 正则 `^([0-9]+)\.([0-9]+)\.([0-9]+)$`
  - `developer_wallet` — EIP-55 格式 `^0x[a-fA-F0-9]{40}$`
  - `price_per_task_usdc` — float，`gt=0.0`，`le=1_000_000.0`
  - `monetization` — 嵌套 `MonetizationConfig`
  - `entry_point` — 默认 `"main.py"`
  - `output_schema` — JSON Schema 必须有顶层 `"type"` 字段
  - `gateway_url` — 正则 `^https?://`
- **文件 I/O**：`from_json_file()` 捕获 `FileNotFoundError`/`JSONDecodeError`，`to_json_file()` 输出缩进 JSON
- **加密凭据存储**（`src/cli/credentials.py`）：`~/.aims/` 目录 `0o700`，`~/.aims/credentials` 文件 `0o600`，使用 `Account.encrypt()` 生成以太坊 keystore v3 标准 JSON，`Account.decrypt()` 解密
- **Click CLI 骨架**（`src/cli/main.py`）：三个命令 — `init`（2×2 矩阵交互引导 + 收入分配预览）+ `login --private-key`（`Account.from_key` 预校验）+ `publish`（8 步管道 + ASCII 审计表）
- **入口点**：`bin/aims-cli` shell 脚本（`sys.path.insert` + `from src.cli.main import main`），与既有 `aims` 脚本一致

### 自定义 Skill 上传模式
- **zip 结构要求**：`manifest.json` + `logic.py` 必须位于 **zip 根目录**（非子目录内），且使用 `zip -j` 扁平压缩
- **`output_schema` 验证**：submit 时自动按 `output_schema` 验证 `result_data`，不匹配返回 `REJECTED`。`additionalProperties: false` 时拒绝任何未知字段
- **开发者注册**：上传后通过 `POST /api/skills/register-developer` 注册开发者地址，合约 settlement 时会查询 `skillIdHash → developer` 映射分配 70% 份额
- **Agent Hint**：`manifest.json` 的 `agent_hint` 字段提供自然语言指引，通过 discovery 端点暴露给 AI 客户端
- **AIMS_GATEWAY_PRIVATE_KEY 必需**：`request_settlement()` 使用此 key 对 settleTask 进行 ECDSA 签名，PoT 生成也依赖此 key。未设置时 `_sign_binding` 返回空签名导致 settleTask 失败

### Document-Driven 架构
- **子目录结构**：`skills/manifests/<skill_name>/manifest.json`（元数据）+ `rules.md`（Markdown 规则文件）
- **rules.md 即文档即代码**：纯 Markdown 格式，任何 AI（Claude/GPT/Codex）都能原生读取理解，无需自定义解析器
- **GatewayRouter 轻量上下文注入**：不再调用 LLM，过滤技能后拼接 rules.md 上下文字符串，由调用方注入
- **Sandbox 持有实现注册**：`SKILL_IMPLS` dict 映射 skill_name → Python callable，`resolve_impl()` 调度

## 常见问题

### Q: 待补充
A: 待补充

### Pipeline 任务链模式
- **BrokerTask** 新增 `pipeline: list[str] | None`（完整 skill ID 有序列表）和 `pipeline_step: int`（当前步骤索引，0-based）
- **自动推进**：`complete_task()` 在 SUCCESS 时检查 pipeline 是否还有未完成的步骤 → 将中间结果写入 Redis context 命名空间 → 递增 `pipeline_step` → 更新 `skill_id` 为下一步 → 重置状态为 PENDING 重新排队
- **延迟结算**：`submit_task()` 在收到 `settle=False` 的完成信号时不结算托管金，仅返回 `PIPELINE_CONTINUED` 响应；仅在最终步骤才调用 `release_escrow_dynamic()`
- **Context 存储**：`broker:context` Redis namespace，key 格式 `{task_id}:step_{step}`，存储当前步骤的中间结果供下游技能使用

### Agent Bootstrap 测试模式
- **`tests/test_agent_bootstrap.py`** 模拟外部 AI Agent 自引导流程，验证 7 个步骤：
  - **Step 1 (Discovery)**：`GET /api/discovery` 返回 200，包含 `documentation_root` URL 和 `skills` 列表
  - **Step 2 (Documentation)**：`documentation_root` URL（GitHub raw）可达，内容包含全部 7 个必需协议和关键技术主题
  - **两阶断言策略**：`REQUIRED_TOPICS`（7 个硬性主题必须全部命中: personal_sign/pipeline/discovery/heartbeat/bootstrap/70/25/5/settleTask）+ `ALTERNATIVE_TOPICS`（escrow/streaming/pot 任一命中即可，兼容架构演进）
  - **本地回退**：`_load_doc_content()` 优先远程 GitHub 获取，本地文件评分更高时自动回退，确保未推送的文档变更仍可通过测试
  - **Step 3 (Schema)**：每个技能有完整的 `input_schema`（`type`/`properties`/`required`），AI Agent 据此构造请求参数
  - **Step 4 (Auth)**：认证部分有 `example_curl` 示例，Agent 可直接适配
  - **Step 5 (Pipeline)**：`POST /api/run` 端点文档化，Agent 发现支持 pipeline 多步骤任务
  - **网络不可达降级**：`test_step2_documentation_root_reachable` 等远程测试在 GitHub raw URL 不可达时自动 `pytest.skip`，不影响本地 CI
- **`TestBootstrapDocumentation`** 验证 `AIMS_AGENT_BOOTSTRAP.md`（System Prompt 存在性）和 `bootstrap_helper.py`（客户端库存在性）

### Worker Schema-Aware Mock 模式
- **问题**：`run_aims_worker.py` 的 `execute_skill()` 输出固定 mock 格式 `{task_id, status, skill, output, timestamp}`，但不同 skill 的 `output_schema` 各异（如 `dashboard_skill` 需要 `status` + `message`），导致 `VALIDATE GENERIC FAIL` → 任务被 `complete_task("FAILED")` 永久标记 → 所有后续 worker 拿到 204
- **解决方案**：Worker 在 `execute_skill()` 中调用 `_fetch_output_schema(skill_id)` 从 `GET /api/discovery` 获取目标 skill 的 `output_schema`，`_build_mock_result()` 遍历 `properties` 按 type 生成合规 Mock 值（string→`"completed"`/`"mock_*"`，number→delay，boolean→true 等），`required` 缺省补全
- **回退安全**：discovery endpoint 不可达时返回 `{"status": "success", "message": "..."}` 通用格式，确保 worker 不崩溃

### Wallet 代理充值 — Web3 模式本地回退
- **问题**：Web3 模式下 `_contract` 为 `Web3SettlementContract`，其 `deposit()` 调用 Solidity `deposit(uint256)` 使用 `msg.sender` 作为充值地址。但网关使用 gateway key 签名交易，`msg.sender` = gateway 而非实际用户，且用户私钥不在网关口内，导致 500 崩溃
- **解决方案**：在 `server.py` 引入 `_local_deposits: dict[str, int]` 内存字典。Web3 模式下 `/api/wallet/deposit` 写入此字典而非调用链上 depsoit；`wallet_balance` 将链上余额 + 本地余额相加返回。以 `_is_web3_mode = isinstance(_contract, Web3SettlementContract)` 标志动态切换
- **模式**：代理充值只适用于测试/开发。生产环境用户直接通过 MetaMask 等钱包调用合约 `deposit()`，不经过网关

### Skill Logic 脚本分发
- **`skills/uploaded/{skill_id}/logic.py`**：`SkillStore` 从 `skills/uploaded/` 目录读取逻辑脚本，通过 `GET /api/skills/{skill_id}/logic` 分发给 Worker
- **`get_logic_source()`** 查找 `UPLOAD_BASE / skill_id / logic.py`（`skills/uploaded/{skill_id}/logic.py`），不存在则返回 404
- **内置 skill 补充**：`test_skill` 等内置 skill 默认无 `logic.py`，需在 `skills/uploaded/test_skill/` 手动创建并注册 manifest 到 Storage。`logic.py` 只需实现 `run(params, user_id, task_id) → dict` 接口，Worker 运行时动态加载调用

### AIMS 2.0 Commerce Matrix 多维计费模式
- **三种计费契约映射**：`CommerceEngine`（`src/gateway/billing.py`）实现 Mode-aware 结算路由
  - **Metered (pay_per_task)**：每次调用扣除消费者链上余额（默认 0.05 USDC），走原 `BillingEngine.request_settlement()` 路径 → `InMemorySettlementContract.settle_task()` 70/25/5 分账
  - **Subscription (订阅)**：`purchase_subscription()` 从消费者余额扣月费（默认 2.0 USDC），入 `pool:subscription` 池，每次调用从池中支付 Worker 带宽费（0.005 USDC）和开发者分成
  - **Buyout (买断)**：`purchase_buyout()` 从消费者余额扣终身授权费（默认 50.0 USDC），入 `pool:buyout` 池，每次调用仅支付 Worker 带宽费 + 平台税
- **RevenuePhase 收入分配合约**：`RevenuePhase` 枚举 `Q1`(70/25/5) / `Q2_Q5`(95/0/5)，通过 `POST /api/commerce/phase` 切换，`_split_bps()` 返回对应 BPS 三元组
- **PLG 首单免费补贴池**：`pool:plg` 命名空间，首次调用由国库种子基金（`POST /api/commerce/seed-plg` 注入）支付 70/25/5 全部分账；池耗尽时 fallback 到 Treasury
- **Pool 风险管理**：Subscription/Buyout 池余额不足时返回 `InsufficientPoolBalance` 错误 + 审计记录 `pool_shortfall`，防止负余额扣划
- **定价系统**：`skill:pricing:{skill_id}` 存储每种计费模式的单价（atomic units），未配置时使用 `DEFAULT_*` 默认值
- **消费者支出追踪**：`consumer:spend:{wallet}:{skill_id}` 记录累计消费 USDC 原子单位，通过 `GET /api/commerce/spend/{wallet}/{skill_id}` 查询
- **API 端点布局**：`/api/commerce/subscription`(POST)、`/api/commerce/buyout`(POST)、`/api/commerce/pricing/{skill_id}`(GET)、`/api/commerce/pricing`(POST)、`/api/commerce/pools`(GET)、`/api/commerce/phase`(GET/POST)、`/api/commerce/seed-plg`(POST)、`/api/commerce/spend/{wallet}/{skill_id}`(GET)
- **`SkillStore.register()`**：通过 `storage.dict_set(MANIFEST_NS, skill_id, manifest)` 注册 manifest，路径存在即可被 `serve_logic` 端点发现

### InMemoryContract 模块级单例模式
- **问题**：`wallet_deposit()` 和 `wallet_balance()` 每个请求中调用 `ChainSettlement(...)` 创建新实例 → `InMemorySettlementContract` 是纯内存对象，每次请求独立实例导致余额写后读不一致
- **解决方案**：在 `server.py` 模块级别创建一次 `_chain_settlement` 和 `_contract`（行 78-80），所有钱包端点直接使用全局 `_contract` 单例
- **模式**：`server.py` 模块加载时初始化 → 所有请求共享同一个 `_contract` 引用
- **生产环境**：切换到 `Web3SettlementContract` 后，每次请求通过 web3.py RPC 调用查询链上状态，不存在单例问题

### 多模态输入预处理模式
- **Base64 解码**：`_detect_base64()` 识别长度 ≥20 的 base64 编码字符串 → 解码为临时文件，通过文件头字节检测图像格式（PNG/JPEG/GIF/WebP）
- **URL 下载**：`_detect_url()` 识别 http/https/file 开头的 URL → `_download_to_temp()` 下载到临时文件，通过扩展名推断 MIME 类型
- **值替换**：原始字符串值替换为文件元数据 dict `{"_type": "file", "path": "...", "mime_type": "...", "size_bytes": N}`，技能 `execute()` 可直接读取 `path`
- **集成点**：`execute_dynamic_skill()` 入口处调用 `preprocess_multimodal(payload)`，对下游技能透明

### 品牌命名规范
- **正式品牌名称**：`AIMS Gateway`（非 `AIMS Network`、`AIMS Protocol`、`AIMS` 单独使用）
- **适用范围**：所有 UI 展示（Logo/标题/描述）、系统提示词、文档开头和结尾、开屏信息
- **内部代码引用**：包名、类名、模块名保持技术命名（如 `aims_worker`、`aims_gateway`），仅用户可见文本统一为 `AIMS Gateway`
- **例外**：`AIMS Protocol` 仅在法律/版权声明（footer Copyright）中使用，`AIMS` 作为缩写仅用于代码标识符
- **上次全局修正**：2026-06-16，覆盖 15 处引用于 HTML/MD/Python 文件

### 前端 UI 模式
- **无构建流水线**：所有 HTML 文件（`index.html`, `console.html`, `docs.html`）为纯内联 HTML+CSS+JS，零构建步骤，FastAPI `StaticFiles` 挂载 + 显式 GET 路由直接服务
- **Console 荧光绿主题**（`Theme_4`）：`--neon: #deff9a` 荧光绿强调色，深色 `#0f172a` 背景，`SF Mono` 等宽字体，终端风格 UI
- **拖拽上传模式**：`drop-zone` CSS class + `dragover/dragdrop/change` 事件监听 + `FormData` multipart 上传至 `POST /api/skills/upload`，EIP-191 签名认证头部
- **充值面板**：6 档预设金额（10/25/50/100/250/500 USDC）+ 自定义输入，调用 `POST /api/wallet/deposit`
- **审计账本**：`GET /api/admin/audit` 端点返回的 `ledger` 数组前端渲染为表格，支持 `?task_id=` 过滤和 `action` 分类显示
- **统一钱包连接**：所有页面通过 `ethers.BrowserProvider` + `eth_requestAccounts` 连接 MetaMask，签名使用 `signer.signMessage()`（EIP-191 personal_sign）
- **SSE 实时数据流**：通过 `EventSource` 连接 `/api/v2/feed/stream`，驱动首页结算大屏和控制台 Feed

### Bountycaster Sniper 自动狙击流水线
- **`scripts/gitcoin_sniper.py`**：四阶段全自动 Bountycaster（Farcaster 生态）赏金猎杀管道，零人工介入完成 "发现→评估→修复→交付" 闭环。已从废弃的 Gitcoin API 全面迁移至 Bountycaster 生态
- **BountycasterPoller**（替代 GitcoinPoller）：60s 间隔直接轮询 Bountycaster Next.js API — `GET /api/v1/bounties/open`（公开列表）+ `GET /api/v1/bounty/{hash}`（独立详情）；解析 `reward_summary`（token/unit_amount/usd_value）、`summary_text`（描述）、GitHub URL 正则提取；无任何 Gitcoin 死代码/API 回退/HTML 爬虫残留；`--dry-run` 模式提供 3 个真实历史 Bountycaster bounty（`bc-mock-001` 250 USDC Frame、`bc-mock-002` 8,000 degen TypeScript、`bc-mock-003` 1 USDC 社交拒绝）
- **AIMSEvaluator**：通过 `POST /api/run` 将 bounty 描述发送至 AIMS 网关大模型，**System Prompt 严格四条件门控**：①必须是可测的代码缺陷/修复/数据迁移 ②成功标准 = 测试套件通过 ③可完全由 LLM 代码智能体闭环 ④拒绝研究/文档/UX 设计类。响应格式：`MATCH:<confidence 0-100>:<rationale>`
- **CodeExecutor**：`git clone` → `claude -p "<prompt>"` 无头修复 → 自动检测项目语言 → **Docker 沙箱隔离执行测试**（`docker run --rm --network none -v <host_path>:/workspace <image> sh -c "<cmd>"`）；支持 `node:20-slim`/`python:3.12-slim`/`golang:1.23-alpine`/`rust:1.75-slim`/`ruby:3.2-slim`/`eclipse-temurin:21-jdk-alpine` 六种镜像 + `alpine:3.19` 兜底；Docker 不可用时优雅回退 `subprocess.run(shell=True)` + 日志警告；`SNIPER_DOCKER=0` 环境变量强制禁用
- **AutoDeliverer**：`git checkout -b aims-sniper/{id}` + commit + push + `gh pr create`；通过 `POST /api/skill/task-action` 推送 Action Traces 至仪表盘 SSE，触发 📈 收益图表更新或 🚨 异常告警
- **干运行验证**：`python3 scripts/gitcoin_sniper.py --dry-run --once` → 19 条 Action Traces，0 失败，2/3 匹配交付，$334 USDC

## 技术决策记录

### 决策1：链上架构最小化
- **背景**: 用户本地运行高频 Skill 调用，如果每条中间数据都上链会导致卡顿和高 Gas
- **决策**: 智能合约只做两件事——结算（扣分/加分）和计数器（+1）
- **原因**: 保证系统不卡顿，Gas 费可控，架构清晰

### 决策2：账户抽象方案
- **背景**: MVP 需要降低用户门槛，不能要求所有用户都有区块链钱包
- **决策**: 使用 ERC-4337/EIP-7702 账户抽象 + 会话密钥（Session Key），用户邮箱登录即可使用
- **原因**: AI 代理需要受限自动签名权——每次调用弹窗确认产品就死了

### 决策3：Skill 对齐 LLM Tool Calling 格式
- **背景**: 万能入口需要让 LLM 能原生选择和执行 Skill
- **决策**: `skill.json` 的字段直接映射为 Anthropic/OpenAI 的 Tool/Function Calling 格式（name/description/input_schema）
- **原因**: 不需要自定义解析器，LLM 原生支持函数调用，DAG 自动从工具链中产生

### 决策4：先积分后发币
- **背景**: 发币涉及复杂的经济模型设计、流动性池和合规
- **决策**: MVP 先用本地积分（off-chain Points）跑通流转，验证分配算法后一键映射上链
- **原因**: 不让发币逻辑卡住核心业务上线

### 决策6：优先级评分 = Frequency + Staked × 10
- **背景**: 新发布的 Skill 没有使用频率，无法在排序中获得展示机会
- **决策**: `Priority_Score = Usage_Frequency + (Staked_Points × 10)`，开发者质押点数获得 10 倍杠杆
- **原因**: 质押机制让优质开发者可以冷启动推广，同时质押点数也被用作质量保证金（失败罚没 2.0）

### 决策7：非托管托管结算（两步交易）
- **背景**: 需要保证用户和开发者在交易过程中都不会被欺诈
- **决策**: `freeze_points()` 先冻结 → `WorkflowEngine.execute()` 验证执行 → `settle_transaction()` 依据结果结算
- **原因**: 两步交易确保即使用户恶意不付款（冻结后不能撤回），或 Skill 执行失败（自动退款），双方资产安全

### 决策8：Cool-down Jail 自动惩罚机制
- **背景**: 低质量 Skill 如果持续失败，会浪费用户时间和算力
- **决策**: 连续失败 ≥ 3 次 OR 质押点数 ≤ 0 → 24h jail，`load_all()` 自动过滤
- **原因**: 自动化的质量保障机制，不依赖人工审核即可清除问题 Skill

### 决策9：Document-Driven 架构（rules.md 即文档即代码）
- **背景**: 之前的 Skill 只能通过 JSON manifest 定义输入输出，AI 无法理解技能的完整行为逻辑（限速规则、错误处理、隐私合规等）
- **决策**: 每个 Skill 子目录包含 rules.md 纯 Markdown 规则文件，GatewayRouter 将其注入 LLM 上下文，AI 原生读取后即可正确使用
- **原因**: JSON Schema 只能描述数据形状，无法表达操作规则。Markdown 是 AI 的原生理解格式，无需自定义解析器即可让任何模型（Claude/GPT/Codex）理解技能的全部行为约束

### 决策10：USDT JIT Escrow（Just-In-Time 托管结算）
- **背景**: 原先的 Points 系统仅是整数加减，无法真实模拟稳定币的现金流流转
- **决策**: MockLedger 改为 USDT 稳定币（浮点数，2 位小数），实现 JIT Escrow — `freeze_usdt()` 从用户余额扣减并存入 `escrow_vault`，`settle_escrow()` 根据执行结果分发
- **经济模型**: 成功收取 1% Platform Tax → `founder_treasury`，99% → developer；失败 100% 原路退回用户
- **现金流向审计**: `main.py` 第 7 阶段展示全流程现金流，确保系统中资金守恒（Seeded $100.00 = Alice $95.00 + Dev $4.95 + Treasury $0.05 ✓）

### 决策11：Dynamic Billing（Gas 计费 + 动态结算 + 并发安全）
- **背景**: 固定价格（price_points）无法反映真实执行成本，不同技能的执行时间和复杂度差异巨大
- **决策**: 引入 Gas 计费模型 — `BASE_GAS_RATE = 0.01 USDT/s`，`total_cost = execution_time × BASE_GAS_RATE + developer_premium`，上限 `max_budget`。`create_escrow_hold()` 预冻结预算上限，`release_escrow_dynamic()` 按实际执行时间结算
- **经济模型**: 成功时扣除实际成本（Gas + premium），1% Platform Tax → `founder_treasury`，99% → developer，未使用部分即时退还用户；失败时 100% 退还全部冻结预算
- **计费数据流**: `sandbox.WorkflowEngine.execute()` 测量 `execution_time`（wall-clock `time.time()`）→ `ExecutionReceipt.execution_time` → `MockLedger.release_escrow_dynamic()` 计算 Gas 和溢价 → 返回 `DynamicSettlementDetail` 分项账单
- **并发安全**: MockLedger 使用 `threading.Lock()` 保护所有状态修改操作，`total_system_wealth` 提供原子快照用于资金守恒验证

### 决策15：Proof of Result + Slashing Protocol（Worker 安全垫）
- **背景**: 恶意 Worker 可能提交假数据（坏 price、空 asin）或 Claim 任务后直接掉线，导致用户付费却拿不到正确结果
- **决策**: 引入三层安全机制 — (1) **Worker 注册质押**：`register_worker()` 冻结 $5 抵押金到 `_staked_collateral`；(2) **Proof of Result**：`validate_task_result()` 校验结果包含有效 `asin`（非空字符串）+ `price`（float > 0），失败自动记 strike；(3) **3-Strike Slashing**：`apply_penalty()` 累计 3 strikes → 削减 $1 抵押金 → `founder_treasury`，strike 计数器归零
- **惩罚触发点**: `check_timeouts()`（超时回收时联动 apply_penalty）+ Worker 循环执行后（validate_task_result 失败时自动记 strike）
- **财富守恒**: `_snapshot_wealth()` 包含 `_staked_collateral`，质押和削减均不影响系统总资产守恒审计

### 决策14：Stateful Task Claiming + Fault-Tolerance 超时回收
- **背景**: DePIN Worker 可能随时掉线（网络波动、机器重启），CLAIMED 任务如果无超时机制会永久卡死
- **决策**: TaskBroker 存储每个任务的状态字典（`PENDING → CLAIMED → SUCCESS/FAILED`），引入 `check_timeouts()` 后台线程：遍历所有 CLAIMED 任务，`time.time() - claimed_at > 5s` 自动 revert 到 PENDING。Worker 使用 `claim_task()` 原子抢占而非被动 pop
- **原因**: 状态机模型让 Broker 能检测 Worker 失联并回收任务，5s 窗口平衡了正常执行时间和故障检测延迟
- **关键模式**: Worker-3 模拟崩溃（claim 后 sleep 10s），Timeout Checker 每秒轮询，回收的任务由 Worker-1/2 重新抢占执行

### 决策12：并发压力测试 — 资金守恒审计
- **背景**: 并发环境下字典读写存在竞态条件，可能导致余额被覆盖或资金凭空消失
- **决策**: 创建 `tests/stress_test.py`，使用 `ThreadPoolExecutor` 模拟 10 个并发用户 × 5 次连续调用 = 50 笔并发交易，每笔经过 `create_escrow_hold → execute → release_escrow_dynamic` 全流程
- **验证**: 录制初始总资产 → 执行全部交易 → 录制最终总资产 → 断言 `初始总资产 == 最终总资产`（精度 4 位小数）
- **结果**: 50/50 成功结算，累计 $0.5000 平台税，$0.000000 差异，**WEALTH AUDIT: PASSED ✓**

### 决策13：DePIN 分布式 Worker 网络 + Task Broker
- **背景**: 单一节点执行无法扩展，真实场景需要多台机器/容器竞争执行技能并收取 Gas 费
- **决策**: 引入 `TaskBroker`（`gateway/broker.py`）作为中央线程安全 FIFO 队列，`publish_task()` 发布预授权托管任务，`poll_task()` 供 Worker 轮询。`runtime/sandbox.py` 新增 `start_worker_loop()` 后台守护线程，自动拉取任务 → 执行 → 调用 `release_escrow_dynamic()` 将 Gas 费记入自身 `worker_id`
- **经济模型**: Broker 负责分配，Worker 竞争拉取，Gas 费 + 开发者溢价按 Worker 实际执行量分布，1% Platform Tax 归 Treasury
- **验证**: 5 个 Worker 线程 × 30 个任务全自动排空，资金守恒 $0.000000 ✓，工作量分布 5–7 任务/worker，Gas 费正确分配到 5 个独立 `worker_id` 余额
- **背景**: 固定价格（price_points）无法反映真实执行成本，不同技能的执行时间和复杂度差异巨大
- **决策**: 引入 Gas 计费模型 — `BASE_GAS_RATE = 0.01 USDT/s`，`total_cost = execution_time × BASE_GAS_RATE + developer_premium`，上限 `max_budget`。`create_escrow_hold()` 预冻结预算上限，`release_escrow_dynamic()` 按实际执行时间结算
- **经济模型**: 成功时扣除实际成本（Gas + premium），1% Platform Tax → `founder_treasury`，99% → developer，未使用部分即时退还用户；失败时 100% 退还全部冻结预算
- **计费数据流**: `sandbox.WorkflowEngine.execute()` 测量 `execution_time`（wall-clock `time.time()`）→ `ExecutionReceipt.execution_time` → `MockLedger.release_escrow_dynamic()` 计算 Gas 和溢价 → 返回 `DynamicSettlementDetail` 分项账单

### 决策17：Compute Tier Billing（层级 Gas 计费）
- **背景**: 不同 Skill 的计算复杂度差异巨大，简单爬虫（Tier-1）和 AI 推理（Tier-3）不应按相同费率计费
- **决策**: 引入 `TIER_MULTIPLIERS = {1: 1.0, 2: 2.5, 3: 6.0}`，gas 公式改为 `gas_cost = exec_time × BASE_GAS_RATE × tier_mult`。`release_escrow_dynamic()` 改为接收 `skill_meta` 字典（含 `compute_tier`/`developer_premium`/`skill_id`），`compute_tier` 通过 `BrokerTask → publish_task → claim_task → skill_meta` 全链路传递
- **原因**: 层级计费让市场自动定价——简单任务便宜，复杂任务贵，激励开发者优化技能效率
- **验证**: Tier-2(2.5x) Worker 运行 4.0s，`gas = 0.01 × 2.5 × 4.0 = $0.1000` 精确匹配 ✓

### 决策19：Ephemeral Dashboard Skill（即席仪表盘）
- **背景**: AI 用户无法直观看到 DePIN 网络的运行状态——任务积压、财富分布、Worker 健康和削减事件都隐藏在日志中
- **决策**: 创建 `dashboard_skill`，通过 `_seed_ecosystem()` 实例化 MockLedger/TaskBroker，聚合实时指标（任务状态/财富分布/层级统计/质押/削减日志），渲染自包含 HTML（Tailwind CSS CDN + Chart.js CDN + 暗色主题），写入 `~/.aims/dashboard.html`，通过 `webbrowser.open()` 弹出浏览器
- **包含两张图表**: (A) 财富分布饼图（用户余额/Worker 质押/平台 Treasury）；(B) 按 Compute Tier 分组的任务柱状图
- **削减日志表**: Worker/原因/罚金/抵押金变化/时间戳，带红色高亮
- **CLI 入口**: `aims dashboard`（通过 `src/client/cli.py` 分发 + `aims` 包装脚本）

### 决策18：通用 JSON Schema 验证器（validate_result_generic）
- **背景**: 原有 `validate_task_result()` 硬编码校验 asin+price 两个字段，无法扩展为新技能类型
- **决策**: 创建 `validate_result_generic(result_data, schema, worker_id)` — 递归 JSON Schema 验证器，支持 `type`/`required`/`properties`/`items`/`minimum`/`maximum`，失败自动联动 `apply_penalty()` 削减协议
- **原因**: 通用验证器让每个 Skill 的 `output_schema` 定义自己的验证规则，不再需要硬编码。验证失败自动 strike，降低运营成本
- **验证**: corrupt 输出 `{"price": -10}`（缺少 required `products` 字段）被 JSON Schema 拒绝，Worker strike 0→1 ✓

### 决策16：Double-Sided Reputation + Outlier Truncation
- **背景**: 恶意用户或机器人可以刷低分操纵技能评分，单个 1 星评价可以显著拉低整体分数
- **决策**: 引入双层保护 — (1) **评分门控**：用户必须先成功使用过技能（有 `release_escrow_dynamic(skill_id=...)` 记录）才能评分；(2) **异常截断**：当技能评分 ≥ 5 条时，计算均值和标准差，`|rating - mean| > 2.5` 的评分被抑制（不追加到评分列表）；(3) **信誉惩罚**：提交异常评分的用户信誉 -0.1（下限 0.0）；(4) **加权评分**：`weighted_score = Σ(reputation_i × rating_i) / Σ(reputation_i)`
- **经济模型**: 用户信誉默认 1.0，每次异常评分 -0.1，低信誉用户的评分权重自动降低，形成自我修复的评分系统
- **验证**: 5 个诚实用户评分 5.0 + 1 个恶意用户评分 1.0（|1.0-5.0|=4.0 > 2.5 → 抑制），恶意用户信誉 1.0→0.9，加权评分保持 5.0 ✓

### MCP 协议集成模式
- **MCP stdio 服务器**：`src/client/mcp_server.py` 实现 Model Context Protocol over stdio，AI 客户端（Claude Code/Cursor）通过 stdin/stdout JSON-RPC 发现和调用 AIMS Skill
- **工具自动发现**：`tools/list` 返回 `SkillRegistry.get_all_manifests()` 的完整工具列表，`tools/call` 通过 `WorkflowEngine.execute()` 执行 Skill
- **无需 SDK**：直接实现 JSON-RPC 2.0 协议（initialize/tools/list/tools/call），零外部依赖

### User Identity Map 模式
- **Email → Wallet 绑定**：`src/chain/settlement.py` 的 `user_identity_map` 将用户 email 映射到钱包地址和会话密钥
- **法币入金桩**：`simulate_stripe_webhook()` 模拟 Stripe `payment_intent.succeeded` 事件，种子用户 USDT 余额

### 决策5：信任模式 + 串行执行
- **背景**: MVP 要快速验证核心路由逻辑
- **决策**: 沙箱隔离不做（信任模式，仅种子开发者）+ 串行执行（不做并行 DAG）
- **原因**: 沙箱和并行调度会增加数倍复杂度，MVP 场景线性的就够用了

### AIMSAgentGateway 生产级合约架构
- **70/25/5 三方分账**：70% 开发者（Skill 作者）、25% Worker（带宽执行者）、5% Treasury（协议可持续性），替代旧版 80/20 分账
- **Compound Nonce 防重放**：`keccak256(abi.encodePacked(nonce, taskId))` 复合索引，即使 nonce 或 taskId 单独重复也不可重放
- **Task 生命周期状态机**：`None → Settled → (Claimed | Refunded)`，三种状态互斥，防双重索赔/退款
- **超时退款保护**：`refundTask()` 仅 Gateway 可触发，`MAX_TIMEOUT = 300s` 窗口，自动撤销结算并归还用户
- **开发者注册表**：`skillIdHash → developer address` 映射，Gateway 通过 `registerDeveloper()` 注册，settleTask 时自动查表分配 70% 份额
- **TaskSettlement 快照**：存储任务完整结算记录（worker/developer/各份额/时间戳），供各方独立 claim

### Raw ECDSA 签名模式（Hardhat / Solidity ECDSA.recover）
- **不要使用 `wallet.signMessage()`**：该函数添加 `\x19Ethereum Signed Message:\n32` 前缀，Solidity `ECDSA.recover()` 期望的是 raw hash 签名
- **正确做法**: `wallet.signingKey.sign(ethers.getBytes(hash))` 执行 raw ECDSA 签名，返回的 `Signature` 对象通过 `ethers.Signature.from(sigObj).serialized` 序列化为 `(r, s, v)` 65 字节 hex
- **Python 对应**: `Account.unsafe_sign_hash(message_hash, private_key)` 产生兼容签名
- **Solidity 对应**: `ECDSA.recover(keccak256(abi.encodePacked(...)), signature)` 直接验证

### 跨平台 Hash 一致性约束
- **Solidity `keccak256(abi.encodePacked(...))`** 必须与 **Python `eth_utils.keccak(bytes_concat(...))`** 产生相同结果
- **PoT hash 三平台一致**: `keccak256(abi.encodePacked(taskId, workerAddress, amount))` — Solidity、Python POTManager、Python InMemorySettlementContract 使用完全相同计算
- **Settlement hash**: `keccak256(abi.encodePacked(taskId, user, worker, amount, nonce))` — Solidity 和 Python `_sign_settlement()` 匹配
- **关键**: `to_canonical_address()` 将 `0x` 地址转换为 20 字节；`amount.to_bytes(32, 'big')` 生成 32 字节大端表示

### Hardhat 测试模式
- **测试文件用 `.cjs` 扩展名**：`package.json` 有 `"type": "module"`，CommonJS 测试文件必须用 `.cjs`
- **config 文件用 `.js`（ESM）**：`hardhat.config.js` 使用 `import`/`export default`
- **MockERC20 部署**: `MockERC20.deploy("USD Coin", "USDC", 6)` — 6 位小数匹配 USDC
- **Signer 管理**: `ethers.getSigners()` 返回 `[fundingSigner, user, worker, owner]` — 索引 0 为 default 签名者，用于资助 `ethers.Wallet.createRandom()` 创建的 gateway wallet

### 决策20：E2E 集成测试 8 阶段全链路验证
- **背景**: 单一机制的单元测试无法捕捉机制间的交互问题（如 staking 后削减、冻结资金释放后的财富守恒）
- **决策**: `tests/e2e_integration_test.py` 定义 8 阶段流水线：Account Abstraction → Developer Registration → Worker Staking → Fault Tolerance → Slashing → Tier-2 Billing → Wealth Audit → Dashboard
- **验证模式**: 11 个检查点覆盖所有经济机制，最终断言 `accounted == initial_wealth`（$180.00 == $180.00）
- **原因**: 端到端测试是发现跨机制资金泄漏的唯一可靠手段，wealth audit 捕获任何未结算或错误分配

### 决策21：Gateway Server（FastAPI HTTP 网关）
- **背景**: DePIN Worker 需要远程 HTTP 接口来拉取任务和提交结果，不能直接访问 Python 内部的 TaskBroker
- **决策**: `src/gateway/server.py` 用 FastAPI 实现三个端点 — `POST /api/tasks/claim`（Worker 拉取 PENDING 任务）、`POST /api/tasks/submit`（Worker 提交结果，触发 JSON Schema 验证 + tier-based gas 结算 + slashing）、`GET /api/health`（健康检查）
- **模式**: 全局单例 `ledger`/`broker`/`registry`，同步 broker/ledger 调用通过 `loop.run_in_executor()` 跑在线程池中，不阻塞事件循环
- **原因**: FastAPI 的 OpenAPI 文档自动生成，Worker 可以用任何 HTTP 客户端接入，无需 Python SDK

### 决策22：HMAC-SHA256 签名认证 + Replay 保护
- **背景**: Gateway Server 暴露在 HTTP 上，未认证的端点任何人都可以 claim/submit 任务，可能导致 Worker 冒充或重放攻击
- **决策**: 使用 `@app.middleware("http")` 对所有 `POST /api/tasks/*` 请求进行签名验证 — `Signature = HMAC-SHA256(secret, body + "|" + timestamp + "|" + user_id)`，`X-Timestamp` 必须在服务端时钟 300s 窗口内。签名缺失/过期/无效返回 403
- **模式**: 常量时间比较 `hmac.compare_digest()` 防止 timing attack；`/api/admin/setup` 和 `GET /api/health` 豁免签名认证
- **原因**: 轻量级对称签名方案，无需 PKI 或 OAuth 基础设施，适合 DePIN Worker 网络中的机器间认证

### 决策23：Fly.io 生产部署（Docker + 最小化容器）
- **背景**: AIMS Gateway 需要部署到生产环境，提供公网 HTTP 端点供 DePIN Worker 远程连接
- **决策**: 使用 `python:3.11-slim` 基础镜像（~120MB），`requirements.txt` 锁定 fastapi==0.134.0 / uvicorn[standard]==0.41.0 / pydantic==2.12.5，`.dockerignore` 排除 CI/测试/文档文件减少构建上下文
- **Fly.io 配置**: `fly.toml` 设定 `internal_port=8000`，`min_machines_running=1` 保持网关常驻，`auto_stop_machines=false` 防止空闲休眠，sin（新加坡）区域降低亚太延迟
- **原因**: Fly.io 支持 Dockerfile 直接部署、自动 HTTPS、按需付费，适合 DePIN 网络的全球分布 Worker 接入

### 决策24：Redis 状态持久化 + Storage 抽象层
- **背景**: MockLedger 和 TaskBroker 所有状态存储在 Python 内存 dict 中，Fly.io 容器重启（部署/扩容/崩溃恢复）会导致任务队列和账本数据全部丢失
- **决策**: 创建 `src/gateway/storage.py` `Storage` 类 — 读取 `REDIS_URL` 环境变量，有 Redis 时使用 `redis.from_url()` 连接并持久化（`decode_responses=True`），连接失败时自动降级为 `threading.Lock()` 保护的内存 dict。所有值通过 `json.dumps/loads` 自动序列化，支持 `get/set/delete/exists/keys/flushdb`
- **模式**: 自动降级（fail-open） — 本地开发无需 Redis，`fly redis create` 创建实例后自动注入 `REDIS_URL` 环境变量，Storage 在下次启动时无缝切换为持久模式
- **原因**: 最小侵入式设计 — Storage 抽象层让账本和 Broker 的 Redis 改造可以分步骤进行，不阻塞部署进度

### 决策27：Redis 持久化 — 写时复制 + dict namespace 模式
- **背景**: MockLedger 和 TaskBroker 所有状态在内存 dict 中，容器重启（部署/扩容/崩溃恢复）导致全部丢失。只有 1 台 Fly.io 机器，不需要分布式锁
- **决策**: Storage 抽象层（`src/gateway/storage.py`）提供 `dict_set/dict_get/dict_all` 等 namespace 操作，Redis key 格式为 `{namespace}:{key}`（如 `broker:tasks:task-0001`、`ledger:user_balance:alice`）。Broker 和 Ledger 保持内存 dict 作为主存储，每个突变后在同一个 `with self._lock` 内写透 Redis
- **启动恢复**: `_load_state()` 调用 `dict_all(namespace)` 全量加载该 namespace 下的所有 k-v 对，按类型（`FreezeReceipt`/`EscrowHold`/`DynamicSettlementDetail`）反序列化重建内存对象
- **写时复制模式**: 写入 Redis 在锁内执行（串行化），不阻塞事件循环。`is_persistent` 属性区分 Redis 模式和内存模式，无 Redis 时行为零变化
- **覆盖范围**: Broker 4 个 namespace（tasks/status/results/counter）+ Ledger 13 个 namespace（user_balance/dev_balance/escrow_vault/treasury/counter/collateral/strikes/skill_usage/reputation/rating_history/rating_entries/skill_score）
- **原因**: 单机无需分布式锁，写时复制保证内存和 Redis 一致性。`dict_all` 全量加载适用于小数据量（MVP 阶段 < 10K 任务），后续可以加增量同步

### 决策28：动态 Skill 插件系统（上传 → 引导 → 执行）
- **背景**: 静态 manifest 技能无法热加载，每次新增技能都需要修改代码和重启服务器，且 Worker 固定逻辑无法扩展新能力
- **决策**: 三层动态插件架构 — (1) **SkillStore**（`src/gateway/skill_store.py`）处理 zip 上传：zip-slip 防护、10MB 限制、manifest 校验、Pydantic 验证，元数据存 Redis，`logic.py` 写 `skills/uploaded/{skill_id}/` 磁盘；(2) **Registry 运行时注册**：`install_skill()` 将动态 SkillManifest 注入缓存（修复 `_cache` 为 None 的边界），`load_into_registry()` 启动时自动恢复已上传技能；(3) **Worker Bootstrap**（`src/worker/bootstrap.py`）：`fetch_logic()` 通过 HMAC 签名 GET 请求下载远程 `logic.py`，`_load_and_execute()` 用 `importlib.util.spec_from_file_location()` 编译临时文件 + exec_module() 执行 + 清理，最后调用 `module.execute(payload)` 返回结果
- **API 端点**: `POST /api/skills/upload`（multipart zip 上传，免 HMAC）、`GET /api/skills/{id}/logic`（源码服务，HMAC 保护）、`POST /api/run`（输入 schema 校验 + escrow + 发单）、`GET /api/tasks/{id}/status`（轮询结果）
- **Claim 响应增强**: `skill_logic_url` 字段携带完整 URL（基于 `request.base_url`），Worker 零配置即可定位技能代码
- **Worker 执行策略**: `execute_task()` 检查 `payload` 字段 — 有 payload 走动态引导（fetch → importlib → execute），无 payload 回退 mock（静态技能兼容）
- **HMAC 扩展**: 中间件覆盖除 `/api/admin/` 和 `/api/health` 外的所有 `/api/*` POST 请求，以及 `/api/skills/*` GET 请求（逻辑代码保护）
- **E2E 验证**: 9 阶段测试全通过（上传→/api/run→claim→bootstrap→submit→SUCCESS ✓），`greeting: "Hello, AIMS!"` 正确返回

### 决策26：生产级 E2E 全流程测试（tests/e2e_full_flow.py）
- **背景**: 负载测试（stress_test.py / load_test_simulation.py）侧重于后端并发和资金守恒，缺少模拟真实生产环境下多 Worker 独立网络出口和长运行时的端到端验证
- **决策**: 创建 `tests/e2e_full_flow.py`，使用 `concurrent.futures.ThreadPoolExecutor` 启发 10 个 Worker 线程，每个 Worker 使用独立 `worker_id` 和可选 SOCKS5 代理出口。Worker 循环执行 `claim→2s 浏览器指纹模拟→submit` 全流程，所有请求携带 HMAC-SHA256 签名。运行时默认 60s，结束时汇总吞吐量、错误日志和成功率
- **代理轮换**: 通过 `AIMS_PROXY_PORTS=7890,7891,7892` 启用 SOCKS5 轮换，每个 Worker 随机选取一个代理端口，`_detect_egress_ip()` 调用 `api.ipify.org` 打印每个 Worker 的出站 IP，方便验证多网络出口
- **错误诊断**: 提交失败时记录完整 HTTP 状态码和响应体 `detail` 字段（Pydantic 验证错误/FastAPI 异常），帮助用户调试生产连接问题
- **双模式**: 无参数时启动本地 uvicorn 实例 + seed 数据后运行；设 `AIMS_GATEWAY_URL` 环境变量时直接连接生产网关（需确保已有任务数据）
- **原因**: 端到端的代理出口验证和 60s 长期运行，比纯本地单元测试更接近生产环境，能发现网络层和签名层的问题

### 决策29：Auto-Discovery 协议（GET /api/discovery）
- **背景**: AI 代理（Claude/GPT/Cursor 等）首次接入 AIMS Gateway 时，需要理解完整的 API 表面——有多少端点、每个端点做什么、如何认证、请求体格式是什么。手动阅读 OpenAPI 文档耗时且不通用
- **决策**: 在 `/src/gateway/server.py` 中实现 `GET /api/discovery` 端点，返回一份**自文档化 JSON**，包含：(1) `discovery_version` 协议版本号；(2) API 元信息（名称/版本/描述）；(3) 服务器时间（当前时间戳）；(4) HMAC 认证说明（scheme + 算法伪代码 + 三个必需请求头 + cURL 示例）；(5) `skills` 数组——动态扫描 `registry.get_all_manifests()` + `skill_store.list_skills()` 构建的活跃技能列表，每个 skill 包含 `skill_id`/完整 `manifest`（input_schema、output_schema、version、tags）/`endpoint`（/api/run）/`auth_type`（HMAC-SHA256）/`source`（built-in 或 uploaded）；(6) 按类别分组的端点列表；(7) links；(8) notes
- **设计原则**: "如果我是 AI，我一眼就能看懂怎么调这个接口" — 每个端点的 `request_schema` 包含完整的 `type/required/properties` 字段，`authentication` 部分给出 `algorithm` 伪代码和可直接运行的 cURL 示例
- **安全策略**: `/api/discovery` 公开可访问（豁免 HMAC 签名），不暴露任何敏感数据（密钥/密码等）
- **原因**: 自动发现协议让任何 AI 客户端在首次连接时就能获得完整的 API 使用指南，无需预配置或读取外部文档。结构化 JSON 比自然语言文档更适合程序化消费

### 决策30：AIMS Agent Bootstrap 协议
- **背景**: 外部 AI 代理（Claude、GPT、Codex 等）需要一份清晰的接入指南，包含 System Prompt、认证算法和代码实现，才能以 Worker 身份参与 AIMS 网络
- **决策**: 创建 `AIMS_AGENT_BOOTSTRAP.md`，包含三部分：(1) **System Prompt 块**——可直接复制到 AI 代理的 Custom Instructions，指令代理在每次会话开始时调用 `GET /api/discovery`，解析 JSON 理解可用技能和认证要求，根据用户自然语言请求映射到对应 `skill_id`，构造 HMAC 签名并执行；(2) **`bootstrap_helper.py`**——Python 封装类 `AIMSClient`，提供 `discover()`/`list_skills()`/`find_skill()`/`run_skill()`/`heartbeat()` 方法，自动处理 discovery → HMAC 签名 → run → poll 全流程，支持 CLI 调用（`python bootstrap_helper.py list` 和 `run`）；(3) **使用说明**——Step 1 设置网关地址、Step 2 粘贴 System Prompt，以及 Claude Code/Cursor/GPTs/Python 脚本的集成方法
- **Agent 接入流程**: `GET /api/discovery` → 解析 skills → 匹配 skill_id → `POST /api/run`（HMAC 签名） → 轮询 `GET /api/tasks/{id}/status` → 返回结果
- **原因**: 无需 SDK 依赖，任何 HTTP 客户端 + 标准库 `hmac` 即可接入。System Prompt + 代码双重保障，确保 AI 代理能以最少配置成为 AIMS Worker

### 决策25：Worker 心跳机制
- **背景**: 生产环境中 Gateway 需要知道哪些 Worker 还活着，以便在 Worker 掉线时及时将任务重新分配给其他 Worker
- **决策**: 新增 `POST /api/workers/heartbeat` 端点，Worker 每 15s 发送一次心跳（HMAC-SHA256 签名）。Gateway 在内存中维护 `worker_id → last_seen_unix_ts` 映射，超过 60s 未报告的 Worker 被标记为不活跃。`GET /api/health` 新增 `workers_active` 字段反映当前活跃 Worker 数
- **Worker 端实现**: `src/worker/worker.py` 中的主循环独立于任务处理逻辑，每 `HEARTBEAT_INTERVAL` (15s) 调用 `send_heartbeat()`，心跳失败不阻塞任务处理
- **原因**: 轻量级心跳避免了 TCP keepalive 的代理兼容性问题，HTTP 层的签名心跳还可以作为 Worker 身份合法性验证

### Credit & Revenue 信用计费模式（Layer 3.5）
- **BillingEngine**（`src/gateway/billing.py`）— 平行信用计费层，独立于 USDT Escrow 系统
- **COST_PER_TASK = 0.05** 固定信用单价，各任务同价
- **Revenue Split** — 成功时 80% Worker + 20% Gateway Owner，Worker 与 Owner 同一实体时全额归 Worker
- **Reservation 模式** — `reserve_credits(task_id, user_id)` 预授权 COST_PER_TASK 存入 reservation `{"user_id": ..., "amount": ..., "timestamp": ...}`，settle 时读取 reservation 确定扣费来源
- **双路径原子结算** — Redis 可用时通过 Lua 脚本（`EVAL`）跨 5 个 Key 原子操作；Redis 不可用时通过 `Storage.pipeline()` + `threading.Lock()` 内存事务回退
- **Idempotent Receipt** — `settle_task()` 第二次调用时 reservation 已删除，自动查找 `billing:reserved:receipt:{task_id}` 返回已有收据，防止双花
- **TransactionLedger**（`src/gateway/ledger.py`）— 追加式交易历史，支持四类交易（deposit/task_deduction/worker_payout/owner_revenue），每用户索引最近 200 条，`get_all()` 全局排序查询
- **Wallet API** — `POST /api/wallet/deposit`（HMAC 保护）+ `GET /api/wallet/balance`（HMAC 保护），通过现有 `/api/` 中间件自动认证

### TikTok Shop 竞品情报 Skill 模式
- **`src/skills/tiktok_competitive_intel.py`**：马来西亚/东南亚 TikTok Shop 竞品情报监控智能体，面向 Shopee/Lazada/TikTok Shop 三个平台
- **确定性 Mock 架构**：`random.Random(keyword + market)` 种子化 RNG，确保同一查询返回可复现的合成数据，适合 Schema 演示和管道测试
- **六类产品模板**：`PRODUCT_TEMPLATES` 包含护肤品（Vitamin C Serum）、美容仪器（LED Mask）、电子配件（Magnetic Cable）、厨房用品（Air Fryer Liners）、保健品（Collagen Gummies）、家电（Stand Mixer），覆盖 SEA 跨境电商热门品类
- **多维度输出**：`competitor_metrics`（价格/销量/评分/卖家维度）、`fraud_risk_score`（5 种欺诈信号启发式检测：评论时间异常/价格偏离/新店高增长/库存不匹配/图片复用）、`market_insights`（品类趋势/广告主分析/推荐定价区间）
- **Fraud Screening 启发式**：价格 < 均价 40% → `price_anomaly_detected`；评论/销量比 < 0.3 且评论 > 500 → `review_manipulation_flag`；随机 12% 新店检测 → `seller_account_age_lt_30_days`。aggregation 按可疑数量分级：>5 → `critical` / >3 → `high` / >1 → `medium`
- **`execute(params)` 单一入口**：遵循 AIMS Skill 标准接口，接收 `params` dict 返回严格匹配 `output_schema` 的 JSON，`fraud_screening` 默认开启
- **`manifest.json` Commerce Matrix 定价**：`price_points: 5`（Metered 等价 0.05 USDC）、`staked_points: 20.0`（冷启动推广）、tags 含 10 个分类标签（tiktok/shopee/lazada/ecommerce/competitive_intel/sea/malaysia/ad_intelligence/fraud_detection），`agent_hint` 提供中文 AI Agent 指引

### E2E Testnet Simulation 双流联动测试模式
- **`tests/e2e_testnet_simulation.py`**：综合性仿真联动测试，模拟 Base Sepolia 测试网（或 in-memory）全链路结算流程，Bloomberg 终端风格彩色日志输出
- **双流商业故事**：Flow 1 (PASS) = PLG First-Task-Free 网关拦截 → DRM PyArmor+AES-256 包装执行 → AI Judge 92/100 → 70/25/5 PLG 国库补贴池结算；Flow 2 (REFUND) = 回归钱包 Metered 模式 → 网络劣化导致输出残缺（`status="partial"`, 缺 `market_insights`）→ AI Judge 74/100 (< 80 SLA) → 合约退款 → 消费者余额不变
- **AI Judge 评分引擎**：`evaluate(result, tampered=False)` → (score, verdict, reason)。扣分规则：status 缺失 25pts、competitor_metrics 缺失 20pts、top_competitors 缺失 15pts、fraud_risk_score 缺失 15pts、market_insights 缺失 10pts、volume <5 减 5pts、恶意篡改 50pts hard cut。阈值 80/100 = SLA 仲裁分界线
- **DRMWrapper 模拟三层 DRM**：`_pyarmor_load()` 加载混淆桩（wrapper.so 模拟）+ `_aes_decrypt()` AES-256-GCM 解密 logic.enc → `execute_skill()` 执行 + `_checksum_verify()` 收尾完整性校验
- **6 个确定性 EVM 地址**：`GATEWAY_ADDRESS=0xaaaa...`、`TREASURY_ADDRESS=0xbbbb...`、`DEVELOPER_ADDRESS=0xcccc...`、`WORKER_ADDRESS=0xdddd...`、`CONSUMER_ALPHA=0xeeee...`（新钱包，Flow 1 免费）、`CONSUMER_BETA=0xffff...`（回归钱包，Flow 2 扣费）
- **Bloomberg 终端日志**：`_ts()` 微秒时间戳 + 彩色标记（green PASS / red REFUND / yellow warn / cyan header）+ 分账 DEBIT(💸)/CREDIT(🧾) 行 + 结算汇总表 + 资金守恒审计断言
- **CLI 网络选择**：`--network in-memory`（默认，零外部依赖）或 `--network base-sepolia`（需 `AIMS_RPC_URL`/`AIMS_CONTRACT_ADDRESS`/`AIMS_GATEWAY_PRIVATE_KEY` 环境变量）

### aims-cli DRM 发布管道模式
- **四模块工具链**：Obfuscator（`src/cli/obfuscator.py`）+ Encryptor（`src/cli/encryptor.py`）+ Signer（`src/cli/signer.py`）+ Publisher（`src/cli/publisher.py`），由 `main.py publish` 命令编排
- **Obfuscator 三级降级**：优先 PyArmor（`pyarmor obfuscate` → `wrapper.so`）→ Cython（`cythonize -3 -i` → `gcc -shared` → `.so`）→ bytecode 复制 + 警告。120s 子进程超时防止挂死
- **Encryptor AES-256-GCM**：`cryptography.hazmat.primitives.ciphers.aead.AESGCM`，随机 12B nonce 前置 + ciphertext 写入 `logic.enc`。`encrypt_directory()` 递归收集 `.py` 文件 tar 后加密。返回 SHA-256 key hash 供签名阶段锁定
- **Signer EIP-191 格式**：消息 `AIMS-SKILL:{skill_id}:{key_hash}:{price}`，`encode_defunct(primitive=message.encode())` → `Account.sign_message()`，返回 `{signature, message, signer}`。签名不可伪造，版权归属锁死于开发者钱包
- **Publisher 8 步管道**：`publish_skill()` 依次执行 validate config → load credentials（`prompt_password()`）→ obfuscate → encrypt → sign → package `dist.zip` → upload（`requests.post` multipart）→ register metadata（EIP-191 签名 POST）。每步 click.echo 进度汇报，上传失败保留 `dist.zip` 手动重试
- **Metadata 注册签名**：`_register_metadata()` 构建 JSON body → `json.dumps(..., separators=(",", ":"))` 字节化 → EIP-191 签名原始 body 字节 → 注入 `X-Wallet-Address`/`X-Signature`/`X-Timestamp` 三头部 → POST 到网关
- **分发构件**：`dist.zip` 包含 `wrapper.so`（混淆壳）+ `logic.enc`（加密内核），Worker 运行时需对应解密和加载协议

## 学习资源
- 待补充

---
*本文档由 Claude Code 自动维护，请勿手动编辑格式*

## 代码模式

### 独立认领模式（Per-Party Claim）
- **`_worker_claimed[taskId]`**/**`_developer_claimed[taskId]`**：Worker 和 Developer 可分别独立调用 `claimReward`/`claimDeveloperReward`，互不阻塞
- **两阶段状态机**：`taskStatus` 仅在双方都认领后才转为 `CLAIMED`（此前保持 `SETTLED`）；`refundTask` 检查任一方认领后禁止退款
- **PoT 份额签名**：Gateway 签发的 PoT 金额为按 `WORKER_BPS`(2500)/`DEVELOPER_BPS`(7000) 计算的份额，而非 `COST_PER_TASK_USDC`
- **Solidity 映射要求**：`mapping(bytes32 => bool) public hasClaimedWorker; mapping(bytes32 => bool) public hasClaimedDeveloper;`
- **InMemory 同步**：`InMemorySettlementContract` 完全镜像上述 Solidity 逻辑，所有测试使用真实 ECDSA 签名验证

## 技术决策记录

### Billing & Settlement 架构
- **结算模式**: 从旧版托管 escrow 冻结迁移为 **实时 EIP-191 签名 Proof-of-Task (PoT) 分发** 的 70/25/5 多方即时分账
- **旧版遗留关键词**: `escrow` — 已废弃，被即时 70/25/5 多方流式分账替代
- **核心流程**: 用户 EIP-191 签名请求 → 中间件验签 + 402 余额拦截 → Gateway 路由 Worker → Worker 执行并签名 PoT → Gateway 验 PoT 并调用 `settleTask()` 上链 → 各方独立 `claimReward/claimDeveloperReward/claimTreasuryFees`
- **两阶段认领**: Worker 和 Developer 可独立领款，互不阻塞，`taskStatus` 仅双方都领完后才转为 `CLAIMED`

### 2026-06-10: Per-Party Claim 替代 Single TaskStatus
- **问题**：Worker 先 `claimReward` 后，`taskStatus` 变为 `CLAIMED`，Developer 无法再调用 `claimDeveloperReward`
- **方案**：增加 `_worker_claimed[taskId]` 和 `_developer_claimed[taskId]` 独立追踪
- **副作用**：`claimReward` 失败消息从 "task not settled" 变为 "worker already claimed"；`refundTask` 需额外检查认领状态

### Anvil E2E Pipeline 模式
- **四文件结构**：
  - `AIMSAgentGateway.sol` — 简化 Solidity 合约（native ETH，无需 USDC），worker-signed PoT 用 `ecrecover` 验证，70/25/5 分账，`onlyGateway` + `nonReentrant` 守卫
  - `gateway.py` — 独立 FastAPI 网关，EIP-191 personal_sign 中间件认证，402 billing 拦截器调用 `availableBalance()` 链上余额检查，`POST /api/run` 通过 httpx 异步调用 Worker
  - `mock_agent_node.py` — Worker 模拟 FastAPI 服务，`POST /api/execute` 模拟执行延迟后调用 `Account.unsafe_sign_hash(keccak256(taskId))` 生成 PoT
  - `pipeline_e2e_test.py` — 编排脚本，`ProcessManager` 管理 Anvil/Gateway/Worker 子进程生命周期，3 个场景（成功 70/25/5 ETH 余额验证 + 402 zero-balance + 403 signature tamper）
- **EIP-191 认证头部**（`gateway.py` 中间件）：`X-AIMS-Address`（consumer EVM address）、`X-AIMS-Signature`（`encode_defunct(primitive=body)` 签名 130 hex chars）、`X-AIMS-Timestamp`（UNIX 秒，±300s 窗口）
- **402 billing 拦截器**：中间件在 auth 通过后调用 `contract.functions.availableBalance(consumer).call()`，若 `< 0.05 ETH` 返回 HTTP 402 + 结构化 JSON（`insufficient balance`/`required_eth`/`balance_eth`/`action`）
- **Worker-signed PoT**：Worker 用自身私钥对 `keccak256(taskId)` 做 raw ECDSA 签名，gateway 用 `Account._recover_hash()` 验签后调用合约 `settleTask`，合约再用 `ecrecover` 二次验证
- **Gateway hot wallet**：交易由 Gateway 签名并广播，Consumer **不支付 Gas**。Gateway 使用 `build_transaction` + `sign_transaction` + `send_raw_transaction` 全流程
- **部署策略**：优先 `forge create`（需 Foundry），回退使用 `py-solc-x` + `solcx.compile_source` 编译后 `eth_sendTransaction` 部署
- **余额验证**：场景 A 对比 4 个地址的 ETH 余额变化（Consumer `availableBalance`、Developer 原生余额、Worker 原生余额、Gateway 原生余额），允许 0.5% Gas 误差

### 生产级 Hot Wallet 密钥安全模式
- **单一来源**：私钥仅从 `AIMS_GATEWAY_PRIVATE_KEY` 环境变量加载，无默认值/空字符串回退，`_load_gateway_key()` 启动时严格校验
- **严格验证**：`len(removeprefix("0x")) != 64` 长度检查 + `int(hex_key, 16)` hex 格式验证，非法 key 立即 `raise RuntimeError`
- **启动崩溃**：私钥缺失/格式错误时在 import 阶段（server bind 前）崩溃，杜绝启动后再发现配置问题
- **环境变量映射**：`pipeline_e2e_test.py` 使用 `AIMS_GATEWAY_PRIVATE_KEY` + `_deploy_via_forge` 兼容双 key（`AIMS_GATEWAY_PRIVATE_KEY` 优先，`GATEWAY_KEY` 回退）

### NonceManager 分布式单调 Nonce 模式
- **初始化同步**：构造时从 `w3.eth.get_transaction_count(address)` 同步链上 nonce，确保进程重启后 counters 不冲突
- **线程安全**：`threading.Lock()` 保护 `self._next_nonce` 增减，`get_nonce()` 原子返回并自增
- **可选 Redis 后端**：`REDIS_URL` 设置时使用 `redis.INCR` 命令实现跨进程原子计数，自动识别 Redis 不可用并回退内存锁
- **链上重同步**：`sync_nonce()` 对比链上 `get_transaction_count` 与本地计数器，链上领先时推进（交易失败后恢复），本地领先时保持不变（pending tx 保护）

### GasEstimator + Replace-by-Fee 模式
- **EIP-1559 动态计费**：`get_block("pending").baseFeePerGas` + `max_priority_fee` 乘以可配置乘数（`GAS_MULTIPLIER`/`PRIORITY_FEE_MULTIPLIER`），不支持 1559 时回退 `gas_price`
- **Gas bump 策略**：`bump_fees()` 将 `maxFeePerGas`/`maxPriorityFeePerGas`/`gasPrice` 按 `GAS_BUMP_PERCENT`（默认 20%）等比增加，用于 replace-by-fee
- **`_send_with_retry()` 全生命周期**：build → attach fees + nonce → sign → broadcast → poll 120s → timeout → bump gas → re-broadcast，最多 `MAX_TX_RETRIES`（默认 3）次
- **失败重同步**：每次 retry 前调用 `nonce_mgr.sync_nonce()` 修复 stuck nonce，确保 bump tx 使用正确 nonce

### 前端 EIP-191 签名模式（浏览器 ↔ Python 后端兼容）
- **浏览器端签名**：`ethers.Signer.signMessage(new Uint8Array(bodyBytes))` — ethers v6 自动添加 `\x19Ethereum Signed Message:\n` 前缀，与 Python `encode_defunct(primitive=body)` 完全兼容
- **三头部注入**：`X-Wallet-Address`（0x + 40 hex）、`X-Signature`（130 hex chars，移除 0x 前缀）、`X-Timestamp`（UNIX 秒）
- **402 拦截**：`POST /api/run` 返回 402 → 前端弹窗显示当前余额 + 合约地址 + 充值引导
- **三角色路由**：Consumer（Skill 调用 + 链上结算）、Developer（70% 流式分润）、Worker（25% 佣金 + 心跳 + 节点模拟）
- **AIMS Execution Pipeline**：Auth → Free Trial Check → Balance Check → Execution → PoT → Settlement 六阶段动画进度条，反映从签名到链上分账的完整资金流

### 前端 PLG UI 模式（6 步管道 + 试用追踪）
- **6 步管道**：Auth → Free Trial Check → Balance Check → Execution → PoT → Settlement，第 2 步（Free Trial Check）为 PLG 新增，仅在 `trialsLeft[skill_id] > 0` 时显示绿色 "Free Trial" 标签
- **Billing Mode 选择器**：下拉菜单（Metered / Subscription / Buyout / Free Trial），Free Trial 选项仅在有剩余试用次数时显示，选择后自动跳过余额检查
- **Trial 状态追踪**：`usedTrials: Record<string, boolean>` 本地对象跟踪每个 skill 是否已消耗试用，`updateTrialDisplay()` 计算 `trialsLeft`，`setTrialStep()` 动态切换管道显示
- **PLG Badge**：顶部栏 `★ 1 Free Trial / Skill` 徽章，单击展开剩余试用列表
- **Trial 生命周期**：SUCCESS 时 `usedTrials[skill_id] = true`（消耗），FAILURE 时恢复（`usedTrials[skill_id] = false`），匹配后端 `FreeTrialManager` 的 `consume_trial()` / 失败不回滚语义
- **402 弹窗增强**：余额不足时显示 "Use Free Trial Instead" 按钮（skill 有剩余试用时），引导用户零成本体验
- **EIP-191 浏览器签名**：`ethers.Signer.signMessage(new Uint8Array(bodyBytes))` 生成兼容 Python `encode_defunct` 的签名，三头部（X-Wallet-Address / X-Signature / X-Timestamp）注入 API 请求

### 前端页面架构
- **index.html**（着陆页）：暗色 Cyberpunk 风格，Hero + 3 价值主张 + 3 角色卡片 + 4 大优势 + How It Works（双分账表 Q1/Q2-Q5）+ PLG 横幅 + Commerce Matrix 3 模式对比表 + 技术规格附录
- **docs.html**（开发者文档）：Quickstart + PLG 说明框 + Revenue Split 表 + Billing Modes 表 + aims-cli 工具链 3 节（init/login/publish 8 阶段 DRM）+ API 端点表 + FAQ
- **console.html**（Web3 控制面板）：三角色视图（Consumer/Developer/Worker）+ MetaMask 直连 + 6 步管道 + Billing Mode 选择器 + Trial 追踪 + Worker 佣金显示 + 配置面板 + 结算流实时推送面板 + Google/Apple 社交登录

### 前端 SLA 争议仲裁保障模式
- **80/100 LLM-as-a-Judge 阈值**：每笔任务完成后由零人 AI 裁判自动评分，低于 80 分触发智能合约 `escrow refund` 自动 100% 退款 — 开发者 0 收入、Worker 0 收入、协议 Treasury 承担 Gas
- **不可变字节码保障**：SLA 规则编码在 `AIMSAgentGateway.sol` 的 `settleTask()` 逻辑中，非人工客服承诺
- **SLA Banner**：首页 `Cryptographic SLA Dispute Escrow` 醒目横幅，标注 `Contract-enforced · 80/100 threshold · Auto-refund · No humans involved`
- **结算流体现**：Settlement Feed 中每个 entry 的 AI Judge 评分 < 80 时显示红色 `✗ REFUND` 标记，绿色 `✓ PASS` 标记表示通过仲裁

### 前端全球实时结算大屏模式（Settlement Feed）
- **Bloomberg 终端风格**：深色背景 + 绿色/青色荧光字体 + 高频滚动终端面板
- **Mock 数据结构**：每 2.8s 生成一条新记录，含相对时间、Skill 名称+图标、钱包地址缩写、AI Judge 评分、USDC 金额、Q1 70/25/5 / Q2-Q5 95/0/5 分账明细、Worker 地理区域
- **滚动逻辑**：`insertBefore()` 顶部插入 → 最多保留 20 条 → 溢出自动移除
- **计数器**：Settled 总数、Volume 总量、Disputes 数量三个全局统计
- **评分着色**：>= 80 绿色 `✓ PASS`（左侧绿色边框），< 80 红色 `✗ REFUND`（左侧红色边框 + 争议计数 +1）
- **控制台版本**：精简版 `feed-console` 类，120px 高度滚动，15 条上限，复用相同数据生成逻辑

### 前端 Web2 社交登录模式
- **Google/Apple 一键登录按钮**：SVG 原生图标按钮，标注 "Coming Soon" / "Soon" 黄色徽章
- **着陆页位置**：Hero CTA 下方独立一行，与 "Launch App / Read Docs / Explore Roles" 并列
- **控制台位置**：Wallet 连接按钮右侧，`.social-btn-group` 横向排列
- **点击行为**：`toast('Social login coming soon — use your wallet')` 提示用户当前仅支持 MetaMask
- **技术背景**：UI 占位，后端需集成 Privy/Magic/Web3Auth 的 AA 账户抽象 + Google OAuth 完成真实社交登录

- **CORS 配置**：`server.py` 使用 `CORSMiddleware(allow_origins=["*"])` 开放跨域；前端通过 `localStorage.setItem("aims_api_base", url)` 配置 API 地址

### AI Judge 仲裁模式
- **LLM-as-a-Judge 评分引擎**（`src/judge/judge_agent.py`）：通过 OpenAI `gpt-4o-mini` 对 Worker 输出进行 0-100 评分，基于三要素（正确性 0-40 / 完整性 0-30 / 质量 0-30）
- **评分流程**：构造带 `JUDGE_SYSTEM_PROMPT` + Task Input/Schema/Output 的 Prompt → OpenAI `chat.completions.create(temperature=0.1)` → 解析 JSON `{"score": int, "reason": "..."}` → 返回 `JudgeVerdict`
- **阈值 80/100**：`JUDGE_PASS_THRESHOLD = 80`，`score >= 80` 通过（继续正常结算），`score < 80` 触发 `refund_on_chain()` + SSE 红警广播
- **确定性回退**：无 `OPENAI_API_KEY` 时使用结构启发式评分（字段缺失 -20 / 空值 -5/个 / 内容过短 -15 / 错误关键词 -10/个），起点 50 分
- **`refund_on_chain()`**：`keccak(task_id)` → `contract.refund_task(amount + reason)` → `on_refund_alert` 回调推 SSE `{"severity": "ALERT"}` 事件
- **集成点**：`server.py` `submit_task` 函数中，Schema 验证和 Canary 检查之后，`commerce.charge_and_settle()` 之前插入 `judge_engine.score()`，评分 < 80 直接返回 `REFUNDED`
- **管理端点**：`POST /api/admin/judge` 接受任意 task_input/task_output/skill_id 测试评分

### Chain Event Listener 模式
- **`ChainListener`**（`src/gateway/chain_listener.py`）：`daemon=True` 后台线程以可配置间隔（默认 15s）轮询合约事件
- **双模式**：`_is_inmemory` 属性通过 `hasattr(contract_client, '_w3')` 自动检测
  - **InMemory 模式**：读取 `InMemorySettlementContract._event_buffer` 列表，比较 `_last_event_count` 发现新事件
  - **Web3 模式**：通过 `w3.eth.get_logs()` 按 topic hash 过滤 `TaskSettled`/`TaskRefunded`，`fromBlock`/`toBlock` 分块扫描（max 200 blocks/次），`last_processed_block` 持久化到 Redis
- **事件 ABI 解码**：`eth_abi.decode()` 解析 indexed 参数（`topics[1:]`）和非 indexed 参数（`data`）；`TaskSettled`（5 个 non-indexed: address + 4×uint256），`TaskRefunded`（2 个 non-indexed: uint256 + string）
- **事件缓冲**：`InMemorySettlementContract.__init__()` 新增 `_event_buffer: list[dict] = []`，`settle_task()` 和 `refund_task()` 方法结束时追加事件 dict
- **SSE 桥接**：`on_settlement`/`on_refund` 回调参数指向 `broadcast_settlement`，实现监听器→前端实时推送
- **生命周期**：FastAPI `lifespan` 上下文管理器启动时调用 `_chain_listener.start()`，关闭时 `_chain_listener.stop()`
- **管理端点**：`GET /api/admin/listener` 返回运行状态、模式、`last_processed_block`、`last_event_count`

### Console 前端 UI 组件模式
- **Free Trial 动态状态指示器**：Consumer 面板顶部专属卡片展示剩余试用次数 + 使用进度条（`trialProgressBar`，绿→绿色渐变），`updateTrialDisplay()` 按 `(usedTrials, skillsCache.length)` 计算剩余并同步更新 Account 卡的 `trialsLeft` 和增强卡片的 `trialsLeftEnhanced`
- **Commerce Mode 切换面板**：`#commercePanel` 卡片包含 Metered/Subscription/Free Trial 三按钮组 + Buyout Perpetual License 按钮，`switchBillingMode()` 同步更新 `#billingMode` 下拉选择器、模式标签和描述文本，按钮高亮通过 `.btn-outline.active` CSS 类控制
- **Buyout Perpetual License 交互**：`#buyoutModal` 模态框展示 Skill 名称/许可证类型/价格，`confirmBuyout()` 通过 `POST /api/licensing/request-key` 发送 EIP-191 签名请求完成买断，成功后自动切换到 buyout 模式
- **Canary Watermark Status 三层防御指示器**：Worker 面板中 `#canaryStatusCard` 卡片实时显示 ECDSA Token（Layer 1）/ Replay Shield（Layer 2）/ Piracy Blacklist（Layer 3）状态，`updateCanaryStatus(true/false)` 在 Worker 节点启动/停止时切换

### Circuit Breaker 三阶熔断模式
- **CircuitBreaker**（`src/gateway/circuit_breaker.py`）：CLOSED→HALF_OPEN→OPEN **三态有限状态机**，通过 `Storage` 持久化计数，SSE 回调桥接实时告警
- **状态转换阈值**：`DEFAULT_CONSECUTIVE_THRESHOLD=3`（连续失败数触发 CLOSED→HALF_OPEN）、`MAX_DEGRADED_THRESHOLD=6`（HALF_OPEN 累积失败触发 OPEN）、`OPEN_COOLDOWN_SECONDS=120.0`（冷却后 `can_pass()` 自动转 CLOSED）
- **核心方法**：`record_failure(reason)` 递增失败计数并推进状态机；`record_success()` 清零并自愈（HALF_OPEN→CLOSED）；`can_pass()` 检查当前是否可放行（OPEN 时返回 False 并检查冷却是否过期）；`admin_reset()`/`admin_force_open()` 管理控制
- **server.py 集成**：`/api/run` 入口调用 `breaker.can_pass()` → OPEN 时返回 503；`submit_task` Judge 评分后 `record_success()`/`record_failure()` 自动驱动状态迁移；`on_state_change` lambda 回调 `broadcast_settlement()` 推 SSE 事件
- **Admin 端点**：`POST /api/admin/emergency-pause`（全网紧急暂停 → `admin_force_open()` + SSE 红警）、`POST /api/admin/reset`（`admin_reset()` 复位 CLOSED）、`GET /api/admin/circuit-breaker`（全量状态快照含阈值和冷却剩余时间）
- **SSE 事件类型**：`circuit_breaker_transition`（状态切换 `{from, to, ts}`）、`emergency_pause`（管理暂停 `{state, ts}`）、`circuit_breaker_reset`（管理复位 `{state, ts}`）

### 并发压测 Worker 循环模式
- **Worker 注册 key 一致性**：`seed_dev_usdt()` 和 `register_worker()` 必须使用相同的 key（worker_id `"worker_00"` 而非 EVM `wallet` 地址），否则注册因余额检查失败
- **Worker 循环终止条件**：`claim_task()` 返回 `None` 时必须在 `continue` 前检查全局完成状态（`pending_count == 0 && all()`），否则空闲 Worker 无限循环
- **异步 Worker 池设计**：`asyncio.gather()` 驱动 N 个 `worker_cycle()` 协程，每个协程内 `while True` 循环，通过 `broker.pending_count` 和全量状态扫描决定退出

### 容器化集群编排模式
- **多节点拓扑**：`docker-compose.yml` 定义 `gateway-server`（FastAPI + 前端）→ `redis-coordinator`（持久化/协调）→ `worker-node-1/2/3`（DePIN 计算节点）的三层依赖拓扑
- **YAML 锚点继承**：`x-gateway-env` / `x-worker-env` YAML 锚点实现环境变量 DRY，Worker 通过 `<<: *gateway-env` 继承 Gateway 的全部配置并追加 `AIMS_GATEWAY_URL`
- **Healthcheck 链式依赖**：`depends_on` 配合 `condition: service_healthy` 确保 redis 就绪→gateway 就绪→worker 启动，`curl` 探测 `GET /api/health`
- **Worker 隔离**：每个 Worker 容器绑定独立 `AIMS_WORKER_ID`/`AIMS_WORKER_KEY`/`AIMS_WORKER_WALLET`，通过 `.env` 文件或平台 secret 注入生产密钥

### Demo Day 路演编排模式
- **4 幕故事线**：Act I（PLG 零摩擦获客）→ Act II（70/25/5 密码学分账）→ Act III（SLA 铁面裁决退款 + 红警）→ Act IV（熔断极限自愈 + 黄警）
- **Bloomberg 终端视觉**：`banner()`/`log()`/`sep()`/`countdown()` 工具函数，彩色状态指示（绿=通过/蓝=结算/红=告警/黄=降级），`C_BG_RED`/`C_BG_GREEN` 大色块强调关键转折
- **SSE 事件总线**：`_on_settlement()` 回调写入 `sse_buffer` 列表，`check_sse_events()` 按时间窗口和 action 过滤，验证每个 Act 的正确事件广播
- **Judge 评分劫持**：`judge.score` 方法在 Demo 场景中通过 `JudgeVerdict(...)` 强制设定确定性分数（95/72 等），确保路演每次结果一致
- **Demo 常见陷阱**：
  - **Gateway 私钥截断**：Hardhat `GATEWAY_KEY` 必须是 64 hex chars（32 bytes），短于 64 的 hex 串导致 `"private key must be exactly 32 bytes"` 错误
  - **Escrow 余额前置**：`publish_task()` 内部调用 `create_escrow_hold()` 检查用户余额，即使是免费试用也需满足 escrow 最低余额
  - **合约注入**：`CommerceEngine.charge_and_settle()` 的 metered 路径调用 `BillingEngine.request_settlement()` 需要 `contract_client` 参数，否则返回 `"No contract client configured"`
  - **余额查询源**：`contract.get_user_balance()` / 1_000_000（6 decimal USDC）查询合约内余额，`ledger.get_user_usdt()` 仅反映 MockLedger 隔离余额

### 生产网迁移清单模式
- **三阶段发布**：Pre-Flight（T-48h 合约部署 + 密钥生成）→ Launch（Fly.io deploy + Worker 启动 + 监控观察）→ Rollback（`admin/emergency-pause` + `fly deploy` 回滚）
- **密钥分级**：`AIMS_GATEWAY_PRIVATE_KEY`（热钱包，< 0.1 ETH，季度轮换）→ `AIMS_SIGNING_SECRET`（HMAC 共享密钥）→ Worker 密钥（每节点独立，仅签名 PoT）
- **多签治理**：`PLATFORM_OWNER` 必须为 3/5 Gnosis Safe，合约升级权限分离（UUPS proxy admin 与 owner 不同多签）

### 生产集群离线部署模式
- **纯离线 Compose**（`docker-compose.prod.yml`）：`image` 直接锁定 `redis:7-alpine` 和 `python:3.11-slim`，不经 `build` 步骤，无 Docker Hub 网络依赖
- **零默认值凭证**：所有 `${VARIABLE}` 不设 `:-fallback`，容器缺失环境变量时立即启动失败而非静默使用不安全默认值
- **Worker 工业隔离三件套**：`user: "1000:1000"`（非 root）+ `cap_drop: ALL`（无网络嗅探/进程外溢）+ `read_only: true` + `tmpfs: /tmp`（无持久化写盘）
- **交互式点火脚本**（`scripts/deploy_mainnet.sh`）：`docker images` 阻断检查 + `read -p` 逐项采集 + `read -s` 静默输入私钥 + 严格格式校验（64 hex chars/URL prefix/address regex）
- **点火后健康轮询**：`/api/admin/listener` 端点 5 轮轮询，同时验证 `ChainListener.status=running` 和 `CircuitBreaker.state=CLOSED`

### DeepSeek AI Judge 生产切换模式
- **零代码变更**：`JudgeEngine` 使用 `openai` Python 包，自动读取 `OPENAI_BASE_URL` 环境变量；只需设置 `OPENAI_BASE_URL=https://api.deepseek.com/v1` + `OPENAI_API_KEY=<DeepSeek Key>` + `LLM_MODEL_NAME=deepseek-v4-flash` 即完成切换
- **模型名严格校验**：DeepSeek API 拒绝 `deepseek-chat`/`gpt-4o-mini`，生产必须使用 `deepseek-v4-flash`（v4 快速版）或 `deepseek-v4-pro`（专业版），通过 `JudgeEngine(model=os.getenv("LLM_MODEL_NAME"))` 从环境变量注入
- **max_tokens 调优**：DeepSeek v4 推理链较长，`max_tokens=256` 导致 JSON 评分被截断无法解析；生产设为 `1024` 确保评分 JSON 完整返回
- **截断 JSON 修复**：DeepSeek v4 可能在 `reason` 字段中间截断，`if not cleaned.endswith("}"): cleaned += '" }'` 补全缺失的右引号和闭合括号，提高 JSON 解析成功率
- **硬编码兜底**：`deploy_mainnet.sh` 脚本内写死 `export OPENAI_BASE_URL="https://api.deepseek.com/v1"` + `LLM_MODEL_NAME="deepseek-v4-flash"`，杜绝人为配错
- **生产监控**：`/api/admin/judge` 端点返回当前 model 名称验证，`/api/admin/judge/verdicts` 回溯最近评分记录

### 任务集市（Task Market）模式
- **BrokerTask 扩展字段**（`src/gateway/broker.py`）：新增 `task_name`（人可读任务名）、`description`（自由文本描述）、`is_custom`（是否开启信用分门控）、`credit_score_required`（0-100 最低信用分要求）
- **`get_pending_tasks(limit=50)`**：返回所有 `PENDING` 状态任务（`newest first`），包含 `task_id`/`skill_id`/`task_name`/`description`/`is_custom`/`credit_score_required`/`max_budget` 等字段，供前端 Task Market UI 渲染
- **`claim_specific_task(task_id, worker_id, credit_score=0)`**：按 ID 精确认领任务；`is_custom` 任务验证 `credit_score >= credit_score_required`，不满足返回 `None`；无锁竞争，原子操作
- **`POST /api/tasks/publish`**：接受 `PublishTaskRequest`（扩展 `RunRequest` 加 Task Market 元数据），和 `/api/run` 一样走 escrow freeze → balance check → trial enforcement 全流程
- **`POST /api/tasks/claim-specific`**：接收 `ClaimSpecificRequest(task_id, worker_id, credit_score)`，调用 `broker.claim_specific_task()`；失败时区分 404（不存在）vs 403（信用分不足，返回 `credit_score_required`）
- **`GET /api/tasks/pending`**：免认证，返回 `{tasks: [...], count: N}` JSON，供前端 Developer 选项卡「抢单池」表格渲染
- **API Discovery 集成**：新增 "Task Market" 类别（publish/pending/claim-specific）和 "Worker Credit" 类别

### Worker Credit Score 系统
- **常量**：`CREDIT_SCORE_NS = "worker:credit"`（`server.py`），Storage namespace for credit scores
- **存储**：`storage.dict_get(CREDIT_SCORE_NS, wallet)` / `storage.dict_set(CREDIT_SCORE_NS, wallet, score)`
- **范围**：0-100，默认 0（新 Worker）
- **`GET /api/worker/credit-score/{wallet}`**：免认证，返回 `{wallet, score}`
- **`POST /api/worker/credit-score`**：需 EIP-191 签名认证（仅 Admin），接受 `{wallet, score}`
- **前端门控**：`claimTask()` 先 `GET /api/worker/credit-score/{wallet}` 获取当前信用分 → `credit_score < credit_score_required` 时调用 `showCreditBlockModal()` 弹窗阻断而非静默失败；custom task 按钮显示 🔒 锁图标

### AIMS_SKILL_GUIDE.md 开发者文档
- **根目录文件**：`AIMS_SKILL_GUIDE.md`，完整接入指南覆盖：
  - Quick Start（Hello World Skill 完整示例）
  - EIP-191 认证流程（Python `eth_account` 示例 + Browser MetaMask 示例）
  - Skill Lifecycle（publish → claim → execute → validate → settle）
  - AI Judge 质量评分（80/100 threshold，打分表格）
  - Commerce & Billing（4 种计费模式表格）
  - Task Market（custom task 信用分门控示例）
  - API 参考表格（所有端点 + 认证要求）
  - 安全模型（威胁矩阵表）
  - Python SDK 完整示例
- **`/developer-guide` 路由**：FastAPI `GET /developer-guide` 读取 `AIMS_SKILL_GUIDE.md`，通过 `_render_markdown_as_html()` 简易 Markdown→HTML 渲染器转换后嵌入 Dark 主题 HTML 模板返回

### Boost Reward（动态加价催单）模式
- **端点到逻辑**：`POST /api/tasks/{task_id}/boost-reward` — 仅 vault `funded` 状态可加价，校验 vault 存在且状态为 `funded`，否则 409
- **状态变更**：`vault_data["balance"]` 和 `vault_data["budget"]` 同时增加 amount，记录 `boost_history[].amount` + `ts` 审计链，`total_boosted` 实时聚合
- **SSE 广播**：`vault_boosted` 事件推送至全局结算流，`amount`、`new_balance`、`total_boosted` 字段
- **前端联动**：vault 面板 boost section 在 vault `unfunded` 时 disabled + opacity 0.4，`funded` 后自动启用；`showVaultPanel()` / `pollVaultStatus()` / `simulateVaultPayment()` 均需更新 boost 状态
- **Task Market 表现**：已加价任务在列表中显示 ⚡ 徽章和总加价金额

### Multi-Contributor Splitter（多贡献者分账）模式
- **数据结构**：`ContributorSplit(BaseModel)` — `wallet`（EVM 42 字符）+ `share_pct`（0-100 float）；存储在 `DEVELOPER_INTEGRATION_NS` 的 skill entry 中 `skills[].co_contributors[]`
- **创建路径**：`POST /api/developer/integrate` 可选字段 `co_contributors` 写入；`POST /api/developer/set-contributors` 事后推送到已集成 skill
- **分账逻辑**：`_settle_vault()` 在 70/25/5 分账时，若 skill 配置了 co_contributors，则 70% 开发者份额按比例分拆给各贡献者；最后一人接收剩余金额（防浮点误差）；`payouts` 数组和 `tx_ledger.record()` 逐钱包记录
- **连带扣分**：`_penalize_contributors()` 在 AI Judge 失败时遍历开发者 + 所有 unique co-contributor 钱包各 -10 credit（`min(0, score - 10)`）
- **前端 UI**：一键接入表单下方动态行（wallet/百分比/删除按钮），实时百分比总计，Save Split Config 按钮调 `set-contributors` 端点；`oneClickIntegrate()` 提交时自动收集 DOM 中 co-contributor 行

### One-Click Integration（一键接入）模式
- **`POST /api/developer/integrate`**：接受 `IntegrateRequest(skill_name_or_url, wallet_address)`，自动检测输入类型（URL 开头 `http://`/`https://` 为 URL Proxy，否则为 Skill Mapping）
- **存储模式**：`DEVELOPER_INTEGRATION_NS = "developer:integration"` namespace，`storage.dict_set(DEVELOPER_INTEGRATION_NS, wallet, integration_data)`，数据含 `{wallet, skills: [{name, url, mapped_at, type}], updated_at}`
- **自动 70% 分润**：检测到输入为已知 Skill 名时，自动调用 `billing.register_developer(skill_name, wallet)` 注册开发者 70/25/5 分账
- **防重入**：遍历 `existing_skills` 检查同 URL/Skill 名重复，重复时返回 `{status: "exists"}` 而非覆盖
- **`GET /api/developer/integration/{wallet}`**：免认证查询，返回 `IntegrationStatusResponse(wallet, skills, count)`
- **前端 UI**：Developer 选项卡 `#integrateCard` 独立输入行（skill/URL + wallet），`oneClickIntegrate()` EIP-191 签名绑定，`fetchIntegrationStatus()` 自动轮询已映射数量
- **Discovery 集成**：新增 "Developer Integration" 类别，含 integrate（认证）和 integration status（免认证）两个操作

### Task-Vault（扫码付款唯一托管钱包）模式
- **确定性 vault 地址**：`hashlib.sha256(f"aims:vault:{task_id}".encode()).hexdigest()` 取前 39 字符，拼接 `0xV` 前缀 → 42 字符 EVM 地址（`V` 前缀区分 vault 地址与用户钱包）
- **存储**：`TASK_VAULT_NS = "task_vault"` namespace，`storage.dict_set(TASK_VAULT_NS, task_id, vault_data)`，vault_data 含 `{task_id, vault_address, balance, status, budget, fiat_paid, created_at, user_id, skill_id}`
- **状态流转**：`unfunded`（发布时）→ `funded`（法币充值后）→ `released`（AI Judge 通过后 70/25/5 自动释放）
- **自动创建**：`publish_task` 中 `_generate_vault_address(task_id)` + `storage.dict_set` → `PublishTaskResponse` 返回 `vault_address` 和 `vault_status`
- **`POST /api/tasks/{task_id}/simulate-fiat-payment`**：vault `unfunded`→`funded`，`balance = budget`，`fiat_paid = true`，`payment_method = "mock_stripe_qr"`；404 无 vault / 409 非 unfunded 状态
- **`_settle_vault(task_id)`**：读取 vault balance → `70%/25%/5%` 分账 → vault_data `released` + `split` 字段 → `broadcast_settlement()` 推送 `vault_settle` 事件
- **submit_task 集成**：在 AI Judge 通过后、普通 escrow 结算前检查 vault 状态，若 `funded` 则直接调用 `_settle_vault()` 并返回 `SubmitResponse`（跳过 `charge_and_settle()`）
- **`GET /api/tasks/{task_id}/vault-status`**：免认证轮询，返回 `VaultStatusResponse(task_id, vault_address, balance, status)`
- **`POST /api/tasks/{task_id}/settle-from-vault`**：管理手动触发 vault 结算，用于测试/人工干预
- **前端 UI**：Consumer 发布任务后 `showVaultPanel()` 展示 vault 地址/余额/QR 模拟 + `simulateVaultPayment()` 法币充值 + `pollVaultStatus()` 状态轮询；FUNDED 时隐藏 QR 面板，RELEASED 时禁用付款按钮

### Multi-Platform AI Tool Integration Docs 模式
- **实现方式**：`INTEGRATION_DOCS` 常量字符串（HTML 嵌入），`GET /integration-docs` FastAPI 路由直接返回 `HTMLResponse(content=INTEGRATION_DOCS)`
- **平台覆盖**：5 个 AI 开发工具 — **Cursor**（`.cursor/mcp.json` 配置）、**Claude Code**（`CLAUDE.md` MCP 服务器声明）、**OpenClaw**（YAML manifest 下载）、**Hermes**（`bootstrap_helper.py` 自动发现）、**Codex**（OpenAPI 自动发现）
- **One-Key Auth**：统一 EIP-191 personal_sign 认证说明，钱包即 API Key
- **快速开始**：4 步标准流程（Install → Discover → Invoke → Settle），API Base 生产/本地切换
- **发现端点**：文档链接至 `/api/discovery`、`/console`、`/developer-guide`

### Credit Score Dashboard UI 模式
- **实现方式**：`fetchCreditScore()` 异步函数通过 `GET /api/worker/credit-score/{wallet}` 获取信用分，`getCreditLevel()` 映射 0-100 分为 AAA/AA/A/B/C 五级（AAA ≥95，AA ≥85，A ≥70，B ≥50，C <50）
- **Consumer 仪表盘**：`#consumerCreditScore` 容器，渐变进度条（前端 JS 动态宽度），等级徽章（颜色编码：绿色 AAA/AA、青色 A、琥珀色 B、红色 C）
- **Developer 仪表盘**：`#developerCreditScore` 替代原 "Last Settlements" 卡片，同 Consumer 一致的信用分展示

### Task Market Boost Button 模式
- **实现方式**：每行 `mt-action` 容器左侧新增小型 ⚡ 按钮，`onclick="boostFromMarket('${t.task_id}')"`，`boostBadge-{taskId}` 元素显示加价状态
- **boostFromMarket()**：调用 `showVaultPanel(taskId)` 并 `scrollIntoView` 平滑滚动至 vault 面板，自动启用 boost section（`style.display = "block"`）
- **设计**：flex 布局 `display:flex;gap:.25rem`，boost 按钮 `font-size:.6rem`，不干扰原 Claim 流程

### Topbar Navigation 模式
- **实现方式**：`<nav class="top-nav">` 嵌入在 `.logo` 与 `.wallet-area` 之间的 flex 容器
- **链接**：Console（neon 高亮）、Integration（/integration-docs）、Rules & Docs（/rules-and-docs）、API（/api/discovery）
- **样式**：`font-size:.72rem`，未选中状态 `var(--text-dim)`，选中状态 `var(--neon)`

### Unified Agent/CLI 端点模式（POST /api/skill/task-action）
- **实现方式**：FastAPI `@app.post("/api/skill/task-action")` 路由，`TaskActionRequest`（action/skill_id/task_id/params）+ `TaskActionResponse`（action/success/data/error）
- **支持动作**：`publish_task`（包装 `/api/tasks/publish`）、`boost_reward`（包装 `POST /api/tasks/{id}/boost-reward`）、`query_account`（查询余额+信用分）、`claim_task`（包装 `/api/tasks/claim-specific`）、`submit_task`（包装 `/api/tasks/submit`）
- **认证**：依赖 `request.state.verified_wallet`（middleware 注入），缺失则 401
- **错误处理**：已知 `HTTPException` 直接传播，未知异常捕获返回 `success=False` + error 消息体

### Auth Guard 双轨登录/注册模式
- **实现方式**：`static/login.html` 独立页面，双 Tab 切换（Sign In / Register），Email+密码传统表单 + MetaMask Web3 一键连接
- **后端端点**：`POST /api/auth/register`（bcrypt 密码哈希 + `create_user()` + `create_jwt()` JWT 发放）、`POST /api/auth/login`（`authenticate_user()` + JWT）、`POST /api/auth/wallet-login`（EIP-191 `personal_sign` 签名恢复地址 + 自动创建/查找用户 + JWT）、`POST /api/auth/link-wallet`（绑定钱包至已有账户）
- **JWT 规格**：HS256 算法，`jwt_secret` 每用户独立（32 字节 hex），7 天有效期，payload 含 `sub`(user_id)/`email`/`wallet`/`iat`/`exp`
- **密码强度**：前端实时评分（长度/大小写/数字/特殊字符），后端 8 位最小长度 + bcrypt rounds

### JWT + API Key 中间件鉴权模式
- **实现方式**：在原有 `verify_wallet_middleware` 中前置注入 Bearer token 检查
- **鉴权优先级**：`Authorization: Bearer <token>` header → 检查是否为 `sk-aims-` 前缀（API Key）→ `verify_api_key()` bcrypt 遍历匹配 → 否则 JWT `verify_jwt()` 验签 → 均失败则回退 EIP-191 headers（CLI 兼容）
- **状态注入**：验签成功后设置 `request.state.verified_wallet` + `request.state.user_id` + `request.state.auth_method`（jwt/api_key/eip191）
- **页面守卫**：`/` 和 `/console` 路由读取 `request.cookies` + `Authorization` header 中的 JWT，无效/缺失返回 HTML 重定向至 `/login`
- **API Key 格式**：`sk-aims-` + `secrets.token_hex(36)` = 48 字符，bcrypt 哈希存储，`key_prefix` 前 12 字符+"..."用于 UI 展示

### Off-Chain User & Payment Database 模式
- **实现方式**：`src/gateway/database.py` 模块，SQLite（`aiosqlite`）+ `DATABASE_URL` 环境变量可切换 PostgreSQL
- **三表结构**：`users`（email/password_hash/wallet_address/jwt_secret/display_name）、`api_keys`（key_hash/key_prefix/label/is_revoked）、`payments`（user_id/action/amount_usdc/wallet_address/tx_ref）
- **安全设计**：密码 `bcrypt.hashpw(gensalt())` 哈希，JWT 密钥每用户独立 32 字节 hex，API Key bcrypt 哈希，WAL 模式写性能
- **Fly.io 持久化**：`[mounts] source = "aims_gateway_data" destination = "/data"`，volume 挂载确保重启/重部署数据不丢失
- **初始化**：`lifespan` 启动时调用 `await init_db()` 自动建表

### API Key 管理控制台模式
- **UI 位置**：Developer 标签页，入口在 One-Click Integration 与 Task Market 之间
- **功能**：输入标签 + 点击 Generate → 弹出一次性明文密钥（点击复制）+ 自动刷新列表；列表表格（Label/Key Prefix/Created/Last Used/Revoke 按钮）；撤销前 confirm() 确认
- **鉴权**：所有 `/api/auth/api-keys` 端点依赖 `request.state.user_id`（JWT 中间件注入）
- **密钥使用**：外部 AI 工具（Cursor/Claude Code/OpenClaw）调用 `POST /api/skill/task-action` 时携带 `Authorization: Bearer <sk-aims-xxx>` 即可通过鉴权

### AIMS Network Behavior Rules 模式
- **实现方式**：`RULES_AND_DOCS` 常量字符串（HTML 嵌入），`GET /rules-and-docs` 路由返回 `HTMLResponse(content=RULES_AND_DOCS)`
- **8 条规则**：Fair Settlement（70/25/5）、Proof-of-Task（ECDSA 签名）、Credit Score Accountability（±1/-5/-10）、Anti-Piracy（Canary 水印）、Slashing & Misconduct（-25+）、Boost Reward Fairness、Free Trial & PLG、Rate Limiting（100/60s）
- **页面结构**：导航链接栏（Console/Integration/API/Dev Guide）→ 规则卡片（color-coded: ok=绿色, 默认=琥珀色, err=红色）→ 多平台集成指南 → One-Key Auth → Unified API 文档
