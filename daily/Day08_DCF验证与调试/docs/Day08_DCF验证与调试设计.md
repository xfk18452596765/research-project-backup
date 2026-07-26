# Day08：DCF验证与调试设计

## 1. 已发现问题一：GENERIC事件名称

### 原因

Day03的`Simulator.schedule_at()`通过`**options`接收`event_type`和`priority`。

Day04的兼容封装通过函数签名检查显式参数，没有识别`**options`中的事件元数据，导致以下事件在底层日志中显示为`GENERIC`：

- PACKET_ARRIVAL；
- FORWARD_ARRIVAL；
- TX_SLOT_RESOLVE；
- 外部信道忙起止事件。

### Day08处理

不修改Day03—Day07稳定代码，而是在`DCFValidatedMultiHopMac`中重写`_schedule_at()`，直接传入：

```python
simulator.schedule_at(
    time,
    callback,
    event_type=event_type,
    priority=priority,
)
```

## 2. 已发现问题二：排队时延边界

### Day07定义

```text
queue_delay = first_DIFS_START - queue_enter_at
```

当数据包成为队首后恰好遇到信道忙时，这个定义会把信道等待误计入排队时延。

### Day08修正

记录数据包第一次成为队首的时刻`head_of_line_at`：

```text
queue_delay = head_of_line_at - queue_enter_at
access_delay = successful_TX_START - head_of_line_at
tx_ack_delay = ACK - successful_TX_START
hop_delay = ACK - queue_enter_at
```

因此每一跳满足：

```text
hop_delay
= queue_delay
+ access_delay
+ tx_ack_delay
```

其中`access_delay`包括：

- 信道忙等待；
- DIFS；
- 随机退避；
- 退避冻结；
- 碰撞；
- ACK超时；
- 重传重新竞争。

## 3. 随机性验证

### 同种子复现

相同：

- 拓扑；
- 业务到达；
-节点参数；
- 随机种子；

应产生完全相同的数据包时延和碰撞重传统计。

### 异种子差异

不同随机种子应改变随机退避序列，使至少部分时延结果不同。

## 4. 周期多包链式场景

```text
0 → 1 → … → H
```

源节点周期生成多个数据包。每个中继仍按传统DCF：

```text
重新入队
→ 重新DIFS
→ 重新退避
→ 重新竞争
→ DATA/ACK
```

验证矩阵：

```text
跳数：2、4、6
负载：low、medium、high
种子：7、17、27
```

## 5. 共享中继汇聚场景

```text
0 ─┐
   ├→ 2 → 3
1 ─┘
```

两个源节点首次都选择0槽，产生一次确定性碰撞；随后执行ACK超时、BEB、重传、退避冻结和共享中继转发。

该场景只作为功能烟雾测试，不替代后续完整汇聚拓扑实验。

## 6. 结果解释边界

Day08矩阵用于：

- 验证代码稳定性；
- 检查负载和跳数趋势；
- 为Fixed-PRMAC止损预实验准备DCF侧数据结构。

Day08结果不直接声明协议性能优势，也不进入RL训练。
