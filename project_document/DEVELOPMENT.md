# 开发工作文档

> **格式要求**: 严格遵循 `.claude/output-styles/bullet-points.md` 格式规范

## 当前任务
- [ ] 编写 AIMS 智能合约（Solidity on Base）
- [ ] 实现 Skill 市场的发布/检索/获取端到端流程
- [ ] 集成 Anthropic SDK 做端到端 route() 测试

## 已完成任务清单

### Layer 0-1: 账本 & 经济模型
- **ADS Phase 2 架构访谈**
  - 状态: 已完成
  - 描述: 完成需求收敛、领域建模、模块划分、依赖图
- **MockLedger USDT 账本**
  - 状态: 已完成
  - 文件: src/ledger/mock_counter.py
  - 描述: USDT JIT Escrow、Dynamic Billing（Gas 计费）、Compute Tier Billing（1x/2.5x/6x）、3-Strike Slashing、Double-Sided Reputation
- **Append-only Log + Merkle**
  - 状态: 已完成
  - 文件: src/ledger/log.py / merkle.py
  - 描述: JSONL 追加日志、Merkle 树批量上链证明

### Layer 2: 技能系统
- **SkillManifest Standard**
  - 状态: 已完成
  - 文件: src/skills/manifest.py
  - 描述: Pydantic 模型，对齐 LLM Tool Calling 格式
- **SkillRegistry + Document-Driven**
  - 状态: 已完成
  - 文件: src/skills/registry.py
  - 描述: 子目录加载、rules.md 缓存、优先级评分、领域检测、冷却监狱
