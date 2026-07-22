# Day04第一阶段验证结果

## 一、测试场景

- 发送节点：节点0
- 接收节点：节点1
- 固定路由：(0, 1)
- 数据包数量：1
- 信道状态：始终空闲
- 碰撞条件：无碰撞
- ACK条件：必定成功

## 二、DCF事件链

PACKET_ARRIVAL
→ DIFS_START
→ DIFS_END
→ BACKOFF_START
→ BACKOFF_EXPIRE
→ TX_START
→ TX_END
→ ACK
→ DELIVERED

## 三、时序结果

- 数据包到达时刻：0.000000 s
- DIFS结束时刻：0.000050 s
- 随机退避槽数：10
- 退避结束时刻：0.000250 s
- DATA发送结束时刻：0.004483 s
- ACK到达时刻：0.004606 s
- 端到端时延：0.004606 s

## 四、最终状态

- 数据包状态：DELIVERED
- 源节点队列长度：0
- 节点MAC状态：IDLE
- 信道是否空闲：True
- 数据包送达率：1.000

## 五、测试结论

自动测试结果：

All Day04 minimum single-hop DCF tests passed.

Day04第一阶段单节点、单跳、无竞争条件下的最小DCF流程验证通过。
