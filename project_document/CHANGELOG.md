<!-- AIMS Protocol | Version 1.0.0 | Last Updated: 2026-06-13 | Hermes-Verified -->

# 变更日志

> **格式要求**: 严格遵循 `.claude/output-styles/bullet-points.md` 格式规范  
> **提交规范**: 遵循 commitlint 规范（type(scope): subject）

## [2026-06-17]
### 重构
- refactor(console): `static/console.html` 从 2993 行压缩至 385 行（87% 缩减） — 提取全部 CSS 至 `static/css/console-v2.css`（297 行），提取全部 50 个 JS 函数至 `static/js/console-core.js`（1624 行），提取平台文档文本至 `static/js/docs-content.js`（44 行）；Stitch 玻璃拟态设计系统 + Tailwind CDN；vault 跨 Tab 保护保留；消除所有空 `catch` 块
### 修复
- fix(console-syntax): `const net` 重复声明 + `invokeSkill()` 多余 `}` — 两个 SyntaxError 导致整个 `<script>` 块不执行，所有按钮点击无反应；第二个声明重命名为 `const currentNet`，删除多余闭合括号
- fix(console-fallback): 5 个关键函数（`handleDeposit`/`rechargeReserves`/`withdrawFunds`/`fiatDeposit`/`sendHeartbeat`）追加 `smartHeaders(body)` JWT fallback — 无 MetaMask 时不再静默失败
- fix(console-silent): `fetchCreditScore()`/`fetchIntegrationStatus()` 静默 `catch{}` → `console.warn()` — 错误不再隐藏
- fix(console-null): `fetchDiscovery()` `devSettlements` null 检查 — 防止 Developer Tab 未渲染时报 `Cannot set properties of null`
- fix(console-vault-ids): `switchRole()` 新增 `_savedVaultTaskId` 备份/恢复 — 离开 Consumer Tab 时保存 `_currentVaultTaskId`，返回时自动还原，修复 vault 面板三个按钮（付款/查询/加价）在 Tab 切换后无响应的问题
- fix(console-claim-silent): `claimTask()` 信用分查询 `catch(e){}` → `console.warn()` — 网络失败不再静默吞掉
- docs(whitepaper): `project_document/AIMS_CONSOLE_BUTTON_WHITEPAPER.md` — 完整按钮白皮书（62 按钮、50 JS 函数、25 API 端点、风险矩阵）
- fix(auth): `/` 路由释放 Auth Guard，改为公开页面 — 用户首次访问可直接看到着陆页，仅 `/console` 保留 JWT 鉴权重定向
- fix(ui): `static/index.html` "Launch App" 按钮 href 修正 `#cta` → `/console`，确保商业动线正确引导至登录拦截流
- fix(db): `create_user()` 返回字典缺少 `jwt_secret` — 注册后 `create_jwt()` 访问 `user["jwt_secret"]` 触发 `KeyError` 导致 500
- fix(auth-api-keys): API Key 端点（POST/GET/DELETE `/api/auth/api-keys`）添加 `_get_jwt_user_id()` — 这些端点在 EXEMPT_PATHS 中不受 middleware 保护，需自行解析 JWT 获取 user_id
- fix(server): 添加全局 `@app.exception_handler(Exception)` — 捕获所有未处理异常，统一返回 `{"detail": "..."}` JSON 格式而非纯文本 500
- fix(redirect-loop): 注册/登录/钱包登录端点返回 `Set-Cookie: aims_jwt` — 解决服务端 `/console` 无法读取 localStorage 中 JWT 导致的 `/console`→`/login`→`/console` 死循环
- fix(auth-me): 添加 `/api/auth/me` 和 `/api/auth/api-keys` 至 `EXEMPT_PATHS` — 避免 middleware EIP-191 鉴权拦截；`auth_me()` 改为直接解析 JWT cookie/Authorization header
- fix(console): `API_BASE` 默认值 `http://127.0.0.1:8000` → `""`（空字符串，使用相对路径）— 解决 Fly.io 生产环境所有 API 调用因 CORS/网络错误失败的问题
- fix(jwt): `create_jwt()` `sub` 字段 int → str — PyJWT 验签要求 `sub` 必须是 string，否则抛出 `Subject must be a string` 导致 `/api/auth/me` 一直返回 401
- fix(console-buttons): 前端全按钮 JWT fallback 大检修 — 新增 `smartHeaders()` 函数（EIP-191 MetaMask 签名失败时自动降级为 JWT-only）+ 修复 publishTask/oneClickIntegrate/boostReward/claimTask/simulateVaultPayment/saveContributors/confirmBuyout 共 7 个关键函数的鉴权头生成，消除按钮无反应问题 + toast 函数异常安全包装 + 添加 DOMContentLoaded 页面初始化（自动加载 skills 列表 + 自动重连 MetaMask）

