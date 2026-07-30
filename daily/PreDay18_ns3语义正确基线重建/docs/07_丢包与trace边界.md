# 07 丢包与 trace 边界

自定义 trace 每行包含 time、node_id、flow_id、packet_id、segment_id、
attempt、hop_index、frame_type、event、reason、queue_length、
reservation_id 和逻辑大小。

边界覆盖 PacketSocket 接受/拒绝、MAC TX/RX/drop、PHY TX/RX begin/end/drop、
控制生命周期、reserved enqueue、释放与最终包终态。逻辑帧创建先减去 14-byte
序列化头，因此 PR_REQ=36、PR_ACK/PR_NACK=24、H_ACK=14、RELEASE=20、
DATA=1024 均满足 `Packet::GetSize()==configured`；MAC/PHY 开销单独由底层
trace 的 packet size 体现。

每个创建包唯一计入 DELIVERED 或一种 final loss。60 个语义/稳定性结果均满足
`created=sum(terminal_counts)`、`UNKNOWN_LOSS=0`、结束时无 active reservation。
高负载中的 `SIMULATION_STOP_TIMEOUT` 是明确终态，不用于宣称协议优劣。
