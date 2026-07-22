# Day04：DCF单节点单跳最小流程设计

## 一、在现有框架中的位置

Day03已经固定底层职责：

```text
Simulator：维护时间与事件队列
Node：维护节点状态与发送队列
Packet：维护数据包生命周期和固定路由
Channel：维护信道空闲、占用者和释放时间
MetricsCollector：只记录结果，不参与协议决策
DCFMac：决定何时等待、退避、发送和处理ACK
```

因此Day04只新增MAC控制层，不修改Day03核心对象，也不改变后续三协议共用底层框架的原则。

## 二、最小状态过程

### 1. PACKET_ARRIVAL

数据包进入源节点发送队列，状态变为`QUEUED`。当它是队首且节点为`IDLE`时，DCF开始接入。

### 2. DIFS

信道必须连续空闲一个DIFS。第一阶段信道始终空闲，因此只调度一个`DIFS_END`事件，不实现中途被打断。

### 3. 随机退避

在区间

```text
[0, CWmin]
```

均匀选择整数退避槽数：

\[
B\sim U\{0,1,\ldots,CW_{\min}\}
\]

退避时间为：

\[
T_{bo}=B\cdot T_{slot}
\]

第一阶段无其他节点竞争，所以无需逐槽冻结，只调度`BACKOFF_EXPIRE`。

### 4. TX_START与TX_END

DATA发送时间为：

\[
T_{data}=\frac{8(L_{payload}+L_{MAC})}{R_{data}}
\]

为保留传播时间，信道占用持续到：

\[
T_{data,channel}=T_{data}+T_{prop}
\]

`TX_START`时：

- 节点状态变为`TRANSMITTING`；
- 数据包状态变为`TRANSMITTING`；
- Channel被当前节点占用。

`TX_END`时：

- Channel释放；
- 节点状态变为`WAIT_ACK`。

### 5. ACK与DELIVERED

ACK到达延迟为：

\[
T_{ack-delay}=T_{SIFS}+T_{ack}+T_{prop}
\]

其中：

\[
T_{ack}=\frac{8L_{ACK}}{R_{basic}}
\]

ACK成功后：

- `packet.advance_hop()`将数据包推进到目的节点；
- 单跳路由使状态变为`DELIVERED`；
- 记录`delivered_at`；
- 数据包从源节点队列出队；
- 节点状态恢复为`IDLE`；
- CW恢复为`CWmin`；
- Metrics记录成功送达。

## 三、单跳理论总时延

在无排队、无碰撞、无重传条件下：

\[
D_{1hop}=T_{DIFS}+B T_{slot}+T_{data}+T_{prop}+T_{SIFS}+T_{ack}+T_{prop}
\]

该公式由测试程序直接计算，并与仿真中的`packet.end_to_end_delay`比较。

## 四、默认参数

| 参数 | 默认值 | 说明 |
|---|---:|---|
| SlotTime | 20 μs | 简化时隙长度 |
| SIFS | 10 μs | 简化短帧间隔 |
| DIFS | 50 μs | 简化分布式帧间隔 |
| CWmin | 15 | 初始竞争窗口 |
| CWmax | 1023 | 后续重传阶段预留 |
| 数据速率 | 2 Mbps | 当前统一仿真假设 |
| 基本速率 | 1 Mbps | ACK发送速率 |
| MAC头 | 34 B | 简化帧开销 |
| ACK | 14 B | 简化ACK长度 |
| 传播时延 | 1 μs | 当前单跳统一假设 |
| 随机种子 | 7 | 保证测试可重复 |

这些参数是当前仿真假设，后续三种MAC方案必须共享相同的基础参数，保证公平对比。

## 五、事件优先级

沿用Day03原则：数值越小，同一时刻越先执行。

| 优先级 | 事件 |
|---:|---|
| 0 | TX_END / 信道释放 |
| 10 | ACK |
| 20 | TX_START |
| 30 | DIFS_END / BACKOFF_EXPIRE |
| 40 | PACKET_ARRIVAL |

## 六、下一阶段接口预留

本阶段保留以下接口，但不实现失败逻辑：

```python
dcf_mac.on_tx_success(packet)
dcf_mac.on_tx_failure(packet)
```

后续可在不修改Day03底层框架的情况下加入：

- 信道忙时DIFS重置；
- 退避冻结与恢复；
- ACK超时；
- 重传计数；
- 二进制指数退避；
- 多节点碰撞。

这些属于Day04后续阶段，不属于当前最小实现。