## [2026-06-16]
### 新增
- feat(boost): `POST /api/tasks/{id}/boost-reward` — 动态加价催单端点（vault funded 状态可追加奖励金，boost_history 审计链，SSE vault_boosted 广播）
- feat(docs): `GET /integration-docs` — 多平台 AI 工具集成文档路由（Cursor/Claude Code/OpenClaw/Hermes/Codex 平台卡片，One-Key Auth）
- feat(splitter): `POST /api/developer/set-contributors` — 多贡献者分账配置端点，支持按比例拆分 70% 开发者份额
- feat(splitter): `_settle_vault()` 多贡献者分账 — 自动解析集成数据的 co_contributors，按比例分配 70% 开发者份额至各钱包
- feat(splitter): `_penalize_contributors()` — AI Judge 失败时连带扣分机制（开发者 + 所有 co-contributor 各 -10 credit）
- feat(console): `static/console.html` — vault 面板新增 Boost Reward ⚡ 加价 UI（金额输入/按钮/总加价显示），vault funded 后自动启用 boost section
- feat(console): `static/console.html` — 一键接入表单新增 Co-Contributors Split 多贡献者配置 UI（动态行添加/删除/保存，实时百分比总计）
- feat(console): `static/console.html` — Task Market 抢单池新增 boost 徽章（已加价任务显示 ⚡ 标签）
- feat(discovery): `/api/discovery` — 新增 boost-reward 和 set-contributors 操作记录
### 修改
- feat(server): `IntegrateRequest` 扩展 co_contributors 可选字段 — 一键接入时附带多贡献者配置
- feat(server): `Discovery` 端点 — Task Vault 分类新增 boost-reward，Developer Integration 分类新增 set-contributors
- feat(console): `oneClickIntegrate()` — 提交时自动收集 DOM 中 co-contributor 行数据
- feat(console): `showVaultPanel()` / `pollVaultStatus()` / `simulateVaultPayment()` — boost section 状态联动（非 funded 禁用/opacity 0.4）
- feat(test): `scripts/test_trigger_biz.py` — E2E 业务触发测试脚本，跨境贸易结算全链路（POST /api/run → DeepSeek AI Judge → Worker claim/submit → on-chain settlement）
- feat(vault): `src/gateway/server.py` — `DEVELOPER_INTEGRATION_NS` + `TASK_VAULT_NS` 常量，`_generate_vault_address()` 确定性唯一 vault 地址生成（`0xV` + SHA256），`_settle_vault()` 70/25/5 分账，`POST /api/developer/integrate` 一键接入端点（自动识别 URL vs Skill），`POST /api/tasks/{id}/simulate-fiat-payment` 法币充值模拟，`GET /api/tasks/{id}/vault-status` 状态轮询，`POST /api/tasks/{id}/settle-from-vault` 管理手动结算
- feat(vault): `src/gateway/server.py` — `publish_task` 响应升级为 `PublishTaskResponse`，新增 vault 自动生成（`unfunded` 状态）；`submit_task` 插入 vault settlement 门控（AI Judge 通过后 vault-funded 优先结算）
- feat(console): `static/console.html` — One-Click Integration 一键接入 UI（Developer 选项卡，skill/URL 输入 + 钱包绑定 + 状态展示 + 自动注册 70% 分润）；Task Vault 扫码付款面板（Consumer 发布后展示 vault 地址/余额/QR 模拟/付款触发按钮/状态轮询）；新增 `oneClickIntegrate()`/`fetchIntegrationStatus()`/`showVaultPanel()`/`simulateVaultPayment()`/`pollVaultStatus()` JS 函数
### 新增
- feat(auth): `static/login.html` — 双轨登录注册页面（Email+密码表单 + MetaMask Web3 一键连接）
- feat(auth): `POST /api/auth/register` — 用户注册端点（bcrypt 密码哈希 + JWT 发放）
- feat(auth): `POST /api/auth/login` — 邮箱密码登录端点（JWT 令牌 + 钱包绑定）
- feat(auth): `POST /api/auth/wallet-login` — EIP-191 钱包签名免密登录（自动创建钱包账户）
- feat(auth): `POST /api/auth/link-wallet` — 钱包地址关联至已有 JWT 账户
- feat(auth): `GET /api/auth/me` — 当前用户信息查询（JWT 保护）
- feat(auth): `GET /login` — 登录页路由
- feat(auth): JWT 中间件 — 自动验证 `Authorization: Bearer <JWT>`，`/` 和 `/console` 页面强制登录重定向
- feat(db): `src/gateway/database.py` — 链下 SQLite 安全数据库（users/api_keys/payments 三表，bcrypt 密码 + WAL 模式）
- feat(apikey): `POST /api/auth/api-keys` — 生成 `sk-aims-` 前缀 API 密钥
- feat(apikey): `GET /api/auth/api-keys` — 列出非撤销密钥（仅前缀）
- feat(apikey): `DELETE /api/auth/api-keys/{id}` — 撤销 API 密钥
- feat(apikey): console 面板 — Developer 标签新增 API Key 管理 UI（生成/复制/撤销表格）
- feat(apikey): API Key 中间件鉴权 — 自动识别 `sk-aims-` Bearer token，适配 `POST /api/skill/task-action`
- feat(deploy): `fly.toml` — 新增 `[mounts]` volume 段（`aims_gateway_data` → `/data`）+ `DATABASE_URL` 环境变量
- feat(deploy): `Dockerfile` — 创建 `/data` 目录用于数据库持久化
- feat(discovery): `/api/discovery` — 新增 Auth & Security 分类（10 个端点）
- feat(api): `POST /api/skill/task-action` — Agent/CLI 统一端点（publish_task/boost_reward/query_account/claim_task/submit_task 五个动作）
- feat(docs): `GET /rules-and-docs` — 网络规则 + 集成指南合一路由（8 条行为规则 + 多平台卡片 + One-Key Auth + Unified API 文档）
- feat(console): `static/console.html` — Task Market 每行 ⚡ 加价按钮（`boostFromMarket()` 一键跳转 vault 面板）
- feat(console): `static/console.html` — topbar 导航栏新增 Console/Integration/Rules & Docs/API 链接
- feat(console): `static/console.html` — Consumer/Developer 信用分仪表盘（渐变进度条 + AAA/AA/A/B/C 等级徽章）
- feat(discovery): `/api/discovery` — 新增 Agent/CLI unified 分类 + Web Pages 分类（rules-and-docs/integration-docs/developer-guide）
- feat(api): `POST /api/wallet/withdraw` — 用户提现端点，Deduct 余额 + tx_ledger 追溯记录
- feat(api): `POST /api/wallet/fiat-deposit` — 法币充值中继桥（mock Stripe），USD→USDC 自动兑换 + tx_ledger 记录
- feat(api): `GET /api/wallet/history` — 用户历史账本查询，支持 type/deposit/withdraw/task_deduction 分类
- feat(deposit): `wallet_deposit` 记录 tx_ledger 条目 — 每笔充值自动入账
### 修改
- feat(worker): `src/worker/utils/signer.py` — HMAC-SHA256 → EIP-191 personal_sign，Worker 通过 `AIMS_WORKER_KEY`/`AIMS_WORKER_WALLET` 环境变量 EIP-191 签名，HMAC 保留为向后兼容回退
- feat(worker): `src/worker/worker.py` — 搜索词感知三池 Mock（electronics/wholesale/components），Canary `_canary_token` 透传修复 DeepSeek 低分问题
- fix(judge): `src/judge/judge_agent.py` — `max_tokens` 256→1024 适配 DeepSeek v4 推理长回复，增加截断 JSON 修复启发式
- feat(server): `src/gateway/server.py` — JudgeEngine 模型名从 `LLM_MODEL_NAME` 环境变量读取，生产切换 `deepseek-v4-flash`
- fix(config): `docker-compose.prod.yml` — `LLM_MODEL_NAME` 修正为 `deepseek-v4-flash`（原 `deepseek-chat` 被 DeepSeek API 拒绝）
- docs(deploy): `DEPLOY.md` — 追加入《AIMS 2.0 系统业务与功能梳理报告》9 大板块
- chore(brand): 全局 `AIMS Network` → `AIMS Gateway` — 修正 3 个 HTML、2 个 Markdown、4 个 Python 源码共 15 处品牌引用
- feat(frontend): `static/index.html` — 新增 Canary 反盗版三层防御、Treasury Isolation 双钱包架构、4+1 Commerce Matrix Free Trial 模式
- feat(console): `static/console.html` — 新增拖拽上传 ZIP Skill、快速充值面板（6 档预设+自定义）、审计账本查询器（task_id 过滤 + 分类）
- docs(deploy): `project_document/FLYIO_DOMAIN_GUIDE.md` — Fly.io 域名绑定指南（CNAME www.aimsgateway.com → aims-gateway.fly.dev）
- **feat(cleanup): 全局 Worker 质押概念清除** — `index.html` 3 处（collateral → zero-barrier/slashing→AI Judge/treasury cleanup） + `docs.html` 1 处（staked collateral → quality strike） + `WEBSITE_COPY.md` 2 处 + `AGENT_INTEGRATION_GUIDE.md` 1 处 + `KNOWLEDGE.md` 新增 2.0 免质押政策
### 新增
- feat(api): `POST /api/tasks/publish` — Task Market 发布任务端点，含 escrow freeze + credit score 门控
- feat(api): `GET /api/tasks/pending` — 列出 PENDING 任务（免认证），供 Developer 抢单池 UI 消费
- feat(api): `POST /api/tasks/claim-specific` — 按 ID 精准确认任务，custom 任务验证信用分门控
- feat(api): `GET /api/worker/credit-score/{wallet}` — Worker 信用分查询（免认证）
- feat(api): `POST /api/worker/credit-score` — Worker 信用分设置（Admin，EIP-191 认证）
- feat(docs): `AIMS_SKILL_GUIDE.md` — 外部开发者接入指南（Python 示例/EIP-191/AI Judge/Task Market/API 表格/Python SDK）
- feat(api): `GET /developer-guide` — 路由将 AIMS_SKILL_GUIDE.md 渲染为 Dark 主题 HTML
### 修改
- feat(broker): `src/gateway/broker.py` — BrokerTask 新增 task_name/description/is_custom/credit_score_required 字段，新增 get_pending_tasks()/claim_specific_task() 方法
- feat(console): `static/console.html` — Consumer 选项卡新增 Publish Task 表单（task_name/budget/custom toggle/description），Developer 选项卡新增 Task Market 抢单池表格 + 信用分门控弹窗
- feat(server): `src/gateway/server.py` — 新增 PublishTaskRequest/ClaimSpecificRequest/CreditScoreRequest 等 Pydantic 模型，Discovery 新增 Task Market + Worker Credit 分类，auth 豁免 credit-score GET
### 验证
- **E2E 全链路通过**: task-0006 (worker-002) → DeepSeek Score ≥80 → SETTLED → on-chain settlement 执行成功 ✓
- **API 测试通过**: GET /api/tasks/pending 返回 200 + 空列表，GET /api/worker/credit-score/{wallet} 返回 200 + 默认 0，POST /api/worker/credit-score 需 EIP-191 认证，/developer-guide 返回 HTML 渲染文档

