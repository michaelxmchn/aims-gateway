<!-- AIMS Protocol | Version 1.0.0 | Last Updated: 2026-06-10 | Hermes-Verified -->

# 项目知识库

> **格式要求**: 严格遵循 `.claude/output-styles/markdown-focused.md` 格式规范

## 代码模式

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
- **合约部署底链**：Base（EVM 兼容，L2，低 Gas），USDC 6 位小数
- **部署脚本硬编码 PLATFORM_OWNER**：`scripts/deploy_settlement.js` 中 `PLATFORM_OWNER = "0x08c9fd0a915f2b0856353850b8adea943f226bcf"`（Solidity `immutable`，烧入合约字节码，永久不可更改）
- **Base 网络配置**：`hardhat.config.js` 包含 mainnet（chainId 8453）和 baseSepolia（chainId 84532）双网络，`DEPLOYER_PRIVATE_KEY` 环境变量注入

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

### 多模态输入预处理模式
- **Base64 解码**：`_detect_base64()` 识别长度 ≥20 的 base64 编码字符串 → 解码为临时文件，通过文件头字节检测图像格式（PNG/JPEG/GIF/WebP）
- **URL 下载**：`_detect_url()` 识别 http/https/file 开头的 URL → `_download_to_temp()` 下载到临时文件，通过扩展名推断 MIME 类型
- **值替换**：原始字符串值替换为文件元数据 dict `{"_type": "file", "path": "...", "mime_type": "...", "size_bytes": N}`，技能 `execute()` 可直接读取 `path`
- **集成点**：`execute_dynamic_skill()` 入口处调用 `preprocess_multimodal(payload)`，对下游技能透明

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
- **AIMS Execution Pipeline**：Auth → Balance Check → Execution → PoT → Settlement 五阶段动画进度条，反映从签名到链上分账的完整资金流
- **CORS 配置**：`server.py` 使用 `CORSMiddleware(allow_origins=["*"])` 开放跨域；前端通过 `localStorage.setItem("aims_api_base", url)` 配置 API 地址
