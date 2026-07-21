# Day03_完成标准问题总结

## 一、为什么采用离散事件仿真？

本研究采用Python离散事件仿真，是因为MAC协议中的大多数行为都由特定事件触发，例如数据包到达、退避结束、信道释放、发送完成、ACK到达和预约超时等。离散事件仿真只在事件发生时推进仿真时钟，不需要以固定时间步长持续计算，因此能够显著减少无效计算。

与固定步长仿真相比，离散事件仿真具有以下优点：

1. **适合描述MAC协议过程**  
   DCF、Fixed-PRMAC和RL-PRMAC都可以表示为一系列事件及其先后关系。

2. **计算效率较高**  
   当两个事件之间没有协议状态变化时，仿真时间可以直接跳到下一个事件时刻。

3. **便于控制事件顺序**  
   可以明确处理同一时刻发生的信道释放、发送开始、ACK到达等事件。

4. **便于逐步扩展协议**  
   后续可以在同一个事件框架中加入DCF退避、路径预约、强化学习决策和指标采集，而不需要重写底层仿真逻辑。

因此，离散事件仿真适合本研究40天内快速完成机制验证、参数实验和协议对比。

---

## 二、Simulator和MAC协议各负责什么？

### 1. Simulator的职责

`Simulator`是整个仿真系统的时间和事件管理器，主要负责：

- 维护全局仿真时钟；
- 保存未来待执行事件；
- 按照事件时间和优先级调度事件；
- 执行事件对应的回调函数；
- 控制仿真结束时间或最大事件数；
- 记录事件执行日志。

`Simulator`只负责“什么时候执行什么事件”，不负责判断DCF应该选多大的竞争窗口，也不负责决定路径预约长度。

### 2. MAC协议的职责

MAC协议负责具体的信道接入规则，主要包括：

- 数据包到达后是否立即竞争；
- 等待DIFS的时间；
- 如何选择随机退避值；
- 信道忙时是否冻结退避；
- 何时发送DATA、RTS、CTS或预约报文；
- 发送失败后是否重传；
- 如何调整竞争窗口；
- Fixed-PRMAC采用多长的预约段；
- RL-PRMAC如何根据状态选择动作。

### 3. 两者的关系

可以概括为：

> MAC协议决定“下一步要做什么”，Simulator决定“这一步在什么时候发生”。

例如，DCF协议决定等待50 μs后开始退避，MAC协议会调用Simulator：

```python
simulator.schedule(
    delay=difs_time,
    callback=start_backoff
)
```

之后由Simulator在对应仿真时刻执行`start_backoff()`。

---

## 三、一个数据包从产生到送达会经过哪些事件？

在完整DCF多跳仿真中，一个数据包通常会经历以下事件：

```text
PACKET_ARRIVAL
→ QUEUE
→ DIFS_WAIT
→ BACKOFF_START
→ BACKOFF_TICK
→ BACKOFF_EXPIRE
→ TX_START
→ TX_END
→ RX_SUCCESS
→ ACK
→ 下一跳转发或DELIVERED
```

具体过程如下。

### 1. 数据包产生

业务生成器创建一个数据包，并调度：

```text
PACKET_ARRIVAL
```

数据包记录源节点、目的节点、生成时间、路径和业务优先级。

### 2. 数据包进入队列

源节点将数据包放入发送队列，数据包状态变为：

```text
QUEUED
```

如果队列已满，数据包会被丢弃。

### 3. 信道接入

当数据包位于队首时，MAC协议开始执行：

- 信道侦听；
- DIFS等待；
- 随机退避；
- 信道忙时冻结退避；
- 退避计数归零后开始发送。

对应事件包括：

```text
BACKOFF_START
BACKOFF_TICK
BACKOFF_EXPIRE
```

### 4. 数据发送

节点占用信道并触发：

```text
TX_START
```

发送持续一定时间后，触发：

```text
TX_END
```

### 5. 接收与确认

如果没有碰撞或信道错误，下一跳节点触发：

```text
RX_SUCCESS
```

随后返回ACK。

如果发送节点在规定时间内没有收到ACK，则触发：

```text
ACK_TIMEOUT
```

并进入重传流程。

### 6. 多跳转发

如果当前接收节点不是最终目的节点，数据包会进入该中继节点的发送队列，并重复上述竞争过程。

如果已经到达目的节点，则状态变为：

```text
DELIVERED
```

MetricsCollector根据创建时间和送达时间计算端到端时延。

---

## 四、同一时刻多个事件如何排序？

仿真中的事件按照以下三元组排序：

\[
(\text{time},\text{priority},\text{sequence})
\]

### 1. 先比较事件时间

发生时间更早的事件先执行。

