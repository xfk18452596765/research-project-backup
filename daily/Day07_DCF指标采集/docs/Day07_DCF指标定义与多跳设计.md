# Day07：DCF指标定义与多跳设计

## 1. 继承关系

```text
Day04 DCFMac
    ↓
Day05 DCFBusyMac
    ↓
Day06 DCFContentionMac
    ↓
Day07 DCFMultiHopMac
```

Day07只新增扩展类，不修改Day03—Day06稳定代码。

## 2. 多跳处理原则

### 2.1 路由固定

数据包使用`Packet.route`保存固定路径，使用：

- `current_hop_index`；
- `current_node`；
- `next_hop`；
- `remaining_hops`；
- `advance_hop()`。

### 2.2 每跳独立竞争

一次ACK只代表当前链路发送成功。

若尚未到达目的节点：

1. 当前发送节点将数据包出队；
2. 数据包执行`advance_hop()`；
3. 本跳重传计数被指标采集器保存；
4. 数据包在下一中继重新入队；
5. 下一中继从CWmin重新开始独立DCF竞争。

预约段内部连续转发尚未实现，因此该流程仍是传统DCF基线。

### 2.3 重传语义

`retry_limit`按单跳生效。

- 当前跳成功后，若还需继续转发，则`packet.retries`重置为0；
- 已完成跳的重传次数写入`HopMetrics`；
- 全路径累计重传次数写入`DCFMetricsCollector.packet_retry_counts`。

## 3. 指标定义

### 3.1 排队时延

```text
queue_delay = first_DIFS_START - queue_enter_at
```

表示数据包进入当前节点队列后，等待成为队首的时间。

### 3.2 接入时延

```text
access_delay = successful_TX_START - first_DIFS_START
```

包括DIFS、退避、冻结、碰撞、ACK超时和重传造成的接入等待。

### 3.3 发送确认时延

```text
tx_ack_delay = ACK - successful_TX_START
```

包括成功DATA发送、传播、SIFS和ACK发送。

### 3.4 单跳时延

```text
hop_delay = ACK - queue_enter_at
```

### 3.5 端到端时延

沿用`Packet.end_to_end_delay`：

```text
end_to_end_delay = delivered_at - created_at
```

### 3.6 竞争次数

一次新的`BACKOFF_START`计为一次竞争尝试。

`BACKOFF_RESUME`只是恢复冻结的剩余退避，不计为新的竞争。

### 3.7 DIFS次数

每个`DIFS_START`均计数，包括：

- 初次竞争；
- 信道忙后重新DIFS；
- 碰撞重传后的新DIFS。

### 3.8 累计退避时间

```text
cumulative_backoff_time
= consumed_backoff_slots × slot_time
```

只统计实际空闲槽倒计时，不把信道忙期间的冻结等待混入退避倒计时。

## 4. Day07验证场景

### 场景A：2跳单流

```text
0 → 1 → 2
```

验证中继重新入队和重新竞争。

### 场景B：2、4、6跳单流

每跳固定退避10槽，验证端到端时延累计。

### 场景C：双发送节点单跳碰撞

沿用Day06确定性退避序列，验证新增指标采集器不会破坏碰撞、ACK超时、BEB和重传。
