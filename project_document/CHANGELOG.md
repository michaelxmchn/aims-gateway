# 变更日志

> **格式要求**: 严格遵循 `.claude/output-styles/bullet-points.md` 格式规范  
> **提交规范**: 遵循 commitlint 规范（type(scope): subject）

## [2026-06-08]
### 新增
- chore(init): Git 仓库初始化（main 分支）
- feat(scaffold): 运行 ADS scaffold 脚本生成 .project.agents/ 治理框架
- feat(config): 创建 AIMS 项目脚手架配置
- docs(prd): 填充 PRD 文档（愿景/用户/范围/功能定义/Q&A 确认）
- docs(arch): 填充 ARCHITECTURE 文档（领域模型/7 模块/DAG 依赖图/目录结构）
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

### 修改
- 暂无

### 修复
- 暂无

### 重构
- 暂无

---
*本文档由 Claude Code 自动维护，请勿手动编辑格式*