## [2026-06-15]
### 新增
- feat(circuit_breaker): `src/gateway/circuit_breaker.py` — 三阶智能熔断隔离（CLOSED/HALF_OPEN/OPEN），3 连续失败→降级，6 累积→熔断，120s 冷却自愈，持久化计数器，SSE 黄/红警回调
- feat(stress): `tests/stress_cluster_simulation.py` — 多 Worker 并发压测 + 熔断韧性验证，10 async EIP-191 Worker × 50 请求/5s 突发，4 场景（公平路由/CB 衰减/自愈/Admin 控制），Bloomberg 终端日志
### 修改
- feat(server): `src/gateway/server.py` — CircuitBreaker 全局实例集成，`/api/run` 503 熔断门，`submit_task` Judge 评分 success/failure 联动状态机，SSE 桥接
- feat(server): `src/gateway/server.py` — 新增 `POST /api/admin/emergency-pause`（全网紧急暂停+红警）、`POST /api/admin/reset`（管理复位）、`GET /api/admin/circuit-breaker`（状态快照）
- feat(console): 新增 Free Trial 动态状态指示器（剩余次数 + 进度条 + 增强卡片）
- feat(console): 新增 Commerce Mode 切换面板（Metered/Subscription/Free Trial 按钮组 + Buyout Perpetual License 交互按钮 + 模态确认框）
- feat(console): 新增 Canary Watermark Status 三层防御指示器（Worker 面板，ECDSA Token/Replay Shield/Piracy Blacklist）
- feat(console): 新增 switchBillingMode()/updateCanaryStatus() 等 JS 功能函数，Wire 至 Worker 节点启停生命周期
### 修复
- fix(stress): `tests/stress_cluster_simulation.py` — 修复 Worker 注册失败（`seed_dev_usdt` 使用 wallet 地址而非 worker_id 导致 key 不匹配）+ Worker 循环终止竞态（claim_task 返回 None 时未检查完成条件导致无限循环）；4 场景全部 PASSED ✓
### 新增
- feat(ops): `docker-compose.yml` — 多节点集群化容器编排，一键拉起 gateway-server + redis-coordinator + 3× worker-node（独立钱包/DRM 挂载），healthcheck 全链路依赖等待
- feat(demo): `scripts/demo_day_master.py` — Demo Day 4 幕自动化路演脚本（PLG 闪电破局/70/25/5 密码学分账/SLA 铁面裁决退款/熔断极限自愈），Bloomberg 终端色彩，SSE 事件监控
- feat(docs): `project_document/PRODUCTION_READY.md` — Base Mainnet 生产网迁移清单（合约部署/多签/USDC/热钱包安全/Worker 黑盒防线/成本预估/回滚方案）
### 修复
- fix(demo): `scripts/demo_day_master.py` — 6 项修复：Alice 余额不足 (`seed_usdt` $0→$2)、GATEWAY_KEY 截断 31→32 bytes（缺失 `944`）、InMemorySettlementContract 集成（`contract_client=` 注入 + `deposit()`/`register_developer()`）、FreeTrialManager API (`check_free_trial()`→`is_trial_eligible()`)、余额源 (MockLedger→contract)、Refund mock（跳过真实扣款）
### 新增
- feat(prod): `docker-compose.prod.yml` — Base 主网离线部署 Compose（镜像锁定 `redis:7-alpine`/`python:3.11-slim`，`PRODUCTION=true`，凭证 `${VARIABLE}` 注入无默认值，Worker `user:1000` + `cap_drop:ALL` + `read_only` 工业隔离）
- feat(prod): `scripts/deploy_mainnet.sh` — 交互式 Shell 点火脚本（离线镜像阻断检查 + `read -p` 逐项采集主网参数 + `docker-compose up` + 5 轮 ChainListener CLOSED 健康轮询）
- feat(docs): `project_document/PRODUCTION_READY.md` (§10) — 主网上线看盘手册（Redis AOF 资金追踪 / PLG 灰度盯盘 / DeepSeek Judge 审计 / CB 熔断快照 / Dashboard One-Liner）

## [2026-06-13]
### 新增
- feat(test): `tests/e2e_testnet_simulation.py` — E2E Testnet Simulation 双流联动测试，PLG First-Task-Free → AI Judge 92/100 → 70/25/5 补贴结算 (Flow 1 PASS) + Metered Escrow → AI Judge 74/100 → SLA 自动退款 (Flow 2 REFUND)，Bloomberg 终端日志，6 确定性 EVM 地址，DRM 包装器模拟，资金守恒审计
- feat(knowledge): `project_document/KNOWLEDGE.md` — 新增 E2E Testnet Simulation 双流联动测试模式文档（AI Judge 评分引擎/DRM 三层包装/6 地址/Bloomberg 日志/CLI 网络选择）
### 修改
- fix(gateway): `src/gateway/billing.py` — `CommerceEngine` 新增 `_record()` 委托方法转发至 `BillingEngine._record()`，修复 `charge_and_settle()` 在免费试用/订阅/买断路径的 `AttributeError` 潜在 bug
- feat(docs): `project_document/DEVELOPMENT.md` — 添加 Phase 4 E2E Testnet Simulation 和 billing.py `_record()` 修复条目
- feat(docs): `project_document/CHANGELOG.md` — 添加 2026-06-13 新条目
### 新增
- feat(gateway): `src/gateway/server.py` — 新增 `POST /api/auth/pre-check` AIMS_GATEWAY_AUTH 信标验签端点 + `GET /api/v2/feed/stream` SSE 实时结算流端点
- feat(frontend): `static/console.html` — MetaMask 连接后 Base Sepolia `wallet_switchEthereumChain` 网络切换提示 + `AIMS_GATEWAY_AUTH` 信标签名验证 + Mock 数据流替换为 EventSource SSE 实时连接
- feat(frontend): `static/index.html` — 全局结算大屏替换为 EventSource SSE 实时连接至 `/api/v2/feed/stream`
### 修改
- feat(billing): `src/gateway/billing.py` — `CommerceEngine` 新增 `on_settlement` 可调用回调参数，`_record()` 方法在写入审计账本后调用回调广播结算事件
- feat(server): `src/gateway/server.py` — `broadcast_settlement` 定义移至 `CommerceEngine` 实例化之前修复 NameError；`EXEMPT_PATHS` 新增 `/api/auth/pre-check` 和 `/api/v2/feed/stream`；FastAPI `docs_url` 改为 `/api/docs`，`openapi_url` 改为 `/api/openapi.json`
### 新增
- feat(judge): `src/judge/judge_agent.py` — `JudgeEngine` AI 裁判评分引擎（LLM-as-a-Judge 0-100，OpenAI `gpt-4o-mini`），确定性回退评分，`score < 80` 自动 `refund_on_chain()` + SSE 红警广播
- feat(chain): `src/gateway/chain_listener.py` — `ChainListener` 异步后台线程轮询合约事件，双模式（InMemory `_event_buffer` + Web3 `w3.eth.get_logs`），ABI 事件解码，Redis 持久化 `last_processed_block`
- feat(contract): `src/chain/contract_client.py` — `InMemorySettlementContract` 新增 `_event_buffer` 事件缓冲，`settle_task()`/`refund_task()` 追加事件供 ChainListener 消费
- feat(server): `src/gateway/server.py` — `lifespan` 启动时 `_chain_listener.start()`；`submit_task` 插入 AI Judge 质量门（评分 < 80 触发 `refundTask` + `REFUNDED`）；`POST /api/admin/judge` 与 `GET /api/admin/listener` 管理端点
### 修改
- feat(deps): `requirements.txt` — 新增 `openai>=1.0,<3.0`（AI Judge）和 `eth-abi>=5.0,<6.0`（事件 ABI 解码）
- feat(docs): `project_document/DEVELOPMENT.md` — 添加 Phase 6 链上事件监听器与 AI 裁判盲审条目
- feat(docs): `project_document/CHANGELOG.md` — 添加 2026-06-13 Phase 6 条目

