<!-- AIMS Protocol | Version 1.0.0 | Last Updated: 2026-06-10 | Hermes-Verified -->

# 变更日志

> **格式要求**: 严格遵循 `.claude/output-styles/bullet-points.md` 格式规范  
> **提交规范**: 遵循 commitlint 规范（type(scope): subject）

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

---
*本文档由 Claude Code 自动维护，请勿手动编辑格式*
