# Day11 Fixed-PRMAC连续转发设计

## 1. 状态前提

Day11不重新建立预约。调用连续转发前，预约记录必须满足：

```text
status = ACTIVE
packet_id与预约一致
packet.route与预约path一致
packet.current_hop_index = segment_start_index
packet.current_node = initiator
```

同时，预约剩余时间必须覆盖完整转发过程。

## 2. 单跳事件链

第`i`条预约链路为`u_i → u_{i+1}`：

```text
DATA_TX(u_i → u_{i+1})
→ DATA_RX(u_{i+1})
→ SIFS
→ H_ACK_TX(u_{i+1} → u_i)
→ H_ACK_RX(u_i)
```

当`i+1 < K_effective`时，再等待一个SIFS并启动下一跳DATA。

## 3. 段转发时延

设：

- `N`为有效预约跳数；
- `T_DATA`为DATA序列化与传播时间；
- `T_HACK`为H_ACK序列化与传播时间；
- `T_SIFS`为SIFS。

则：

```text
T_segment
= N × (T_DATA + T_SIFS + T_HACK)
+ (N - 1) × T_SIFS
```

1024字节负载、K=2时：

```text
DATA frame bytes = 1024 + 34 = 1058 bytes
DATA serialization = 1058 × 8 / 2 Mbps = 0.004232 s
DATA link delay = 0.004232 + 0.000001 = 0.004233 s
H_ACK serialization = 14 × 8 / 1 Mbps = 0.000112 s
H_ACK link delay = 0.000112 + 0.000001 = 0.000113 s

T_segment
= 2 × (0.004233 + 0.000010 + 0.000113)
+ 1 × 0.000010
= 0.008722 s
```

## 4. 数据包状态

每次`DATA_RX`后推进一个路径索引：

- 未到最终目的节点：`FORWARDED`；
- 到达最终目的节点：`DELIVERED`，记录`delivered_at`。

K=2且完整路径超过2跳时，数据包停在预约段末端，不自动申请下一段预约。

## 5. 指标边界

控制帧指标继续记录：

- PR_REQ；
- PR_ACK；
- PR_NACK；
- RELEASE。

Day11新增：

- DATA帧数与字节数；
- H_ACK帧数与字节数；
- 已转发跳数；
- 完成预约段数；
- 段转发时延；
- 总帧数与总字节数。

## 6. 当前边界

本日假设预约段内DATA和H_ACK可靠到达，不实现DATA/H_ACK超时、重传或预约失败后的退避。这些不应在Day11提前加入。