## [2026-06-12]
### 修改
### 新增
- feat(skills): `src/skills/tiktok_competitive_intel.py` — TikTok Shop 竞品情报 Skill，马来西亚/东南亚跨境电商价格/销量/广告/欺诈多维度监控，确定性 Mock + 6 类模板产品 + Fraud Screening 启发式检测
- feat(skills): `src/skills/manifests/tiktok_competitive_intel/manifest.json` — 完整 manifest 含 Commerce Matrix 定价（Metered: 0.05 USDC / Sub: 19.99 USDC / Buyout: 199 USDC）、SEA 10 标签分类、中文 agent_hint
- feat(docs): `project_document/DRM_PUBLISH_GUIDE.md` — aims-cli 8 步 DRM 加壳发布指南（init/login/PyArmor/Cython/AES-256-GCM/EIP-191 签名/发布/链上验证），含 3 种计费场景和 Base Sepolia/Mainnet 迁移附录
- feat(frontend): `static/index.html` — 全量重写 AIMS 2.0 着陆页，70/25/5 + 95/0/5 双分账表、PLG First-Task-Free 横幅、3 角色专区（Contributor/Consumer/Worker）、Commerce Matrix 3 模式对比表、4 大优势重写、How It Works 双象限分账
- feat(frontend): `static/docs.html` — 全量重写开发者文档，增加 aims-cli 工具链 3 节（init/login/publish 8 步 DRM）、Revenue Split 表 Q1/Q2-Q5、Billing Modes 表、API 端点表新增 register-metadata/request-key、FAQ 更新
- feat(frontend): `static/console.html` — PLG 全功能升级，Auth→Free Trial Check→Balance Check→Execution→PoT→Settlement 6 步管道、Billing Mode 选择器（Metered/Subscription/Buyout/Free Trial）、Trial 追踪（usedTrials + 402 弹窗 "Use Free Trial"）、PLG Badge `★ 1 Free Trial / Skill`
- feat(docs): `project_document/WEBSITE_COPY.md` — 全量重写同步 HTML 文案，11 节覆盖 Hero、价值主张、3 角色、4 优势、How It Works、PLG、Commerce Matrix、Agent 集成、Policy、aims-cli 工具链、技术规格
### 重构
- refactor(gateway): `src/gateway/billing.py` — 全量重构，新增 `CommerceEngine` 类实现多维计费结算路由（Metered/Subscription/Buyout 三种模式），`RevenuePhase` 收入分配合约枚举（Q1 70/25/5 ↔ Q2-Q5 95/0/5），PLG 国库补贴池（`pool:plg`），按 skill 定价系统，Subscription/Buyout Pool 资金池管理，消费者支出追踪
### 新增
- feat(gateway): `server.py` — 新增 8 个 `/api/commerce/*` 端点：`POST /api/commerce/subscription`（订阅购买）、`POST /api/commerce/buyout`（买断购买）、`GET /api/commerce/pricing/{skill_id}`（定价查询）、`POST /api/commerce/pricing`（定价设置）、`GET /api/commerce/pools`（池余额）、`GET/POST /api/commerce/phase`（收入阶段查询/切换）、`POST /api/commerce/seed-plg`（PLG 国库种子）、`GET /api/commerce/spend/{wallet}/{skill_id}`（消费追踪）
- feat(gateway): `server.py` — `submit_task` 结算路径迁移至 `commerce.charge_and_settle()`，支持模式感知的 PoT 生成；`FreeTrialError` 导入补全
### 修改
- feat(frontend): `static/index.html` — 新增全球实时结算大屏（高频滚动 Bloomberg 风格 Settlement Feed，AI Judge 评分 + 70/25/5 分账实时流）、Google/Apple 社交登录按钮（Coming Soon）、SLA 争议仲裁保障（80/100 LLM-as-a-Judge 阈值 + 自动全额退款）、Advantage 04 重命名为 Cryptographic SLA Dispute Escrow
- feat(frontend): `static/console.html` — 新增控制台实时结算流面板、Google/Apple Web2 登录按钮（钱包区域）、SLA 保障文案强化、结算 Mock 数据流动态推送

### 新增
- feat(canary): 创建 `src/gateway/canary.py` — `CanaryManager` ECDSA 签名水印系统，支持 token 生成/验证/重放检测/Worker 黑名单
- feat(canary): `POST /api/run` 注入 `_canary_token`（时间戳+随机 Hash+ECDSA 签名）到任务 payload，Worker claim 时自动携带
- feat(canary): `POST /api/tasks/submit` 增加金丝雀验证门 — 缺失/伪造/重放 Token → `FORBIDDEN_PIRACY` 熔断，阻止 70/25/5 分润，自动拉黑 Worker 地址
- feat(canary): `royalty_test_skill/logic.py` 增加 `_canary_token` 透传 — 从 params 读取并写入 result_data 供网关验证
- feat(licensing): 创建 `src/gateway/licensing.py` — `LicensingManager` 单次随机种子密钥发放，`keccak(gateway_key ++ task_id ++ user_address ++ random)` 种子推导，`ACTIVATED_ONCE` 状态追踪
- feat(licensing): `POST /api/skills/register-metadata` — 轻量化路由表注册接口，存储 skill_id/contributor_address/encrypted_source，上限数 KB，重复注册 409
- feat(licensing): `POST /api/licensing/request-key` — 三道强制校验（Task 锁仓态 CLAIMED/SUCCESS / EIP-191 钱包归属匹配 Task owner / `is_license_issued()` 防重放），通过后下发单次随机种子
- feat(discovery): 新增 "Licensing & Routing" API 类别文档，包含 `/api/skills/register-metadata` 和 `/api/licensing/request-key`
- feat(cli): 创建 `src/cli/schema.py` — `AIMSConfig(BaseModel)` 8 字段 + `MonetizationConfig` 2×2 矩阵（worker_collab/direct_skill × pay_per_task/subscription），Q1 70/25/5 Q2–Q4 95/0/5，subscription 强制 rate_limit_per_day
- feat(cli): 创建 `src/cli/credentials.py` — `~/.aims/credentials` 以太坊 keystore v3 加密存储（`Account.encrypt/decrypt`），目录 0700/文件 0600 权限保护
- feat(cli): 创建 `src/cli/main.py` — Click CLI 骨架，`init`（2×2 矩阵交互引导 + 收入分配合约展示）/ `login --private-key`（私钥加密持久化）/ `publish`（全管道编排）
- feat(cli): 创建 `bin/aims-cli` — 入口点脚本，`pip install click>=8.1`
- feat(cli): 创建 `src/cli/obfuscator.py` — `wrapper.so` 二进制桩（4KB ELF 占位）
- feat(cli): 创建 `src/cli/encryptor.py` — AES-256-GCM 内核加密（`cryptography.hazmat` AESGCM，随机 12B nonce + ciphertext 格式，目录 tar 加密）
- feat(cli): 创建 `src/cli/signer.py` — EIP-191 版权签名（`AIMS-SKILL-AUTH:{skill_id}:{key_hash}:{price}` 格式）
- feat(cli): 创建 `src/cli/publisher.py` — 8 步发布管道 + ASCII 审计表（5% Platform Treasury 分账明细）
- feat(cli): `main.py` init 命令重写为 2×2 矩阵交互，publish 命令新增 `--gateway-url`/`--entry-point`
- chore(deps): `requirements.txt` 添加 `cryptography>=42.0,<44.0`
- feat(cli): schema `MonetizationConfig` 2×2 → 2×3 矩阵升级，新增 `buyout` 模式 + 风控熔断断路器（worker_collab+buyout 禁止）+ Q5 `quadrant_label`
- feat(cli): `main.py` init 命令 billing_mode 新增 `buyout` 选项，买断制跳过 rate_limit_per_day 提示
- feat(cli): `publisher.py` 审计表新增 `_rate_limit_display()` 辅助函数，buyout 模式显示 "Perpetual (buyout)"
- fix(cli): obfuscator.py ELF 桩 struct.pack 数量不匹配修复 — 简化 raw bytes 实现
- feat(cli): schema `AIMSConfig` 新增 `enable_universal_free_trial` 字段，强制 validator 锁定为 True
- feat(cli): `main.py` init 新增 "Universal First-Task-Free Policy" 协议展示
- feat(cli): `publisher.py` 审计表新增 "Universal First-Task-Free Routing" 路由逻辑面板，register-metadata body 带 monetization 字段
- feat(gateway): 创建 `src/gateway/trial.py` — `FreeTrialManager` 按 (wallet, skill_id) 追踪使用量，支持 trial/subscription/buyout 三种模式支付证明验证，FreeTrialError 异常抛出 402 锁断
- feat(gateway): `server.py` `/api/run` 集成 trial 检查 — 第 1 次调用免费跳过余额验证，第 2+ 次按 billing_mode 验证支付证明；`register_skill_metadata` 接受并持久化 monetization 配置；新增 `_get_skill_billing_mode()` 辅助函数
### 验证
- **正常流程**: 携带 `_canary_token` 提交 → ECDSA 验签通过 → `COMPLETED` + PoT 生成 ✓
- **盗版检测**: 无 `_canary_token` 提交 → `FORBIDDEN_PIRACY` + Worker 拉黑 + 0 审计条目 ✓
- **重放防护**: Token 一次性使用（`canary:used:{task_id}` 标记），二次提交 409 ✓

