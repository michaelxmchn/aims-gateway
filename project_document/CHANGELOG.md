# 变更日志

> **格式要求**: 严格遵循 `.claude/output-styles/bullet-points.md` 格式规范  
> **提交规范**: 遵循 commitlint 规范（type(scope): subject）

## [2026-06-09]
### 新增
- feat(gateway): broker.py 新增 succeeded_count / claimed_count 状态查询属性
- feat(gateway): server.py health 端点新增 tasks_succeeded 字段
### 修复
- fix(server): health 端点缺失 tasks_succeeded 导致 Pydantic ValidationError (500)
### 测试
- feat(test): 创建 tests/load_test_simulation.py — 20 Worker 多进程压力测试（HMAC-SHA256 签名，100 任务全通过 ✓）
- test(load): 负载测试 100/100 任务完成，111.7 tasks/s 吞吐量 ✓
### 新增
- feat(deploy): 创建 Dockerfile — python:3.11-slim，uvicorn 生产部署
- feat(deploy): 创建 fly.toml — Fly.io 部署配置（sin 区域，256MB，min_machines_running=1）
- feat(deploy): 创建 .dockerignore — 排除 .git/tests/__pycache__/.env 等
- feat(deploy): 创建 requirements.txt — fastapi/uvicorn/pydantic 锁定版本

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

---
*本文档由 Claude Code 自动维护，请勿手动编辑格式*
