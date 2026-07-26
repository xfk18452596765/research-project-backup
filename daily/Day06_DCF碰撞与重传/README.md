# Day06：DCF碰撞与重传

## 一、任务定位

Day06在Day05信道忙与退避冻结机制上，引入多个独立DCF发送节点和共享碰撞域，实现传统DCF基线中的碰撞、ACK超时、二进制指数退避、重传和重传上限丢包。

## 二、今日目标

完成以下流程：

```text
两个节点独立DIFS与退避
→ 同一时隙退避归零
→ 同时发送DATA
→ COLLISION
→ 无ACK
→ ACK_TIMEOUT
→ retries增加
→ CW扩大
→ 重新DIFS和退避
→ 退避值分离
→ 依次成功送达
```

## 三、已完成内容

- 实现`CollisionChannel`共享碰撞域；
- 实现`DCFContentionCoordinator`同槽发送意图统一判定；
- 实现多个节点同槽发送产生一次共享碰撞；
- 实现碰撞DATA不返回ACK；
- 实现`ACK_TIMEOUT`；
- 实现数据包重传次数；
- 实现二进制指数退避：

  ```text
  CWnew = min(2 × CWold + 1, CWmax)
  ```

- 实现重传后的重新竞争；
- 保留重传竞争中的退避冻结与恢复；
- 实现重传上限和丢包；
- 成功后CW恢复`CWmin`；
- 完成自动测试和双节点演示。

## 四、核心事件链

```text
PACKET_ARRIVAL
→ DIFS
→ BACKOFF
→ TX_SLOT_RESOLVE
→ TX_START
→ COLLISION
→ TX_END
→ ACK_TIMEOUT
→ CW_UPDATE
→ DIFS
→ BACKOFF
→ 重传
→ ACK
→ DELIVERED
```

## 五、目录说明

```text
Day06_DCF碰撞与重传/
├─ code/
│  ├─ dcf_collision_mac.py
│  ├─ main_dcf_two_node_collision.py
│  └─ test_dcf_collision_retry.py
├─ docs/
├─ figures/
├─ logs/
├─ results/
└─ README.md
```

## 六、运行方法

自动测试：

```powershell
python ".\daily\Day06_DCF碰撞与重传\code\test_dcf_collision_retry.py"
```

预期结果：

```text
All Day06 DCF collision and retransmission tests passed.
```

运行演示：

```powershell
python ".\daily\Day06_DCF碰撞与重传\code\main_dcf_two_node_collision.py"
```

## 七、关键验证结果

第一次竞争：

```text
节点0退避 = 0
节点1退避 = 0
碰撞次数  = 1
```

碰撞后：

```text
两个数据包retries = 1
CW：15 → 31
```

第一次重传：

```text
节点0退避 = 0
节点1退避 = 1
```

最终结果：

```text
packet0_delay = 0.008812秒
packet1_delay = 0.013238秒
两个数据包状态 = DELIVERED
成功交换次数   = 2
送达率         = 1.000
信道最终空闲
两个节点状态均为IDLE
```

`retry_limit=0`时，两个碰撞数据包均被正确丢弃。

## 八、设计说明

`DCFContentionCoordinator`只代表共享介质对同一时隙发送意图的判定，不为节点选择退避值，也不构成集中式MAC控制。各节点仍然独立维护队列、CW、退避计数和重传状态。

## 九、当前实现边界

本日尚未实现：

- 隐藏终端和捕获效应；
- 非碰撞信道误码；
- RTS/CTS；
- 多跳逐跳转发；
- 多业务流完整拓扑；
- 路径预约；
- Fixed-PRMAC；
- Q-learning；
- 真实海面传播模型。

## 十、今日结论

Day06完成了传统DCF基线中的碰撞和重传核心能力，为多跳路径中的竞争、碰撞、重传和累计时延实验提供基础。

## 十一、明日衔接

Day07实现固定路由多跳DCF逐跳转发，并建立每跳与端到端指标采集器。
