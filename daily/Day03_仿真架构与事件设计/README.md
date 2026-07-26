# Day03：仿真架构与事件设计

## 一、任务定位

Day03建立RL-PRMAC项目的Python离散事件仿真底层框架，为后续DCF、Fixed-PRMAC和RL-PRMAC提供统一的事件、节点、数据包、信道与指标接口。

本日只搭建仿真基础设施，不实现完整DCF、路径预约或强化学习。

## 二、今日目标

1. 定义`Event`、`Simulator`、`Packet`、`Node`、`Channel`和`MetricsCollector`；
2. 建立基于优先队列的单线程离散事件引擎；
3. 统一事件时间、优先级和稳定排序规则；
4. 定义数据包、节点和信道状态；
5. 为三种MAC方案预留统一扩展接口；
6. 通过冒烟测试和组件测试验证底层框架。

## 三、已完成内容

- 实现事件排序键：

  ```text
  (time, priority, sequence)
  ```

- 实现绝对时间和相对时间调度；
- 实现节点发送队列、队列容量限制和邻居集合；
- 实现数据包固定路由、当前跳、下一跳、剩余跳数和端到端时延；
- 实现信道占用、释放和忙状态保护；
- 实现创建包、送达包、丢弃包、重传和平均时延统计；
- 完成核心组件边界测试；
- 完成最小冒烟测试。

## 四、核心模块

```text
Simulator
├─ Event
├─ Node
│  └─ tx_queue
├─ Packet
├─ Channel
└─ MetricsCollector
```

职责边界：

- `Simulator`：维护全局时钟与事件队列；
- `Event`：保存时间、优先级、顺序、类型和回调；
- `Node`：维护队列、邻居和MAC状态；
- `Packet`：维护生命周期、固定路由和时间戳；
- `Channel`：维护忙闲、占用者和释放时间；
- `MetricsCollector`：只记录结果，不参与协议决策。

## 五、目录说明

```text
Day03_仿真架构与事件设计/
├─ code/
│  ├─ event.py
│  ├─ simulator.py
│  ├─ packet.py
│  ├─ node.py
│  ├─ channel.py
│  ├─ metrics.py
│  ├─ main_smoke_test.py
│  └─ test_core_components.py
├─ docs/
├─ figures/
├─ logs/
├─ results/
└─ README.md
```

## 六、运行方法

在项目根目录执行：

```powershell
python ".\daily\Day03_仿真架构与事件设计\code\test_core_components.py"
```

预期结果：

```text
All Day03 core component tests passed.
```

运行冒烟测试：

```powershell
python ".\daily\Day03_仿真架构与事件设计\code\main_smoke_test.py"
```

预期包含：

```text
Smoke test passed.
```

## 七、验证结果

核心组件测试已验证：

- 事件优先级顺序正确；
- 同优先级事件保持插入顺序；
- 非法事件时间被拒绝；
- 节点队列容量限制有效；
- 忙信道拒绝第二个占用者；
- 数据包路由属性正确；
- 指标采集与端到端时延计算正确。

冒烟测试结果：

```text
created_packets  = 1
delivered_packets = 1
average_delay     = 0.004秒
delivery_ratio    = 1.0
```

## 八、当前实现边界

本日尚未实现：

- DIFS与随机退避；
- 信道忙时退避冻结；
- 碰撞、ACK超时和重传；
- 多跳逐跳转发；
- Fixed-PRMAC；
- RL-PRMAC；
- 动态路由和真实海面信道。

## 九、今日结论

Day03已经完成可运行、可测试、可扩展的离散事件仿真底层框架。后续协议只需要在该框架上增加MAC控制逻辑，不应把具体协议决策写入`Simulator`、`Channel`或`MetricsCollector`。

## 十、明日衔接

Day04在本框架上实现单节点、单跳、信道空闲、无碰撞条件下的最小DCF发送流程。
