# Day09：Fixed-PRMAC报文与预约设计

## 1. 与DCF基线的关系

传统DCF：

```text
每到一个中继
→ 重新DIFS
→ 重新退避
→ 重新竞争
→ DATA/ACK
```

Fixed-PRMAC计划：

```text
预约段起始节点竞争一次
→ 建立K跳路径段预约
→ 预约段内连续转发
```

Day09只完成控制平面，不完成预约段内DATA连续转发。

本日入口`schedule_reservation()`表示：

> 当前预约段起始节点已经获得发送PR_REQ的机会。

固定CW参数已经进入配置和事件记录，但完整的DCF竞争与PR_REQ接入整合将在后续联调阶段完成。

## 2. 成功预约时序

以路径：

```text
0 → 1 → 2 → 3
```

以及：

```text
K_fixed = 2
```

为例：

```text
节点0：RESERVATION_START
节点0：PR_REQ_TX 0→1
节点1：PR_REQ_RX
节点1：PR_REQ_TX 1→2
节点2：PR_REQ_RX
节点2：PR_ACK_TX 2→1
节点1：PR_ACK_RX
节点1：PR_ACK_TX 1→0
节点0：PR_ACK_RX
节点0：RESERVATION_ACTIVE
```

最终预约链路为：

```text
0→1
1→2
```

节点2是预约段末端。由于目的节点3仍未到达，Day11完成连续转发后，节点2将成为下一预约段起始节点。

## 3. 预约状态

```text
PENDING
→ ACTIVE
→ RELEASED
```

或：

```text
PENDING
→ ACTIVE
→ EXPIRED
```

同时预留：

```text
FAILED
```

但Day09不产生FAILED，也不实现PR_NACK。

## 4. 预约表

每条预约记录保存：

- ReservationID；
- FlowID；
- PacketID；
- 完整路径；
- 预约段起始索引；
- 请求K；
- 实际K；
- 预约链路集合；
- 发起节点；
- 预约段末端；
- 优先级；
- 持续时间；
- 请求时刻；
- 激活时刻；
- 到期时刻；
- 释放时刻；
- 当前状态。

## 5. 控制开销

K=2时，成功预约需要：

```text
2次PR_REQ传输
+ 2次PR_ACK传输
= 4次控制帧传输
```

默认帧大小：

```text
PR_REQ = 36字节
PR_ACK = 24字节
```

所以成功建立一次2跳预约的控制字节数为：

```text
2×36 + 2×24 = 120字节
```

RELEASE如沿2跳传播，则再增加：

```text
2×20 = 40字节
```

这些是事件级抽象参数，后续可根据论文正式帧格式统一调整。

## 6. Day09为何不做冲突拒绝

Day10目录固定为：

```text
Day10_Fixed-PRMAC冲突模型
```

因此Day09预约表只维护生命周期，不判断两条预约是否共享节点、链路或干扰范围。

测试中允许两条重叠预约同时ACTIVE，是为了明确验证：

> Day09尚未提前实现Day10功能。

## 7. Day10衔接

Day10将在当前预约表前增加：

1. 冲突链路判定；
2. 半双工冲突；
3. 相邻干扰冲突；
4. 已有ACTIVE/PENDING预约查询；
5. PR_NACK返回；
6. 失败原因记录；
7. 冲突预约不进入ACTIVE。
