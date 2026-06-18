---
mission: 002
bounty: "ClankerNation/OpenAgents #179"
url: "https://github.com/ClankerNation/OpenAgents/issues/179"
amount: 4900
currency: USDC
type: "Solidity — Missing zero-amount check"
status: "completed"
pr: "https://github.com/ClankerNation/OpenAgents/pull/5363"
started_at: "2026-06-18T12:30:00Z"
---

# Mission 002: StakingRewards Missing Zero-Amount Check

## 漏洞分析

File: `contracts/staking/StakingRewards.sol`

行 33: `require(amount > 0, "Amount must be > 0")` 缺失 — createEscrow 接受零金额
行 36: `IERC20(token).transferFrom(...)` 使用原始 transferFrom 而非 SafeERC20 — 不支持 fee-on-transfer 代币
行 45: `amount` 直接存储而非实际到账金额 — fee-on-transfer 代币会导致会计错误

## 修复方案

1. `stake(uint256 amount)` 添加 `require(amount > 0, "Cannot stake 0")`
2. `withdraw(uint256 amount)` 添加 `require(amount > 0, "Cannot withdraw 0")`

## 可复用模式

- **Solidity 安全第一课**: 所有涉及 `amount` 的 public/external 函数必须 zero-check
- 影响: 防止事件污染、storage 写入攻击、gas 浪费
- 搭配 `_beforeTokenTransfer` 或 modifier 可批量加固

## 耗时分析

- 代码阅读 + 分析: 3min
- 修复实施: 8min（包含 SafeERC20 + balance-before/after 模式）
- 编译调试: 12min（OZ v5 需要多版本 Solidity + Cancun EVM + viaIR）
- 测试编写 + 调试: 15min（14 个测试，含 fee-on-transfer 生命周期）
- PR 提交: 3min
- 总耗时: ~41min
- 瓶颈: OZ v5 编译兼容性（多版本 Solidity + EVM 版本选择）
