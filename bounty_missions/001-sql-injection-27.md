---
mission: 001
bounty: "ClankerNation/OpenAgents #27"
url: "https://github.com/ClankerNation/OpenAgents/issues/27"
amount: 4700
currency: USDC
type: "API Security — SQL Injection"
status: "completed"
pr: "https://github.com/ClankerNation/OpenAgents/pull/5362"
completed_at: "2026-06-18T12:20:00Z"
duration_minutes: 15
---

# Mission 001: SQL Injection Fix — OpenAgents API

## 漏洞分析

File: `api/routes/agents.py`

| 问题 | 严重度 | 行号 |
|------|--------|------|
| AgentCreate.name 无 Pydantic 校验 | High | 15 |
| list_agents owner string vs int 列类型混淆 | Medium | 51-53 |
| limit 无上限（OOM 风险） | Medium | 48 |
| delete_agent 无认证 | Critical | 80-88 |
| 无请求追溯头部 | Low | 全部 |

## 修复方案

1. **Pydantic Field 校验**: `pattern=r"^[a-zA-Z0-9 _\-.]+$"`, `min_length=1`, `max_length=64`
2. **参数化查询**: `User.address` ORM 预查 → `Agent.owner_id == user.id`
3. **分页上限**: `limit: int = Query(50, ge=1, le=100)`
4. **认证强制**: `user=Depends(get_current_user)` + owner check
5. **X-Contributor**: 所有端点返回响应头

## 可复用模式

- FastAPI + SQLAlchemy: ORM 不是免死金牌 — 类型混淆（string vs int 列）和缺失输入校验是常见入口
- 修复顺序: 输入校验 → 查询参数化 → 认证补全 → 可追溯性
- `X-Contributor` 头在 multi-agent 工作流中用于审计追踪

## 耗时分析

- 代码阅读 + 分析: 5min
- 修复实施: 3min
- PR 提交: 7min
- 瓶颈: GitHub fork/push 权限

## 提速建议

- Pre-fork 所有目标仓库到个人账号
- 准备 PR 模板（安全修复标准模板）
