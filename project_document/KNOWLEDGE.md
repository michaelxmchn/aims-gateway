# 项目知识库

> **格式要求**: 严格遵循 `.claude/output-styles/markdown-focused.md` 格式规范

## 代码模式

### 认证模式
- 待补充（不使用传统用户登录，用户通过 AI 客户端（Claude Code/Cursor 等）本地操作，链上身份通过智能钱包关联）

### AIMS 链上架构模式
- **链上仅做两件事**：结算（扣分/加分）+ 计数器（+1 状态证明）
- **高频运行数据**：本地 Append-only Log 挡在前面，定期 Batch 上链
- **底链**：Base（EVM 兼容，低 Gas）
- **意图驱动路由**：万能入口 Skill 将用户需求拆解为 DAG 工作流，自动编排多个原子 Skill
- **Domain Detection**：通过关键词匹配将用户 Prompt 分类到 7 个领域（security/git/code/data/devops/writing/general）
- **Top-3 注入**：`get_top_for_domain()` 按 `Priority_Score = Frequency + (Staked × 10)` 排序，只注入匹配领域的前 3 个 Skill

### Document-Driven 架构
- **子目录结构**：`skills/manifests/<skill_name>/manifest.json`（元数据）+ `rules.md`（Markdown 规则文件）
- **rules.md 即文档即代码**：纯 Markdown 格式，任何 AI（Claude/GPT/Codex）都能原生读取理解，无需自定义解析器
- **GatewayRouter 轻量上下文注入**：不再调用 LLM，过滤技能后拼接 rules.md 上下文字符串，由调用方注入
- **Sandbox 持有实现注册**：`SKILL_IMPLS` dict 映射 skill_name → Python callable，`resolve_impl()` 调度

## 常见问题

### Q: 待补充
A: 待补充

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

### 决策5：信任模式 + 串行执行
- **背景**: MVP 要快速验证核心路由逻辑
- **决策**: 沙箱隔离不做（信任模式，仅种子开发者）+ 串行执行（不做并行 DAG）
- **原因**: 沙箱和并行调度会增加数倍复杂度，MVP 场景线性的就够用了

## 学习资源
- 待补充

---
*本文档由 Claude Code 自动维护，请勿手动编辑格式*
