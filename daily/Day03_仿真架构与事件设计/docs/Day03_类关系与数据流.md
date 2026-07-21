# Day03_类关系与数据流

1. 业务生成器创建Packet；
2. Simulator调度PACKET_ARRIVAL；
3. Node将分组放入发送队列；
4. MAC协议决定何时竞争；
5. Channel负责占用和释放；
6. MetricsCollector记录关键时间点。

约束：Simulator不包含具体MAC规则；Channel不决定竞争者；Node不直接推进时间；MetricsCollector不改变协议行为。

## 后续扩展

- Day04—Day08：DCFMAC、DIFS、随机退避、DATA/ACK、重传、多跳转发；
- Day09—Day13：ReservationManager、PR-REQ/PR-ACK、固定预约长度；
- Day14—Day18：QLearningAgent、状态、动作、奖励和Q表更新。
