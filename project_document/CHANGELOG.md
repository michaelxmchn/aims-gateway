<!-- AIMS Protocol | Version 1.0.0 | Last Updated: 2026-06-10 | Hermes-Verified -->

# 变更日志

> **格式要求**: 严格遵循 `.claude/output-styles/bullet-points.md` 格式规范  
> **提交规范**: 遵循 commitlint 规范（type(scope): subject）

## [2026-06-12]
### 修改
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
