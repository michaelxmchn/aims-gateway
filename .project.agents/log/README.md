# 实施日志（execution log）

本目录沉淀"做了什么 + 哪些提交 + 下一步"，供下一个会话接手用。
规则与时机见 `../VIBECODING_GUIDE.md §5`；硬约束见 `../SELF_CONSTRAINTS.md §B6`。

---

## 文件命名

`YYYY-MM-DD-<slug>.md`

- `<slug>` = 简短动词 + 范围，kebab-case
- 同日多份按写作顺序加 `-1`、`-2` 后缀

## 模板

```markdown
# <一句话标题：完成了什么>

- **日期**：YYYY-MM-DD
- **关联**：ROADMAP M<N> / 子任务名 / 关联文档
- **会话上下文**：（可选）本会话从哪开始接手的

## 做了什么
- bullet 1
- bullet 2

## 提交
- `<short hash>` <commit subject>

（若本段未提交：明确写"未提交，工作树状态：…"并说明原因）

## 状态变更
- ARCHITECTURE：是否动过？动了哪一节？
- PRD / UIUX：是否触发回归？
- 测试：跑了什么，结果

## 下一步
- 接下来要做的第一件事（具体到任务名）
- 已知阻塞 / 待澄清项
```

## 何时写

- 完成一个 ROADMAP milestone
- 完成一个独立可验收的子任务
- 完成非平凡的重构 / bug 修复
- 会话即将结束（兜底）

## 何时不写

- 还没完成一个"可独立验收"的部分（别凑数）
- 纯文档微调（commit 自身已够说明）
- 实验性探索且最终 revert（commit 即可）