## [2026-06-11]
### 修改
- fix(contract_client): `_send_tx()` 中 `estimate_transaction` → `estimate_gas`（web3.py v7 API 兼容）
- fix(server): 移除 test_skill 计费旁路，使其通过标准 `request_settlement()` 触发链上结算
- fix(scripts): 修正 `scripts/full_settlement_test.py` 中 DEV_KEY 常量 — 映射到正确的 Hardhat Account #2 地址
- fix(server): `wallet_deposit` Web3 模式 500 崩溃 — 添加 `_local_deposits` 内存回退字典，网关无需用户私钥即可完成代理充值
- fix(server): `serve_logic` 对内置 skill 返回 404 — 为 `test_skill` 创建 `skills/uploaded/test_skill/logic.py` 骨架逻辑脚本并注册 manifest
- fix(skills): `test_skill` 的 `input_schema` 添加 `additionalProperties: true`，解除所有参数限制，空 `{}` 和任意字段均放行
- feat(skills): `SkillManifest` 新增 `agent_hint` 可选字段 — 自然语言 Agent 提示词契约，通过 discovery 端点向外暴露
- feat(skills): `test_skill` 恢复 `repo_path` 必填字符串校验 + `agent_hint` 中文指引 AI 客户端自动补全路径
- fix(billing): `check_user_balance` 在 Web3 模式跳过错误的 on-chain auto-seed（gateway 未 approve USDC 导致 `ERC20InsufficientAllowance` revert），改用 on-chain + local 和值校验
- fix(server): `admin_setup` 调用不存在的 `simulate_stripe_webhook()` 导致 AttributeError 500 — Web3 模式下跳过该行
- fix(server): `run_skill` 余额校验纳入 `_local_deposits` 本地代理充值
- feat(billing): 添加可逆审计追踪系统 — `_audit_ledger` 记录每笔 settlement/refund 的 [ts, action, roles, amounts]，支持按 task_id 回溯和全局聚合查询
- feat(server): 添加 `GET /api/admin/audit` 审计回溯端点，返回完整结算流水和统计摘要
- feat(server): `POST /api/skills/register-developer` — 通过网关 API 注册 Skill 开发者地址，BillingEngine 自动为开发者分配 70% 分润
- feat(skills): `SkillManifest.agent_hint` 字段支持自然语言提示词，指导 AI 客户端正确构造请求参数
- fix(server): `GET /api/tasks/{task_id}/pot` 支持 `?party=` 查询参数指定领取方，无参数时自动回退至 task worker_id
- feat(skills): 创建 `royalty_test_skill` — 自定义 zip 上传 Skill，严格 `output_schema`（`status`+`message` 必填），演示 70/25/5 动态分润全流程
- feat(store): `SkillStore.install_zip()` 期望 zip 根目录下包含 `manifest.json` + `logic.py`
### 新增
- feat(scripts): 创建 `scripts/deploy_agent_gateway.cjs` — 部署 AIMSAgentGateway（70/25/5）+ MockERC20 到 Hardhat 本地节点
- feat(scripts): 创建 `scripts/fund_test_user.py` — 测试用户 MockUSDC 预充值脚本
- feat(scripts): 创建 `scripts/e2e_web3_test.py` — E2E Web3 结算测试（run→claim→submit→on-chain）
- feat(scripts): 创建 `scripts/full_settlement_test.py` — 完整结算生命周期测试（开发者注册 + 70/25/5 分账 + Worker/Developer PoT 领取）
- feat(hardhat): 启用 `viaIR: true` 解决 Solidity `stack too deep` 编译错误
- feat(skills): 创建 `skills/uploaded/test_skill/logic.py` — test_skill 骨架逻辑，`run()` 返回 SUCCESS 和输入回显
- feat(skills): 在 `SkillStore` 中注册 `test_skill` manifest 和 logic.py 路径，使 `GET /api/skills/test_skill/logic` 可响应 200
### 验证
- **Full Settlement Lifecycle 通过**: 开发者注册 → task-0005 → COMPLETED → 0.05 USDC 结算 → Worker 0.0125 USDC (25%) + Developer 0.0350 USDC (70%) + Treasury 0.0025 USDC (5%) 全部 PoT 领取成功
### 技术决策
- 部署脚本使用 `--network localhost`（而非 `--network hardhat`）连接持久化 Hardhat 节点- DEV_KEY 需使用 Hardhat Account #2 实际私钥：`0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a`（非 `Account.from_key()` 推导的公钥对应私钥）

## [2026-06-09]
### 新增
- feat(billing): 创建 src/gateway/billing.py — BillingEngine 信用计费引擎（COST_PER_TASK=0.05、80/20 分账、Lua 脚本原子结算、Reservation 防双花模式）
- feat(ledger): 创建 src/gateway/ledger.py — TransactionLedger 交易历史账本（deposit/task_deduction/worker_payout/owner_revenue 四类交易、每用户索引、全局排序查询）
- feat(server): POST /api/wallet/deposit + GET /api/wallet/balance — Wallet API（HMAC-SHA256 自动认证）
- feat(server): run_skill() 集成信用预检（402 余额不足）+ reserve 预留；submit_task() 集成 settle 结算 + txn_ledger 记录
- feat(server): Discovery 端点新增 "Wallet & Credits" 类别文档
- feat(storage): storage.py pipeline() 上下文管理器 + _InMemoryPipeline 类（多 Key 原子操作支持）
- feat(test): 创建 tests/test_billing.py — 35 个测试（余额/预留/结算/账本/全生命周期）
- feat(gateway): GET /api/discovery — Auto-Discovery 自文档化端点，动态扫描 registry + skill_store 生成技能列表，OpenAPI 3.0 子集格式，discovery_version 1.0.0
- feat(test): 创建 tests/test_discovery.py — 17 个测试覆盖端点结构/字段/技能动态列表/API 关键路径/免认证访问
- feat(test): 创建 tests/e2e_full_flow.py — 生产级 E2E 全流程测试（10 并发 Worker、SOCKS5 代理轮换、2s 浏览器指纹模拟、60s 吞吐量基准）
- feat(test): 清理 src/skills/manifests/project_document/ 意外复制
- feat(storage): storage.py 新增 dict namespace 操作（dict_set/dict_get/dict_delete/dict_keys/dict_all）和原子计数器（incr）
- feat(broker): TaskBroker Redis 持久化 — publish/claim/complete/check_timeouts 全链路写透 Redis，启动自动恢复
- feat(ledger): MockLedger Redis 持久化 — 13 个 namespace 覆盖所有账本状态（balance/escrow/collateral/strikes/reputation/rating）
- feat(server): 共享 Storage 实例注入 MockLedger + TaskBroker，`REDIS_URL` 未设置时自动降级内存模式
- feat(broker): Pipeline 任务链 — BrokerTask 新增 `pipeline`/`pipeline_step`，`complete_task()` 自动推进并重新排队，`submit_task()` 延迟结算至最终步骤
- feat(bootstrap): 多模态输入预处理 — `preprocess_multimodal()` 支持 base64 解码和 URL 下载，自动检测图像格式
- feat(deploy): Worker Dockerfile 安装 tesseract-ocr；requirements.txt 新增 opencv-python-headless/pillow/pytesseract
- feat(gateway): Discovery 端点技能 `capabilities` 字段 — 6 个内置技能定义能力标签，上传技能默认 `["custom"]`
- feat(server): RunRequest 新增 `pipeline` 参数支持多步骤任务链声明
- feat(gateway): Discovery 响应新增 `documentation_root` 字段指向 `docs/MASTER_INDEX.md`
- feat(docs): 创建 `docs/MASTER_INDEX.md` — AI Agent 单入口协议索引（Discovery/HMAC/Run/Pipeline/Heartbeat/Upload/Bootstrap）
- feat(docs): 所有 markdown 文件添加 `<!-- Hermes-Verified -->` 版本元数据头部注释
### 修复
- fix(deploy): 生产环境 500 — python-multipart 缺失导致 FastAPI File() 参数启动崩溃（POST /api/skills/upload 需 multipart 支持）
- fix(test): e2e_full_flow.py 端口冲突 — 8765 被其他服务占用导致 404；改用 9876 + 智能健康检查验证网关字段
- fix(billing): _settle_in_memory worker==owner 时管道双写同一 Key 覆盖 — 合并 worker_share + owner_share 为一次 SET（#49）
- fix(storage): keys() 内存回退路径忽略 glob pattern — dict_all 误返回其他 namespace 数据（#49）
- feat(gateway): broker.py 新增 succeeded_count / claimed_count 状态查询属性
- feat(test): 创建 tests/test_agent_bootstrap.py — AI Agent 引导测试（14 个测试：discovery 获取 → documentation_root URL 可达性 → 7 个协议完整性 → input_schema 校验 → pipeline 文档验证 → 全流程端到端模拟）
- fix(docs): documentation_root 指向 GitHub raw URL `https://raw.githubusercontent.com/michaelxmchn/aims-gateway/main/docs/MASTER_INDEX.md`，外部 AI 代理（Hermes）免认证访问
- feat(gateway): server.py health 端点新增 tasks_succeeded 字段
### 修复
- fix(server): health 端点缺失 tasks_succeeded 导致 Pydantic ValidationError (500)
### 测试
- feat(test): 创建 tests/load_test_simulation.py — 20 Worker 多进程压力测试（HMAC-SHA256 签名，100 任务全通过 ✓）
- test(load): 负载测试 100/100 任务完成，111.7 tasks/s 吞吐量 ✓
- feat(gateway): 创建 src/gateway/skill_store.py — 动态 Skill zip 上传/校验/持久化（zip-slip 防护、manifest 验证、Redis + 磁盘双写）
- feat(gateway): server.py 新增 POST /api/skills/upload、GET /api/skills/{id}/logic、POST /api/run、GET /api/tasks/{id}/status 端点
- feat(gateway): server.py 中间件扩展覆盖 /api/skills/ 和 /api/run（HMAC-SHA256 全面认证）
- feat(gateway): ClaimResponse 新增 skill_logic_url 字段（Worker 零配置发现）
- feat(registry): install_skill 修复缓存空指针（_cache 为 None 时初始化空 dict）
- feat(worker): 创建 src/worker/bootstrap.py — 动态技能引导模块（fetch_logic + importlib 加载 + execute 调用）
- feat(worker): worker.py execute_task() 新增动态技能分支（有 payload 时 bootstrap 加载，无 payload 时 mock 回退）
- feat(worker): config.py 新增 LOGIC_ENDPOINT 配置
- feat(deploy): 创建 src/worker/Dockerfile — Worker 容器（Playwright Chromium + OpenClaw 集成）
- feat(deploy): requirements.txt 新增 playwright + openclaw 依赖
- feat(manifest): 创建 manifests/openclaw_skill.json — OpenClaw 互联 Manifest（/api/run 端点描述、HMAC 认证、输入/输出 Schema）
- feat(test): 创建 tests/e2e_dynamic_skill.py — 动态插件 E2E 测试（上传→/api/run→claim→bootstrap→submit→status）
### 新增
- feat(deploy): 创建 Dockerfile — python:3.11-slim，uvicorn 生产部署
- feat(deploy): 创建 fly.toml — Fly.io 部署配置（sin 区域，256MB，min_machines_running=1）
- feat(deploy): 创建 .dockerignore — 排除 .git/tests/__pycache__/.env 等
- feat(deploy): 创建 requirements.txt — fastapi/uvicorn/pydantic 锁定版本
### 修复
- fix(server): AIMS_SIGNING_SECRET 改为 os.getenv() 读取环境变量，生产部署不再硬编码
- feat(storage): 创建 src/gateway/storage.py — Redis KV 存储抽象层，自动降级为内存字典
- feat(deploy): fly.toml 新增 /api/health 健康检查配置（15s 间隔 / 5s 超时 / 10s 宽限）
- feat(deploy): requirements.txt 新增 redis + hiredis 依赖
- fix(deploy): .gitignore 新增 .project.agents/ 和 logs/ 条目
- chore(deploy): requirements.txt 补充 starlette + pydantic_core 递依赖锁定
- feat(worker): 创建 src/worker/ 生产 DePIN Worker（config.py / signer.py / worker.py）
- feat(server): 新增 POST /api/workers/heartbeat 端点 + workers_active 健康指标
- feat(deploy): requirements.txt 新增 requests 依赖（Worker HTTP 客户端）