例如：

```text
t=0.003 s 的TX_START
```

一定早于：

```text
t=0.005 s 的RX_SUCCESS
```

### 2. 时间相同时比较优先级

优先级数值越小，越先执行。

例如，在同一时刻：

```text
TX_END，priority=0
RX_SUCCESS，priority=10
```

则`TX_END`先执行，先释放信道，再处理接收成功。

推荐事件优先级如下：

| 优先级 | 事件 |
|---:|---|
| 0 | 信道释放、发送结束 |
| 10 | 接收成功、ACK、预约确认 |
| 20 | 发送开始 |
| 30 | 退避结束 |
| 40 | 数据包到达 |
| 90 | 统计采样 |

### 3. 时间和优先级都相同时比较创建顺序

每个事件在创建时都会获得一个唯一的序号`sequence`。

如果两个事件的时间和优先级完全相同，则先创建的事件先执行，从而保证仿真结果具有确定性和可重复性。

---

## 五、Node、Channel和Metrics之间如何协作？

### 1. Node

`Node`代表网络中的船舶节点，主要保存：

- 节点编号；
- 发送队列；
- MAC状态；
- 邻居节点；
- 当前队首数据包；
- 后续的路由和协议对象。

Node负责管理本节点的数据包，但不直接控制全局时间。

### 2. Channel

`Channel`代表共享无线信道，主要保存：

- 当前信道是否空闲；
- 当前占用信道的节点；
- 信道释放时间；
- 后续的碰撞和干扰状态。

节点发送前需要先检查Channel。发送开始时占用Channel，发送结束时释放Channel。

### 3. MetricsCollector

`MetricsCollector`只负责记录和统计，不参与协议决策，主要记录：

- 创建数据包数量；
- 成功送达数量；
- 丢包数量；
- 重传次数；
- 端到端时延；
- 送达率；
- 后续的吞吐量和控制开销。

### 4. 三者的协作流程

典型流程为：

```text
Node队列中存在数据包
→ MAC协议向Channel申请发送
→ Channel空闲，允许Node发送
→ Simulator调度TX_END
→ Channel释放
→ 下一跳Node接收数据包
→ Metrics记录发送或送达结果
```

三者之间的职责边界必须保持清晰：

- Node不负责推进仿真时间；
- Channel不决定哪个节点优先发送；
- Metrics不改变协议行为；
- MAC协议不直接修改最终统计结果。

---

## 六、DCF以后从哪个位置接入当前框架？

DCF将作为Node与Channel之间的MAC控制模块接入当前框架。

整体结构为：

```text
Simulator
├─ Node
│  ├─ tx_queue
│  └─ DCFMac
├─ Channel
└─ MetricsCollector
```

### 1. 数据包到达入口

当数据包到达Node后：

```python
node.enqueue(packet)
dcf_mac.on_packet_arrival(packet)
```

DCF检查数据包是否位于队首，并决定是否启动信道接入。

### 2. 信道接入入口

DCF通过以下过程使用Channel：

```text
检查信道
→ 等待DIFS
→ 选择随机退避
→ 退避归零
→ 占用Channel
```

### 3. 事件调度入口

DCF不会直接推进时间，而是通过Simulator调度：

```text
DIFS_END
BACKOFF_TICK
TX_START
TX_END
ACK_TIMEOUT
```

### 4. 结果反馈入口

发送成功后调用：

```python
dcf_mac.on_tx_success(packet)
```

发送失败或ACK超时后调用：

```python
dcf_mac.on_tx_failure(packet)
```

DCF根据结果：

- 更新竞争窗口；
- 增加重传次数；
- 重新竞争；
- 或将数据包丢弃。

### 5. 后续协议扩展

在底层框架不变的情况下，可以将DCF替换为：

```text
FixedPRMAC
RLPRMAC
```

三种协议共用：

- Simulator；
- Node；
- Packet；
- Channel；
- MetricsCollector。

区别只存在于MAC接入和路径预约决策逻辑中。

---

## 七、第三天结论

第三天已经完成Python离散事件仿真的底层框架，并通过事件排序、节点队列、信道占用、数据包属性和指标采集测试。

当前框架的核心逻辑可以概括为：

> Simulator负责时间和事件调度，MAC协议负责信道接入规则，Node负责数据包队列和节点状态，Channel负责信道占用，MetricsCollector负责结果统计。

下一步进入Day04，在当前框架上实现最小DCF单跳流程：

\[
\text{PACKET\_ARRIVAL}
\rightarrow
\text{DIFS}
\rightarrow
\text{随机退避}
\rightarrow
\text{DATA发送}
\rightarrow
\text{ACK确认}
\]
