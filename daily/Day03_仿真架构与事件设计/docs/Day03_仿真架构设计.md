# Day03_仿真架构设计

## 一、总体原则

采用单线程、事件驱动和全局时钟。所有未来动作必须通过Simulator调度，协议对象不得直接推进仿真时间。

事件排序键为：

\[
(\text{time},\text{priority},\text{sequence})
\]

时间越小越先执行；同一时刻优先级数字越小越先执行；仍相同则按创建顺序执行。

## 二、核心类

| 类 | 职责 |
|---|---|
| Event | 保存事件时间、优先级、类型、回调和参数 |
| Simulator | 维护全局时间、事件优先队列和运行循环 |
| Packet | 保存源、目的、路径、状态、重传和时间戳 |
| Node | 保存发送队列、邻居和MAC状态 |
| Channel | 保存空闲/占用状态、占用者和释放时间 |
| MetricsCollector | 记录创建、送达、丢弃、重传和时延 |

## 三、协议层次

```text
Simulator
├─ Node
│  ├─ Queue
│  ├─ Route
│  └─ MACProtocol
│     ├─ DCFMac
│     ├─ FixedPRMAC
│     └─ RLPRMAC
├─ Channel
└─ MetricsCollector
```

三种MAC协议后续统一提供：

```python
on_packet_arrival(packet)
try_access()
on_channel_idle()
on_tx_success(packet)
on_tx_failure(packet)
```

## 四、时间单位

内部统一采用秒：10微秒写为`10e-6`，1毫秒写为`1e-3`。

## 五、推荐事件优先级

| 优先级 | 事件 |
|---:|---|
| 0 | 信道释放、接收完成 |
| 10 | ACK、预约确认 |
| 20 | 发送开始 |
| 30 | 退避结束 |
| 40 | 分组到达 |
| 90 | 指标采样 |