## [2026-06-08]
### 新增
- feat(test): 创建 tests/e2e_integration_test.py — 8 阶段 E2E 集成测试（身份/Staking/Fault-Tolerance/Slashing/Tier-2 Billing/Wealth Audit/Dashboard）
- fix(test): e2e_integration_test.py — price_points 类型 int，initial_wealth 捕获时机后移至 Phase 3，staking check 考虑削减后余额
- feat(gateway): 创建 src/gateway/server.py — FastAPI 生产级 Gateway Server（claim/submit/health 三个端点）
- feat(gateway): broker.py 新增 get_task_meta / get_task_status 公开方法
- feat(ledger): 实现 Worker Registration — register_worker() 质押 $5 抵押金 + seed_dev_usdt()
- feat(ledger): 实现 Slashing Protocol — apply_penalty() 3 strikes 削减 $1 到 Treasury
- feat(broker): 实现 Proof of Result — validate_task_result() 校验 asin+price，失败自动 penalty
- feat(broker): check_timeouts() 超时回收联动 apply_penalty() strike 系统
- feat(sandbox): Worker 循环集成 validate_task_result() + corrupt_output 坏数据模式
- feat(test): 重写 tests/stress_test.py 为 Slashing Protocol 模型（40 任务，W3 削减 $1，WEALTH AUDIT PASSED ✓）
- feat(ledger): 实现 Double-Sided Reputation — submit_rating() + get_user_reputation() + get_skill_weighted_score()
- feat(ledger): 实现 Outlier Truncation — |rating - mean| > 2.5 自动抑制 + 信誉惩罚 -0.1
- feat(broker): BrokerTask / publish_task / claim_task 传递 skill_id 支持评分链
- feat(test): stress_test.py Double-Sided Reputation 验证 — 6 任务全完成，恶意 1.0 抑制，信誉 1.0→0.9，评分 5.0 不变，PASSED ✓
- feat(ledger): 实现 Compute Tier Billing — TIER_MULTIPLIERS {1:1.0, 2:2.5, 3:6.0} + gas = rate × tier_mult × duration
- feat(ledger): release_escrow_dynamic 改用 skill_meta 字典参数（compute_tier + developer_premium + skill_id）
- feat(broker): 实现 validate_result_generic — JSON Schema 通用验证器（type/required/properties/items/minimum/maximum）
- feat(broker): BrokerTask/publish_task/claim_task 新增 compute_tier 字段传递
- refactor(sandbox): Worker 循环改用 skill_meta + validate_result_generic 替换硬编码 asin+price 校验
- feat(test): stress_test.py 新增 Phase 3 Tier-2 Billing 验证（4.0s 2.5x gas=$0.1000 ✓）
- feat(test): stress_test.py 新增 Phase 4 Generic Validation Rejection 验证（corrupt output 拒绝 + strike ✓）
- feat(dashboard): 创建 src/skills/dashboard_skill.py — Tailwind + Chart.js 暗色仪表盘，数据聚合+浏览器弹出
- feat(cli): 创建 src/client/cli.py — aims dashboard 命令入口 + aims shell 包装脚本
- feat(manifest): 创建 dashboard_skill Document-Driven 定义（manifest.json + rules.md）
- feat(sandbox): dashboard_skill 注册到 SKILL_IMPLS
### 修复
- fix(test): stress_test.py 声誉测试阶段等待全部任务完成（completed_count 检查取代 pending_count 检查）
- fix(test): stress_test.py 移除未定义的 pytest.approx 引用，使用 abs 差值验证
- feat(broker): 实现 Stateful Task Claiming — claim_task() / complete_task() / check_timeouts() 状态机（PENDING/CLAIMED/SUCCESS/FAILED）
- feat(broker): 实现 Fault-Tolerance 超时回收机制 — CLAIMED >5s 自动 revert 到 PENDING
- feat(sandbox): start_worker_loop 改用 claim_task() + 新增 crash_simulate_after 模拟 Worker 崩溃
- feat(test): 重写 tests/stress_test.py 为 Fault-Tolerance 模型（3 Workers + Timeout Checker，WEALTH AUDIT PASSED ✓）
- feat(ledger): MockLedger 改 Points 为 USDT 稳定币语义，实现 JIT Escrow（freeze_usdt / settle_escrow / escrow_vault / 1% tax）
- feat(ledger): 实现 Dynamic Billing 系统 — create_escrow_hold + release_escrow_dynamic（Gas 计费 BASE_GAS_RATE=0.01 USDT/s + 开发者溢价 + Platform Tax 1%）
- feat(sandbox): ExecutionReceipt 新增 execution_time wall-clock 字段，amazon_scraper 模拟随机延迟 0.5-2.5s
- feat(demo): main.py 第 7 阶段改为 Dynamic Billing 演示 — 分项账单（Gas 费/溢价/税/Payout/Refund）
- feat(ledger): MockLedger 全线添加 threading.Lock() 保证并发安全，新增 total_system_wealth 快照
- feat(test): 创建 tests/stress_test.py 高并发压力测试（10 用户 × 5 次 = 50 并发交易，WEALTH AUDIT PASSED ✓）
- feat(broker): 创建 gateway/broker.py TaskBroker 中央线程安全 FIFO 任务队列
- feat(sandbox): 新增 start_worker_loop() DePIN Worker 守护线程，自动轮询+执行+结算 Gas 费
- feat(test): 重写 tests/stress_test.py 为 DePIN 模型（5 Workers × 30 Tasks，WEALTH AUDIT PASSED ✓）
- chore(init): Git 仓库初始化（main 分支）
- feat(scaffold): 运行 ADS scaffold 脚本生成 .project.agents/ 治理框架
- feat(config): 创建 AIMS 项目脚手架配置
- docs(prd): 填充 PRD 文档（愿景/用户/范围/功能定义/Q&A 确认）
- docs(arch): 填充 ARCHITECTURE 文档（领域模型/7 模块/DAG 依赖图/目录结构）
### 修复
- fix(main): release_escrow_dynamic() 签名不匹配 — 改用 skill_meta 字典参数
- fix(merkle): import json 作用域错误 — hash_record() 无法访问 json 模块
### 新增
- feat(mcp): 创建 src/client/mcp_server.py — MCP stdio 服务器（initialize/tools/list/tools/call）
- feat(cli): 扩展 CLI — aims exec/aims list/aims login/aims mcp 子命令
- feat(chain): 实现 user_identity_map + simulate_stripe_webhook() 法币入金桩
- feat(test): 创建 4 个单元测试套件 — Manifest/Registry/Log/Sandbox（47 tests）
### 重构
- refactor(runtime): 删除死代码 executor.py（已被 sandbox.py 替代）
- refactor(chain): settlement.py 重构 — 新增 UserIdentity + Stripe Webhook 支持
- feat(manifest): 创建 SkillManifest Pydantic 模型，对齐 LLM Tool Calling 格式
- feat(registry): 创建 SkillRegistry，支持本地 manifests/ 加载 + Anthropic/OpenAI 工具定义注入
- feat(router): 创建 GatewayRouter 万能入口，动态注入工具到 LLM + 串行编排
- feat(engine): 创建 DAG Engine 串行执行引擎
- feat(runtime): 创建 SkillRuntime 本地信任模式执行 + 日志记录
- feat(ledger): 创建 Append-only Log（JSONL 格式）+ Merkle 树工具
- feat(chain): 创建 ChainSettlement 存根 + SessionKeyManager
- feat(examples): 创建代码安全审计和 Git 变更日志两个种子 Skill manifest
- feat(entry): 创建 main.py 组装入口
- feat(manifest): SkillManifest 新增 staked_points（冷启动推广）和 frozen_until（冷却监狱）字段
- feat(registry): 实现优先级评分 Priority = Frequency + (Staked × 10) + 领域关键词匹配 + 连续失败追踪 + 冷却监狱
- feat(router): GatewayRouter 新增 parse_intent_to_workflow() + MockLLMProvider + 全 escrow 集成
- feat(sandbox): 创建 WorkflowEngine 执行引擎（try-except + output_schema 校验 + ExecutionReceipt）
- feat(ledger): 创建 MockLedger 非托管托管结算（freeze_points → settle_transaction + 罚没 2.0）
- feat(manifests): 创建 data_analyzer（数据分析报告）和 buggy_skill（故意失败用于测试监狱）
- feat(demo): 重写 main.py 为全生命周期演示（优先级评分、意图检测、托管结算、冷却监狱）
- feat(amazon_scraper): 创建 amazon_scraper 种子技能（竞品爬虫，含 rules.md + Python 实现）
- feat(rules): 为所有 5 个技能创建 rules.md Document-Driven 规则文件

