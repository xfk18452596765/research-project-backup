# Day04：DCF基础框架

## 一、任务定位

Day04在Day03离散事件框架上实现最小单跳DCF基线，验证一个数据包在信道始终空闲、无碰撞、ACK必定成功条件下的完整发送过程。

## 二、今日目标

完成以下事件链：

```text
PACKET_ARRIVAL
→ DIFS_START
→ DIFS_END
→ BACKOFF_START
→ BACKOFF_EXPIRE
→ TX_START
→ TX_END
→ ACK
→ DELIVERED
```

## 三、已完成内容

- 新增`DCFConfig`集中保存DCF与简化PHY参数；
- 实现DIFS等待；
- 实现`[0, CWmin]`范围内的随机退避；
- 实现DATA发送和信道占用；
- 实现SIFS与ACK确认；
- 实现数据包送达、出队和节点恢复`IDLE`；
- 实现Day03统计接口兼容；
- 实现事件轨迹记录；
- 完成自动测试和主程序验证。

## 四、默认参数

| 参数 | 默认值 |
|---|---:|
| SlotTime | 20 μs |
| SIFS | 10 μs |
| DIFS | 50 μs |
| CWmin | 15 |
| CWmax | 1023 |
| 数据速率 | 2 Mbps |
| 基本速率 | 1 Mbps |
| MAC头 | 34 B |
| ACK长度 | 14 B |
| 单跳传播时延 | 1 μs |
| 随机种子 | 7 |

无竞争单跳理论时延为：

```text
D1hop
= DIFS
+ backoff_slots × SlotTime
+ DATA发送时间
+ 传播时延
+ SIFS
+ ACK发送时间
+ 传播时延
```

## 五、目录说明

```text
Day04_DCF基础框架/
├─ code/
│  ├─ dcf_config.py
│  ├─ dcf_mac.py
│  ├─ main_dcf_single_hop.py
│  └─ test_dcf_single_hop.py
├─ docs/
├─ figures/
├─ logs/
├─ results/
└─ README.md
```

## 六、运行方法

自动测试：

```powershell
python ".\daily\Day04_DCF基础框架\code\test_dcf_single_hop.py"
```

预期结果：

```text
All Day04 minimum single-hop DCF tests passed.
```

运行单跳示例：

```powershell
python ".\daily\Day04_DCF基础框架\code\main_dcf_single_hop.py"
```

## 七、关键验证结果

固定随机种子7时：

```text
退避槽数       = 10
DIFS结束       = 0.000050秒
退避结束       = 0.000250秒
DATA发送结束   = 0.004483秒
ACK到达        = 0.004606秒
端到端时延     = 0.004606秒
数据包状态     = DELIVERED
送达率         = 1.000
```

最终状态：

- 源节点队列为空；
- 节点MAC状态为`IDLE`；
- 信道恢复空闲；
- 创建包1个、送达包1个、丢弃包0个。

## 八、当前实现边界

本日尚未实现：

- 信道忙时DIFS重启；
- 退避冻结与恢复；
- 多节点碰撞；
- ACK超时；
- 二进制指数退避；
- 数据包重传；
- 多跳转发；
- 路径预约；
- 强化学习。

## 九、今日结论

Day04完成了传统DCF最小单跳成功链路，仿真时延与理论公式一致，可作为后续信道忙处理、碰撞重传和多跳DCF的基础接入模块。

## 十、明日衔接

Day05在不修改Day03和Day04稳定代码的前提下，实现信道忙检测、DIFS重启、退避冻结和恢复。