- **6 个种子 Skill**
  - 状态: 已完成
  - 文件: skills/manifests/*/
  - 描述: amazon_scraper、code_security_audit、git_changelog、data_analyzer、buggy_skill、dashboard_skill

### Layer 3: 网关 & 路由
- **GatewayRouter**
  - 状态: 已完成
  - 文件: src/gateway/router.py
  - 描述: 万能入口、轻量上下文注入
- **TaskBroker**
  - 状态: 已完成
  - 文件: src/gateway/broker.py
  - 描述: 线程安全 FIFO、Stateful Claiming、Fault-Tolerance 超时回收、JSON Schema 通用验证器

### Layer 3.5: HTTP 网关
- **FastAPI Gateway Server**
  - 状态: 已完成 (2026-06-09)
  - 文件: src/gateway/server.py
  - 描述: POST /api/tasks/claim、POST /api/tasks/submit、POST /api/workers/heartbeat、GET /api/health、HMAC-SHA256 签名认证中间件、replay 保护（300s 窗口）
- **TaskBroker 状态查询**
  - 状态: 已完成 (2026-06-09)
  - 文件: src/gateway/broker.py
  - 描述: 新增 succeeded_count / claimed_count 属性、get_task_meta / get_task_status 公开方法
- **Redis 持久化存储层**
  - 状态: 已完成 (2026-06-09)
  - 文件: src/gateway/storage.py
  - 描述: Redis-backed KV 存储，自动降级为内存字典，JSON 序列化
- **生产 DePIN Worker**
  - 状态: 已完成 (2026-06-09)
  - 文件: src/worker/
  - 描述: 配置管理（config.py）、HMAC-SHA256 签名工具（signer.py）、无限循环 Worker（worker.py：claim → execute → submit + heartbeat）
- **Worker 心跳机制**
  - 状态: 已完成 (2026-06-09)
  - 文件: src/gateway/server.py
  - 描述: POST /api/workers/heartbeat 端点 + workers_active 健康指标（60s 超时淘汰）

### Layer 4: 执行沙箱
- **WorkflowEngine**
  - 状态: 已完成
  - 文件: src/runtime/sandbox.py
  - 描述: try-except 执行、output_schema 校验、ExecutionReceipt、DePIN Worker Loop

### Layer 5: 链上结算
- **ChainSettlement**
  - 状态: 已完成
  - 文件: src/chain/settlement.py
  - 描述: UserIdentity Map、Stripe Webhook 桩（法币入金）、SessionKeyManager 存根

### Layer 6: 客户端 & MCP
- **MCP stdio Server**
  - 状态: 已完成
  - 文件: src/client/mcp_server.py
  - 描述: JSON-RPC over stdio，tools/list + tools/call，6 个 skill 自动发现
- **CLI**
  - 状态: 已完成
  - 文件: src/client/cli.py
  - 描述: aims exec/list/login/mcp/dashboard 子命令

### Layer 7: Worker 网络
- **生产 DePIN Worker**
  - 状态: 已完成 (2026-06-09)
  - 文件: src/worker/
  - 描述: 配置管理、HMAC-SHA256 签名、无限 claim→execute→submit 循环 + 心跳
- **Worker 心跳监控**
  - 状态: 已完成 (2026-06-09)
  - 文件: src/gateway/server.py
  - 描述: POST /api/workers/heartbeat 记录 last_seen，GET /api/health 返回 workers_active

### 测试
- **单元测试**
  - 状态: 已完成
  - 文件: tests/test_manifest/registry/log/sandbox.py
  - 结果: 47/47 PASSED ✓
- **压力测试**
  - 状态: 已完成
  - 文件: tests/stress_test.py
  - 结果: Slashing/Reputation/Tier-2/Generic Validation 全验证 ✓
- **E2E 集成测试**
  - 状态: 已完成 (2026-06-08)
  - 文件: tests/e2e_integration_test.py
  - 结果: 11/11 全通过 ✓，$180.00→$180.00 资金守恒 ✓，100% 架构闭合 ✓
- **负载压力测试**
  - 状态: 已完成 (2026-06-09)
  - 文件: tests/load_test_simulation.py
  - 结果: 20 Workers × 100 任务，111.7 tasks/s 吞吐量，100% 通过 ✓（HMAC-SHA256 签名）
- **生产级 E2E 全流程测试**
  - 状态: 已完成 (2026-06-09)
  - 文件: tests/e2e_full_flow.py
  - 结果: 10 并发 Worker 线程，ThreadPoolExecutor，SOCKS5 代理轮换，2s 浏览器指纹模拟，60s 吞吐量基准

### 部署
- **Fly.io 部署配置**
  - 状态: 待部署
  - 文件: Dockerfile / fly.toml / .dockerignore / requirements.txt
  - 描述: python:3.11-slim 容器，sin 区域，256MB，min_machines_running=1

## 部署指南

参见下方 Fly.io 部署命令。

## 最近完成
- 初始化 Git 仓库（main 分支，Git Flow 策略）
- 运行 ADS scaffold 脚本，生成 .project.agents/ 治理框架（17 个文件）
- 确定技术方向：Base L2 + 智能合约（仅结算/计数）+ 本地 Append-only Log
- 完成 ADS Phase 2 全流程：PRD 需求收敛、领域模型、7 个模块划分、依赖图 DAG
- 创建源目录结构和 12 个核心模块文件
- 定义 SkillManifest Pydantic 模型（对齐 LLM Tool Calling 格式）
- 实现 SkillRegistry（本地 manifests/ 自动加载 + Anthropic/OpenAI 双格式注入）
- 实现 GatewayRouter（万能入口 + 动态工具注入 + 串行编排）
- 实现 Append-only Log（JSONL 格式 + Merkle 树）
- 实现 Chain Settlement 存根 + Session Key Manager
- 创建 2 个种子 Skill manifest 示例
- 扩展 SkillManifest 模型，新增 staked_points（冷启动推广）+ frozen_until（冷却监狱）字段
- 实现 SkillRegistry 优先级评分（Priority = Frequency + Staked × 10），支持冷启动推广
- 实现 intent domain detection（关键词匹配 7 个领域）+ get_top_for_domain 过滤注入
- 实现 WorkflowEngine 执行验证（try-except + output_schema 校验）+ ExecutionReceipt
- 实现 MockLedger 两步托管结算（freeze_points → settle_transaction）含 SUCCESS 转账 / FAILED 退款+罚没
- 实现 Cool-down Jail 机制：3 次连续失败或 staked_points ≤ 0 → 24h 冻结，load_all() 自动过滤
- 创建 data_analyzer（数据分析和报告）+ buggy_skill（故意失败用于测试监狱）两个种子 manifest
- 实现 main.py 全生命周期演示（优先级评分、意图检测、托管结算、冷却监狱）
- **重构为 Document-Driven 架构**：skills/manifests/ 改为子目录结构，每个技能独立 manifest.json + rules.md
- 重写 gateway/router.py：去除 LLM 调用逻辑，改为轻量级上下文注入器，返回 rules.md 作为 LLM 上下文字符串
- 重写 skills/registry.py：支持子目录遍历加载 + rules.md 缓存 + get_rules()/get_top_rules() 接口
- 重写 runtime/sandbox.py：持有 SKILL_IMPLS 实现注册表 + resolve_impl() 调度执行
- 创建 amazon_scraper 种子技能：Document-Driven 第一个种子，含完整 rules.md（输入/输出/限速/合规/示例）
- 为 code_security_audit、git_changelog、data_analyzer、buggy_skill 补充 rules.md
- 重写 main.py：展示 Document-Driven 工作流（技能发现 → 上下文注入 → 沙箱执行）
- **升级 MockLedger 为 USDT JIT Escrow**：改 Points 为 USDT 稳定币语义，实现 JIT 托管（freeze_usdt 冻结 → escrow_vault 托管 → settle_escrow 结算）
  - SUCCESS 结算：1% Platform Tax → founder_treasury，99% → developer
  - FAILED 结算：100% instant refund to user
- **main.py 新增 USDT 结算演示**：展示全现金流向审计（Seeded $100.00 → $100.00 circulating ✓），支持 $X.XX 美元日志
- **实现 Dynamic Billing（Gas 计费）系统**：
  - 定义 `BASE_GAS_RATE = 0.01` USDT/s + `PLATFORM_TAX_RATE = 0.01`
  - `MockLedger.create_escrow_hold()`：预授权冻结最大预算到 escrow vault
  - `MockLedger.release_escrow_dynamic()`：按实际执行时间动态结算（gas_cost = exec_time × BASE_GAS_RATE + developer_premium，上限 max_budget）
  - `ExecutionReceipt.execution_time`：沙箱记录 wall-clock 执行时间用于计费
  - amazon_scraper 模拟随机网络延迟 `random.uniform(0.5, 2.5)` 使 Gas 计费真实
  - main.py 第 7 阶段展示详细分项账单（Gas 费/开发者溢价/平台税/Dev payout/未使用退款）
- **MockLedger 添加 threading.Lock() 线程安全保护**：所有 balance 修改通过 `with self._lock` 互斥，`total_system_wealth` 提供一致快照
- **创建 tests/stress_test.py 高并发压力测试**：10 并发用户 × 5 次 = 50 笔并发交易，验证资金守恒
  - 结果：50/50 成功结算，$0.000000 差异，WEALTH AUDIT: PASSED ✓
- **实现 DePIN 分布式 Worker 网络**：
  - 创建 `gateway/broker.py`：`TaskBroker` 中央线程安全 FIFO 队列（publish_task / poll_task / record_result）
  - `sandbox.py` 新增 `start_worker_loop()` 后台守护线程：自动轮询 Broker → 执行技能 → 调用 `release_escrow_dynamic()` 将 Gas 费记入自身 `worker_id`
  - 更新 `tests/stress_test.py` 为 DePIN 模型：5 个 Worker × 30 任务，自动排空，工作量分布 5–7 任务/worker，Gas 费分配到 5 个独立 worker_id 余额
  - 验证：WEALTH AUDIT: PASSED ✓（$70.00 Alice + $29.70 Workers + $0.30 Treasury = $100.00 ✓）
- **实现 Stateful Task Claiming + Fault-Tolerance**：
  - 重构 `gateway/broker.py`：`queue.Queue` → `Dict[str, dict]` 任务状态存储，实现 `claim_task()`（原子抢占 CLAIMED）、`complete_task()`（SUCCESS/FAILED）、`check_timeouts()`（>5s 回收 PENDING）
  - `sandbox.py`：`start_worker_loop()` 改用 `claim_task()`，新增 `crash_simulate_after` 参数（Worker-3 10s 模拟崩溃）
  - 重写 `tests/stress_test.py`：3 Workers（W1/W2 正常，W3 10s 模拟崩溃） + 后台 Timeout Checker 每 1s 轮询
  - 验证：12/12 任务完成，$0.000000 差异，Worker-3 任务回收成功 ✓
- **实现 Proof of Result 验证 + Slashing Protocol 削减协议**：
  - `ledger/mock_counter.py`：新增 `register_worker()`（质押 $5 抵押金）+ `apply_penalty()`（3 strikes → 削减 $1 → Treasury）
  - `gateway/broker.py`：新增 `validate_task_result()`（Proof-of-Result：校验 asin+price）+ `check_timeouts()` 自动调用 `apply_penalty()`
  - `runtime/sandbox.py`：Worker 循环集成 `validate_task_result()`，支持 `corrupt_output` 模拟坏数据
  - `tests/stress_test.py`：Worker-3 注册 $5 质押 → 3 次超时 → 削减 $1 → 抵押金 $5→$4，国库 +$1.40（$1 罚金+$0.40 平台税）
  - 验证：40/40 任务完成，$105.00==$105.00 守恒 ✓，Slashing Protocol PASSED ✓
- **实现 Double-Sided Reputation & Outlier Truncation 评分保护系统**：
  - `ledger/mock_counter.py`：新增 `_user_reputation`（默认 1.0，[0,1] 范围）、`_skill_weighted_score`（加权评分）、`submit_rating()`（评分门控 + 异常截断 + 信誉惩罚）
  - `gateway/broker.py`：`BrokerTask`/`publish_task()/claim_task()` 新增 `skill_id` 字段传递
  - `ledger/mock_counter.py/release_escrow_dynamic()`：新增 `skill_id` 参数，成功使用时自动记录用户技能使用记录
  - 验证：6/6 任务完成，恶意用户 1.0 评价被抑制（|1.0-5.0|>2.5），信誉 1.0→0.9，加权评分保持 5.0，资金守恒 ✓
- **实现 Compute Tier Billing（层级计费）系统**：
  - `mock_counter.py`：新增 `TIER_MULTIPLIERS = {1: 1.0, 2: 2.5, 3: 6.0}`，`release_escrow_dynamic()` 改为接收 `skill_meta` 字典（含 compute_tier/developer_premium/skill_id），gas 公式改为 `exec_time × BASE_GAS_RATE × tier_mult`
  - `broker.py`/`sandbox.py`：`compute_tier` 贯穿 `BrokerTask → publish_task → claim_task → skill_meta`
  - 验证：Tier-2(2.5x) Worker 运行 4.0s，gas=$0.1000 精确匹配预期，TAX 资金守恒 ✓
- **实现通用 JSON Schema 验证器**：
  - `broker.py`：新增 `validate_result_generic(result_data, schema, worker_id)` — 支持 type/required/properties/items/minimum/maximum 检查，失败自动调用 `apply_penalty()`
  - `sandbox.py`：Worker 循环改用通用验证器替代硬编码 asin+price 校验
  - 验证：corrupt 输出 `{"price":-10}`（缺少 products）被 JSON Schema 拒绝，Worker 被记 strike+1 ✓
- **实现 Ephemeral Dashboard Skill（即席仪表盘）**：
  - `src/skills/dashboard_skill.py`：数据聚合（任务状态/财富分布/层级统计/质押/削减日志）+ 自包含 HTML（Tailwind CSS + Chart.js 暗色主题）+ `webbrowser` 弹出
  - `src/client/cli.py`：新增 `aims dashboard` 命令入口
  - `src/runtime/sandbox.py`：`dashboard_skill` 注册到 SKILL_IMPLS
  - `src/skills/manifests/dashboard_skill/`：manifest.json + rules.md Document-Driven 定义
  - 验证：HTML 生成 13KB ✓，Tailwind/Chart.js/Slashing 表/财富饼图/层级柱图均正确渲染 ✓
- **修复 main.py release_escrow_dynamic() 签名不匹配**：
  - `src/main.py`：将 `developer_premium=` 关键字参数改为 `skill_meta=` 字典参数
  - 原因：函数签名重构为接收 `skill_meta` 字典（含 compute_tier/developer_premium/skill_id）
  - 验证：python3 -m src.main 全流程通过（6 skills + billing + jail demo ✓）
- **删除死代码 executor.py**：
  - `src/runtime/executor.py`：已删除（遗留 SkillRuntime + 空 SKILL_IMPLS，未被任何文件导入）
- **实现 MCP stdio 服务器**：
  - `src/client/mcp_server.py`：MCP 协议实现（initialize/tools/list/tools/call），暴露所有活跃 skill 为 MCP Tool
  - 验证：6 个 skill 全部正确列出 ✓
- **扩展 CLI 命令行**：
  - `src/client/cli.py`：新增 `aims exec <name> <json-args>`（执行 skill）、`aims list`（列出 skill）、`aims login`（创建会话密钥）、`aims mcp`（启动 MCP 服务器）
- **实现 User Identity Map + Stripe Webhook 桩**：
  - `src/chain/settlement.py`：新增 `UserIdentity` 和 `user_identity_map`（email → wallet 绑定）、`register_identity()`、`resolve_wallet()`、`simulate_stripe_webhook()`（模拟法币入金流程）
- **创建单元测试套件**：
  - `tests/test_manifest.py`：8 个测试（Pydantic 校验、name pattern、schema 验证、tool def 转换）
  - `tests/test_registry.py`：16 个测试（领域检测、优先级评分、冻结机制、rules.md 加载）
  - `tests/test_log.py`：12 个测试（Append/Flush/Query/Merkle 根）
  - `tests/test_sandbox.py`：11 个测试（WorkflowEngine 执行、输出验证、错误处理）
  - 验证：47/47 PASSED ✓
- **创建 E2E 集成测试套件**：
  - `tests/e2e_integration_test.py`：8 阶段端到端测试（Account Abstraction → Developer Registration → Worker Staking → Fault Tolerance → Slashing → Tier-2 Billing → Wealth Audit → Dashboard）
  - 验证：11/11 全通过 ✓，$180.00→$180.00 资金守恒 ✓，100% 架构闭合 ✓
- **创建 Gateway Server**：
  - `src/gateway/server.py`：FastAPI 生产级服务器（POST /api/tasks/claim / POST /api/tasks/submit / GET /api/health）
  - `src/gateway/broker.py`：新增 get_task_meta / get_task_status 公开方法
  - 验证：FastAPI 启动成功，3 条路由注册 ✓
- **实现 HMAC-SHA256 签名认证中间件**：
  - `src/gateway/server.py`：verify_signature_middleware 对所有 /api/tasks/* POST 请求验证 HMAC-SHA256 签名 + replay 保护（300s 窗口）
  - 验证：签名缺失/过期/无效均返回 403 ✓
- **创建多进程负载测试**：
  - `tests/load_test_simulation.py`：20 Worker 多进程并发，HMAC-SHA256 签名请求，自愈重试（3 次 backoff）
  - 验证：100/100 任务完成，111.7 tasks/s 吞吐量 ✓
- **修复 health 端点缺失 tasks_succeeded 字段**：
  - `src/gateway/server.py`：HealthResponse 新增 tasks_succeeded 字段，broker 新增 succeeded_count / claimed_count 属性
  - 原因：Pydantic 验证导致 GET /api/health 返回 500
- **Fly.io 生产部署配置**：
  - `Dockerfile`：python:3.11-slim + uvicorn 生产启动（port 8000）
  - `fly.toml`：sin 区域，256MB，min_machines_running=1 保持在线
  - `.dockerignore`：排除 .git/tests/__pycache__/.env 等
  - `requirements.txt`：fastapi/uvicorn/pydantic + redis/hiredis 版本锁定
- **创建 Redis 持久化存储层**：
  - `src/gateway/storage.py`：Storage 类 — 键值对存储，Redis 可用时持久化，不可用时自动降级为线程安全内存字典
  - 支持 get/set/delete/exists/keys/flushdb，值自动 JSON 序列化
  - 读取 `REDIS_URL` 环境变量，与 Fly.io Redis 插件无缝集成
- **.gitignore 安全加固**：新增 .project.agents/ 和 logs/ 排除规则
- **requirements.txt 补充**：锁定额外的 starlette + pydantic_core 递依赖，+ redis/hiredis
- **fly.toml 健康检查配置**：
  - 新增 `[http_service.health_check]`：指向 `GET /api/health`，15s 间隔 / 5s 超时 / 10s 宽限期
- **创建生产级 E2E 全流程测试 tests/e2e_full_flow.py**：
  - 10 并发 Worker 线程（ThreadPoolExecutor），独立 worker_id
  - 可选 SOCKS5 代理轮换 + egress IP 检测
  - 2s 浏览器指纹模拟 + HMAC-SHA256 签名全流程
  - 双模式：本地自动起服务 / 连接生产网关
  - 60s 运行 + 吞吐量 / 错误日志 / 成功率汇总
