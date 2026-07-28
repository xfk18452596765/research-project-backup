# Day15：Q-learning动作与策略

## 今日目标

在 Day14 已冻结的本地离散状态基础上，完成分布式表格 Q-learning 的联合动作与本地 ε-greedy 策略设计。

## 冻结设计

```text
K  ∈ {1, 2, 3}
CW ∈ {15, 31}
```

稳定动作编号：

```text
a0=(1,15)  a1=(1,31)
a2=(2,15)  a3=(2,31)
a4=(3,15)  a5=(3,31)
```

保留 Fixed-PRMAC 基线动作 `(2,15)`。

## 关键语义

- 决策主体：当前预约段起始节点；
- 决策时刻：本地 FIFO 队首获得服务资格后、初始 DIFS/退避之前；
- `K > remaining_hops` 的动作被屏蔽，不做静默截断；
- 一个动作覆盖完整预约段重试序列；
- PR_NACK 后不立即重新选动作，而是从动作中的初始 CW 执行 BEB；
- 每个节点维护独立的稀疏 Q 值表；
- ε-greedy 只在合法动作中探索或利用；
- 并列最大 Q 值采用带种子的随机打破，保证可复现。

## 文件说明

- `code/rl_prmac_action_policy.py`：最终动作空间、动作掩码、本地 Q 表与 ε-greedy 策略；
- `code/test_rl_prmac_action_policy.py`：23 项 Day15 专项测试；
- `code/main_day15_action_policy_validation.py`：最终接口验证；
- `code/run_day03_day15_regression.py`：Day03—Day15 全量回归入口；
- `docs/Day15_Q-learning动作与策略.md`：仓库继承分析和详细设计；
- `results/day15_action_policy_validation.json`：示例验证结果；
- `results/day15_action_catalog.csv`：冻结动作目录；
- `test_results.txt`：隔离测试输出。

## 今日边界

Day15 不实现奖励、TD/Q-learning 更新、完整训练、中心控制或对 Day13 Fixed 基线的修改。

## 明日衔接

Day16 在不改变本日状态—动作接口的前提下，完成奖励函数与 Q 值更新机制。
