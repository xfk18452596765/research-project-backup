# Day12：Fixed-PRMAC预约失败、退避与重传设计

## 1. 设计目标

Day10已经实现冲突检测与`PR_NACK`，Day11已经实现ACTIVE预约段内的连续DATA/H_ACK转发。Day12补齐两者之间缺失的失败恢复闭环：

```text
预约冲突
→ PR_NACK反向返回
→ 发起节点确认本次尝试失败
→ 随机退避
→ 重新发起预约
```

## 2. 为什么每次重试创建新预约记录

Day12不把原来的`REJECTED`记录重新改回`PENDING`，而是为每次尝试生成新的`reservation_id`。

这样可以保留：

- 每次PR_REQ/PR_NACK的控制开销；
- 每次冲突位置和失败原因；
- 每次CW与退避槽；
- 最终成功是第几次尝试；
- 重试耗时和失败率。

状态示例：

```text
request-1 = REJECTED
request-2 = ACTIVE
```

若重试上限耗尽：

```text
request-1 = REJECTED
request-2 = REJECTED
...
request-N = FAILED
packet    = DROPPED
```

## 3. 退避规则

把首次预约看作使用`CWmin=15`的第0阶段。第`r`次重试（`r>=1`）采用：

```text
CW_r = min((CWmin + 1) × 2^r - 1, CWmax)
```

因此默认序列为：

```text
15 → 31 → 63 → 127 → 255 → 511 → 1023 → 1023
```

随机槽：

```text
B_r ~ UniformInteger[0, CW_r]
```

重试等待时间：

```text
T_retry = DIFS + B_r × slot_time
```

默认参数：

```text
DIFS      = 50 μs
slot_time = 20 μs
seed      = 7
```

固定种子7时，第一次重试：

```text
CW = 31
B  = 20 slots
T  = 50 μs + 20 × 20 μs
   = 450 μs
```

## 4. 重试序列状态

父级重试序列：

```text
SCHEDULED
→ ATTEMPTING
→ BACKING_OFF
→ ATTEMPTING
→ SUCCEEDED
```

持续失败时：

```text
SCHEDULED
→ ATTEMPTING
→ BACKING_OFF
→ ...
→ FAILED
```

单次预约尝试仍使用：

```text
PENDING → ACTIVE
PENDING → REJECTED
REJECTED → FAILED（仅最后一次、重试上限耗尽）
```

## 5. 关键事件

新增可观测事件：

```text
RETRY_SEQUENCE_START
RETRY_ATTEMPT_SCHEDULED
RETRY_ATTEMPT_START
RETRY_BACKOFF_START
RESERVATION_RETRY_START
RETRY_SEQUENCE_SUCCEEDED
RETRY_SEQUENCE_FAILED
```

已有事件继续保留：

```text
PR_REQ_TX / PR_REQ_RX
PR_ACK_TX / PR_ACK_RX
PR_NACK_TX / PR_NACK_RX
RESERVATION_ACTIVE
RESERVATION_REJECTED
DATA_TX / DATA_RX
H_ACK_TX / H_ACK_RX
```

## 6. 指标

新增：

- 重试序列数；
- 总预约尝试数；
- 实际重试次数；
- 首次成功数；
- 重试后成功数；
- 重试耗尽失败数；
- 累计退避槽；
- 累计/平均退避时间；
- 平均每序列重试次数；
- 重试序列成功率；
- 重试序列完成时延。

控制帧、DATA、H_ACK及字节开销继续沿用Day09—Day11统计。

## 7. 主程序场景

已有预约：

```text
2 → 3 → 4
```

候选预约：

```text
0 → 1 → 2
```

初始候选在节点2发生冲突：

```text
request-1 → REJECTED
```

已有预约随后RELEASE，第一次重试使用：

```text
CW = 31
backoff_slots = 20
backoff_delay = 0.000450 s
```

第二次预约成功：

```text
request-2 → ACTIVE
```

随后继承Day11完成：

```text
DATA 0→1 → H_ACK 1→0
DATA 1→2 → H_ACK 2→1
```

## 8. 当前边界

Day12只实现PR_NACK后的事件级退避与重试。初始预约接入仍继承Day09“发起节点已经获得PR_REQ发送机会”的抽象；退避期间也尚未与共享信道忙检测、冻结和恢复耦合。

因此Day12结果用于验证失败恢复机制正确性，不能直接作为DCF与Fixed-PRMAC公平性能结论。Day13必须完成完整Fixed-PRMAC集成和公平止损预实验后，才能决定是否进入RL。
