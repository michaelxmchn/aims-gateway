# 开发工作文档

> **格式要求**: 严格遵循 `.claude/output-styles/bullet-points.md` 格式规范

## 当前任务
- [ ] 编写 AIMS 智能合约（Solidity on Base）
- [ ] 实现 Skill 市场的发布/检索/获取端到端流程
- [ ] 写单元测试（Manifest 校验、Registry 加载、Log 追加）
- [ ] 集成 Anthropic SDK 做端到端 route() 测试

## 任务详情
- ADS Phase 2 架构访谈
  - 状态: 已完成
  - 文件: PRD.md / ARCHITECTURE.md
  - 描述: 完成需求收敛、领域建模、模块划分、依赖图
- Skill Manifest Standard + Registry
  - 状态: 已完成
  - 文件: src/skills/manifest.py / registry.py
  - 描述: Pydantic 模型定义 + 本地 JSON 加载 + LLM Tool Def 注入
- Gateway Router + DAG Engine
  - 状态: 已完成
  - 文件: src/gateway/router.py / engine.py
  - 描述: 万能入口 + 动态工具注入 + 串行编排
- Append-only Log + Chain Settlement
  - 状态: 已完成
  - 文件: src/ledger/log.py / merkle.py / src/chain/settlement.py / wallet.py
  - 描述: 本地追加日志 + Merkle 化 + 链上结算存根 + 会话密钥管理
- Skill Runtime
  - 状态: 已完成
  - 文件: src/runtime/executor.py
  - 描述: 本地信任模式执行 + 日志记录

## 任务详情
- 任务1
  - 状态: 进行中
  - 文件: 待定
  - 描述: 待定

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

## 遇到的问题
- 暂无

## 技术决策
- 暂无

---
*本文档由 Claude Code 自动维护，请勿手动编辑格式*
