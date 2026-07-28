# Day16：奖励函数与更新机制

## 今日目标

在不修改 Day14 状态接口和 Day15 动作/策略接口的前提下，完成一个预约段一次奖励、局部转移结构、终止状态处理和节点独立表格 Q-learning 更新。

## 已完成的代码设计

- 冻结局部多目标奖励公式；
- 保留高优先级业务的更强时延惩罚；
- 实现 `SegmentRewardInput` 与可审计 `RewardBreakdown`；
- 实现 `(s,a,r)` 结算与同节点下一决策状态 `s'` 的两阶段组装；
- 实现终止转移和 bootstrap=0；
- 实现仅在合法下一动作集合中计算 `max Q(s',a')`；
- 实现 `α`、`γ`、节点归属、动作合法性和数值边界检查；
- 新增 29 项 Day16 专项测试；
- 新增 Day16 主验证和 Day03—Day16 回归入口；
- 子进程强制 UTF-8，兼容 Windows 中文目录与日志。

## 本机验证状态

待在以下本地仓库中运行：

```text
C:\research-project-backup
```

只有专项测试、主验证和 Day03—Day16 全量回归均通过后，Day16 才算完成闭环。

## 文件说明

- `code/rl_prmac_reward_update.py`：奖励、转移和 Q 更新核心实现；
- `code/test_rl_prmac_reward_update.py`：Day16 专项测试；
- `code/main_day16_reward_update_validation.py`：确定性主验证 JSON；
- `code/run_day03_day16_regression.py`：Day03—Day16 全量回归入口；
- `code/run_day16_checks.py`：UTF-8 安全的一键专项测试、主验证和全量回归闭环；
- `docs/Day16_奖励函数与更新机制.md`：设计论证与冻结公式；
- `logs/`：本机运行后生成专项测试、主验证和全量回归日志；
- `results/`：本机运行后生成主验证 JSON。

## 今日边界

Day16 不接入 Day13 完整协议控制器，不运行完整流量训练，不做超参数搜索，不实现中心控制，不使用未来端到端时延，也不修改 Day14/Day15 冻结接口。

## 明日衔接

完成本机 Day03—Day16 全量回归并确认只有 Day16 目录发生预期变化后，才允许交给 Codex 提交。未完成闭环前不得进入 Day17。