### 重构
- refactor(manifests): skills/manifests/ 改为子目录结构，每个技能独立 manifest.json + rules.md
- refactor(registry): SkillRegistry 支持子目录遍历加载 + rules.md 缓存
- refactor(router): GatewayRouter 简化为轻量级上下文注入器，去除所有 LLM 调用代码
- refactor(sandbox): runtime/sandbox.py 重写为执行沙箱，持有 SKILL_IMPLS 实现注册表
- refactor(main): main.py 重写为 Document-Driven 工作流演示

### 修复
- 暂无

### 重构
- 暂无

## [2026-06-10]
### 新增
- feat(chain): 创建 src/chain/eip712.py — EIP-712 签名/验签（sign_eip712_message / verify_eip712_signature），支持 AIMSRunRequest/AIMSSubmitRequest/AIMSDepositRequest 三种类型
- feat(chain): 创建 src/chain/nonce_manager.py — NonceManager 每地址单调 nonce 追踪（Storage 持久化）
- feat(chain): 创建 src/chain/pot.py — POTManager 生成/验证/存储 Proof-of-Task（ECDSA 签名 keccak256(taskId ++ workerAddress)）
- feat(chain): 创建 src/chain/contract_client.py — SettlementContractClient ABC + InMemorySettlementContract（纯 Python 镜像 Solidity）+ Web3SettlementContract（web3.py 生产封装）
- feat(chain): 创建 src/chain/abi.py — 合约 ABI JSON 常量和 USDC 6 位小数常量
- feat(contracts): 创建 contracts/AIMS_Settlement.sol — Solidity 合约（deposit/withdraw/settleTask/claimReward/claimOwnerFees，80/20 分账，nonce + taskId 双重防重放）
- feat(server): EIP-712 签名认证中间件 — 替换 HMAC-SHA256，验证 EVM 地址/时间窗口/deadline/nonce/签名恢复
- feat(server): POST /api/tasks/{task_id}/pot — 获取 Proof-of-Task 端点
- feat(test): 创建 tests/test_eip712.py — 9 个测试（sign/verify/wrong_signer/tampered/value_builders）
- feat(test): 创建 tests/test_pot.py — 9 个测试（generate/verify/tamper/storage）
- feat(test): 创建 tests/test_contract_interactions.py — 24 个测试（deposit/withdraw/settle/claim/split/replay）
- feat(test): 创建 tests/test_server_auth.py — 11 个测试（valid/missing/expired/wrong_signer/nonce_replay/exempt_paths）

### 修改
- refactor(billing): BillingEngine 重写为 on-chain settlement orchestrator — 移除 Redis 余额管理，新增 check_user_balance() + request_settlement() + generate_pot()
- refactor(wallet): 替换 UUID-based SessionKey 为 ECDSA 密钥对（eth_account.Account.create()）
- refactor(settlement): ChainSettlement 新增 contract 属性惰性初始化（Sentinel 地址 ↔ InMemory/Web3）
- refactor(server): 中间件 HMAC-SHA256 → EIP-712；submit_task 集成 billing.request_settlement() + PoT 生成；wallet_deposit/wallet_balance 代理到合约
- refactor(test_billing): 重写为 14 个测试（check_balance/request_settlement/insufficient/nonce/PoT）
- refactor(test_discovery): 认证断言 HMAC-SHA256 → EIP-712，添加 X-Nonce/X-Deadline 头部检查
- refactor(requirements): 添加 web3>=7.0 / eth-account>=0.12 / eth-hash[pycryptodome] / pycryptodome

### 修复
- fix(test_auth): 修复 EIP-712 paramsHash 不匹配 — 测试签名用空 params 而 body 含 search_term，导致 middleware 重建 hash 不一致返回 403
- fix(test_bootstrap): 更新认证 scheme 断言 HMAC-SHA256 → EIP-712
- fix(billing): 添加缺失 `from eth_account import Account` 解决 `_sign_settlement()` NameError；删除 `return` 后死代码

### 修改
- feat(server): 中间件支持 X-Wallet-Address 为首选头部，X-User-ID 为回退
- feat(broker): 新增 set_pot_signature()/get_pot_signature() 存储 PoT 到任务状态
- feat(server): GET /api/tasks/{id}/status 返回 pot 字段
- fix(contract_client): to_bytes(amount, 32) → amount.to_bytes(32, 'big') 兼容 eth_utils v4 API
- fix(pot): to_bytes(amount, 32) → amount.to_bytes(32, 'big') 支持 amount=0
- fix(billing): 移除 unused to_bytes import，使用 int.to_bytes()
- fix(test): 更新所有测试 EVM 地址为有效 hex 地址；contract_interactions/billing 测试使用真实 ECDSA 网关签名

### 修复
- fix(contract): claimReward PoT hash 缺少 amount 参数 — 增加 `workerAmount` 到 `keccak256(abi.encodePacked(taskId, msg.sender, workerAmount))` 保证跨平台一致性（Solidity/Python POTManager/InMemorySettlementContract）
- fix(contract): settleTask 事件未定义 — 从 `settleTask` 改为 `TaskSettled` 事件名
- fix(billing): `_sign_settlement()` 缺失 `from eth_account import Account` — 添加修复 NameError
- fix(billing): 删除 `return signed.signature.hex()` 后的不可达死代码

