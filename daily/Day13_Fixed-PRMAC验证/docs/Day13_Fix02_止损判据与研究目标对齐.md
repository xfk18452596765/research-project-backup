# Day13-Fix02：止损判据与研究目标对齐

## 1. 触发原因

Day13-Fix01加入本地FIFO后，第二次止损矩阵得到：

```text
fairness_passed                                  = True
fixed_functionality_passed                       = True
dcf_delay_increases_with_hops                    = True
critical_delay_wins_out_of_4                     = 3
critical_seed_consistent_cells_out_of_4          = 3
critical_delivery_losses_out_of_4                = 0
all_delivery_losses_out_of_9                     = 0
fixed_queue_overflow_drops                       = 0
fixed_delay_wins_majority_of_9_cells             = False
```

Fixed-PRMAC在以下核心场景明显优于DCF：

```text
4跳-high
6跳-medium
6跳-high
```

但在2跳、低负载以及4跳-medium等弱竞争场景中，固定路径预约的PR_REQ、PR_ACK和RELEASE开销高于节省的逐跳竞争开销，因此未在9个单元中取得多数胜利。

## 2. 为什么不继续修改协议

当前功能、公平性、投递率、本地队列和资源释放均已通过。继续修改K、CW、PHY参数、负载或种子，只为增加9单元胜场，会形成针对当前矩阵的参数调优，并提前侵入后续RL任务。

本课题原始假设不是“Fixed-PRMAC在所有负载和所有跳数均优于DCF”，而是：

> 路径预约能够在较长路径和较强竞争下减少逐跳重复竞争造成的端到端时延累计。

因此，下一步应修正止损判据与原研究目标之间的不一致，而不是修改协议或实验数据。

## 3. Fix02只修改判定器

Fix02不修改：

- `K_fixed=2`；
- `CWmin=15`、`CWmax=1023`；
- 重试上限；
- 本地FIFO；
- PHY和控制帧参数；
- 跳数、负载、数据包数和种子；
- DCF或Fixed-PRMAC的任何测量值。

只修改`evaluate_stop_loss()`的PASS门槛。

## 4. 新的必要判据

PASS必须同时满足：

1. 参数公平性通过；
2. Fixed-PRMAC所有会话到达终态且无残留ACTIVE预约；
3. DCF在三种负载下均呈现2跳 < 4跳 < 6跳的时延累积；
4. 三个核心目标单元全部获胜：`4跳-high`、`6跳-medium`、`6跳-high`；
5. `4/6跳 × medium/high`四个关键单元至少赢3个；
6. 四个关键单元至少3个在三个种子中有不少于2个种子方向一致；
7. 四个关键单元无投递率下降；
8. 全部9个单元均无投递率下降；
9. Fixed-PRMAC无FIFO溢出丢包。

## 5. 9单元多数胜利的处理

`fixed_delay_wins_majority_of_9_cells`继续保留在JSON和终端输出中，但改为**描述性观察项**，不再作为PASS门槛。

这不是删除不利结果：2跳和低负载的性能代价必须继续写入实验结果和论文，作为固定路径预约的适用边界。

## 6. 复验要求

修正后必须重新运行：

```text
Day13专项测试
→ Day03—Day13完整回归
→ 完整2/4/6跳 × 三负载 × 三种子止损矩阵
```

只有新的`day13_stop_loss_decision.json`明确为`PASS`，才允许关闭Day13并进入Day14。
