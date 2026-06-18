---
mission: 003
bounty: "ClankerNation/OpenAgents #66"
url: "https://github.com/ClankerNation/OpenAgents/issues/66"
amount: 4700
currency: USDC
type: "Solidity — Phantom reward accrual"
status: "completed"
pr: "https://github.com/ClankerNation/OpenAgents/pull/5364"
started_at: "2026-06-18T13:15:00Z"
completed_at: "2026-06-18T13:30:00Z"
duration_minutes: 15
---

# Mission 003: StakingRewards Phantom Rewards + Access Control + Precision Loss

## 漏洞分析

File: `contracts/staking/StakingRewards.sol`

| 问题 | 位置 | 严重度 |
|------|------|--------|
| `rewardPerToken()` 使用 `block.timestamp` 而非 `lastTimeRewardApplicable()` | L73 | High — 期后虚增奖励 |
| `notifyRewardAmount` 无权限控制 | L117 | Critical — 任何人可重置奖励率 |
| `rewardRate` 整数除零精度损失 | L122 | Medium — 小额奖励永久丢失 |

## 修复方案

1. **L73**: `block.timestamp` → `lastTimeRewardApplicable()` — 期后奖励冻结
2. **L117**: `external` → `external onlyOwner` — 仅合约拥有者可通知奖励
3. **L122**: `require(reward / rewardsDuration > 0)` — 确保奖励率非零

## 可复用模式

- **Synthetix StakingRewards 标准模式**: `rewardPerToken` 必须使用 `lastTimeRewardApplicable()` 而非 `block.timestamp`，这是 phantom reward 的标准修复
- **notifyRewardAmount 必须 onlyOwner**: 缺少权限控制 = 任何人可盗取奖励池
- **rewardRate 前除零检查**: `reward / rewardsDuration > 0` 门控是 Synthetix 官方模式

## 耗时分析

- 代码阅读 + 分析: 3min
- 修复实施: 3min
- 测试编写: 7min
- 调试: 2min（MockERC20 参数 + reward prefund）
- 总耗时: ~15min