### 新增
- feat(web3): 创建 src/gateway/web3_utils.py — 网关 EIP-191/EIP-712 验签 + 结算证明生成/验证（_compute_settlement_message_hash / generate_settlement_proof / verify_settlement_proof）
- chore(deploy): .dockerignore 补充 node_modules/、artifacts/、cache/ 等排除规则，构建上下文 350MB → ~30MB
- feat(contract): 创建 contracts/test/MockERC20.sol — 可配置小数位数的 ERC20 测试桩
- feat(hardhat): 创建 tests/hardhat/aims_settlement_test.cjs — 18 个 Hardhat 合约测试（Deposits/Withdrawals/Settlement/Claim+PoT/OwnerFees/KeyRotation），使用 raw ECDSA 签名验证 all Solidity 逻辑
- feat(hardhat): 创建 hardhat.config.js — Hardhat v2 配置（Solidity 0.8.20、优化器 200 runs、contracts + tests 路径映射）
- feat(deps): package.json 添加 hardhat / @nomicfoundation/hardhat-toolbox / @openzeppelin/contracts 依赖
- chore(gitignore): 添加 node_modules/、artifacts/、cache/ 忽略规则
- feat(config): 创建 .env.example — 部署环境变量模板（DEPLOYER_PRIVATE_KEY / BASE_RPC_URL / PLATFORM_OWNER / AIMS_CONTRACT_ADDRESS）
- feat(scripts): 创建 scripts/deploy_settlement.js — Base 网络部署脚本（主网 canonical USDC、测试网 MockERC20、硬编码 immutable PLATFORM_OWNER、后部署校验）
- feat(network): hardhat.config.js 新增 base（chainId 8453）和 baseSepolia（chainId 84532）双网络配置，DEPLOYER_PRIVATE_KEY 环境变量注入
- feat(docs): MASTER_INDEX.md 新增 EVM/Base Compliance 协议节

### 修改
- refactor(middleware): server.py EIP-712 → EIP-191 personal_sign 简化为 3 头部（X-Wallet-Address / X-Signature / X-Timestamp），移除 nonce/deadline
- refactor(middleware): 头部提取改为大小写不敏感 `_get_header()`（扫描全部 header key 做 lower 匹配），解决 Fly.io 等反向代理变换头部大小写问题
- fix(middleware): 403 响应改为报告具体缺失字段和已接收头部列表，加速调试
- feat(middleware): 中间件入口添加 `Incoming headers` 调试日志打印完整请求头
- refactor(bootstrap): bootstrap_helper.py HMAC → ECDSA 钱包自动生成 + EIP-191 签名
- refactor(test): test_server_auth.py EIP-712 → EIP-191（remove nonce/replay tests）
- refactor(test): test_discovery.py auth scheme EIP-712 → EIP-191
- refactor(docs): MASTER_INDEX.md 所有认证章节 EIP-712 → EIP-191
- refactor(contract): _verifyWorkerBinding() 统一 ECDSA 验证（OZ v5.6.0 tryRecover 3 值解构）
- refactor(settlement): worker-binding 签名格式简化至 3 参数（taskId + worker + amount）
- refactor(server): submit_task anti-tampering — 使用 broker-locked claimed_worker 而非 self-reported worker_id
- refactor(server): 新增滑动窗口限流器（100 req/60s per X-Wallet-Address）
- refactor(server): POST /api/run budget control（max_budget < COST_PER_TASK_USDC * steps 时 400）

### 移除
- chore(auth): 移除 EIP-712 模块依赖（不再需要 typed data 验证）
- chore(bootstrap): 移除 hmac/hashlib 导入和 SIGNING_SECRET

### 新增
- feat(contract): 创建 contracts/AIMSAgentGateway.sol — 生产级 Solidity 合约（USDC 托管、PoT 链上验证、70/25/5 三方分账、超时退款、Compound Nonce 防重放、开发者注册表）
- feat(deploy): 全局域名 aims-gateway.fly.dev → api.aimsgateway.com（8 个文件）
- fix(billing): check_user_balance() 自动注入 10 USDC 初始额度（InMemory 模式，签约通过的钱包自动获得）

---
*本文档由 Claude Code 自动维护，请勿手动编辑格式*

## [2026-06-11]
### 新增
- feat(anvil): 创建 tests/anvil_e2e/AIMSAgentGateway.sol — 简化原生 ETH 合约，worker-signed PoT via ecrecover、70/25/5 分账、nonReentrant
- feat(anvil): 创建 tests/anvil_e2e/gateway.py — 独立 FastAPI 网关（EIP-191 personal_sign 认证、402 billing interceptor、httpx Worker 路由、hot wallet 签名 settleTask）
- feat(anvil): 创建 tests/anvil_e2e/mock_agent_node.py — Worker 模拟器，ECDSA 签署 keccak256(taskId) 生成 Proof-of-Task
- feat(anvil): 创建 tests/anvil_e2e/pipeline_e2e_test.py — 编排脚本，自动启动 Anvil/部署合约/启动服务/运行 3 场景（成功 70/25/5 + 402 + 403）
### 修改
- docs(master_index): 添加 escrow 遗留参考说明和 70/25/5 分账描述，修复 agent bootstrap 测试断言
- test(bootstrap): REQUIRED_TOPICS 改为两阶断言 — 硬性主题 + `ALTERNATIVE_TOPICS` ANY-match 兼容未来文档演进
### 重构
- refactor(anvil/gateway): 生产级安全加固 — `_load_gateway_key()` 严格 env var 加载（AIMS_GATEWAY_PRIVATE_KEY），NonceManager 线程安全 + 可选 Redis 后端，GasEstimator EIP-1559 动态计费 + replace-by-fee 重试
- fix(anvil/pipeline): 环境变量名对齐 — `GATEWAY_KEY` → `AIMS_GATEWAY_PRIVATE_KEY`，`_deploy_via_forge` 兼容双 key 读取
### 新增
- feat(console): 创建 static/console.html — Web3 前端控制面板，MetaMask 钱包直连，EIP-191 浏览器端签名，三角色视图（Consumer/Developer/Worker），AIMS Execution Pipeline 进度条，402 余额不足弹窗
- feat(server): 添加 CORS 中间件（开发模式全放行） — `from fastapi.middleware.cors import CORSMiddleware`
- feat(server): 添加 `GET /console` 路由 — 托管 Web3 控制面板
- feat(worker): 创建 run_aims_worker.py — 独立 OpenClaw 兼容 Worker 节点，EIP-191 认证，PoT 签名，claim→execute→submit 全循环
### 修复
- fix(server): `wallet_deposit`/`wallet_balance` 每个请求创建独立 `ChainSettlement` 实例 → `InMemorySettlementContract` 余额不共享。改为使用模块级 `_contract` 单例
### 修复
- fix(worker): `run_aims_worker.py` `execute_skill()` 生成 mock 数据不匹配 skill 的 `output_schema` → 提交时 `VALIDATE GENERIC FAIL` → `complete_task("FAILED")` → 后续 worker 全 204。新增 `_fetch_output_schema()` 从 `/api/discovery` 获取输出 schema，`_build_mock_result()` 按 schema 生成合规 mock 数据
### 新增
- feat(test_skill): 创建 `test_skill` 沙盒技能 — 完全宽松的 `output_schema`（`{"type":"object"}`，无 required），`submit_task` 短路由直接返回 `outcome=ACCEPTED`，跳过结算/托管流程。用于 DePIN 带宽烟雾测试和流水线验证

## [2026-06-10]
### 修复
- fix(contract): Worker/Developer 独立领款（per-party claim），仅双方都认领后状态才转为 CLAIMED
- fix(billing): PoT 金额修正为份额（25%/70%）而非任务总额，确保 on-chain claim 验证通过
- fix(solidity): `claimReward`/`claimDeveloperReward` 使用 `hasClaimedWorker`/`hasClaimedDeveloper` 独立映射
- fix(refund): `refundTask` 新增认领后禁止退款检查
- fix(tests): 更新所有测试适配 `party_address` 重命名、compound key 查找和 70/25/5 分账
### 修改
- refactor(contract): `_worker_claimed` + `_developer_claimed` 映射替代单一 taskStatus 认领守卫
- refactor(billing): 导入 `WORKER_BPS`/`DEVELOPER_BPS` 计算索赔 PoT 金额
- refactor(test_billing): 适配新的 BillingEngine 构造函数和 `party_address`
- refactor(test_contract_interactions): 完全重写适应 70/25/5 API
- refactor(test_pot): 适配 `party_address` 和 compound key 查找
