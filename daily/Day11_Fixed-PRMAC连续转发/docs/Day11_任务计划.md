# Day11任务计划：Fixed-PRMAC连续转发

## 任务目标

在Day10已经建立的`ACTIVE`预约段上，实现固定K=2的连续DATA转发和每跳H_ACK确认。

## 实现顺序

1. 继承Day10消息模型和冲突控制器；
2. 增加与DCF一致的DATA/H_ACK PHY参数；
3. 增加段转发状态与指标；
4. 实现ACTIVE状态校验；
5. 实现DATA_TX/DATA_RX；
6. 实现H_ACK_TX/H_ACK_RX；
7. 前一跳确认后再启动下一跳；
8. 预约段末端停止，不跨段；
9. 编写专项测试；
10. 运行完整回归、主程序和结果导出。

## 完成判据

- K=2产生2个DATA和2个H_ACK；
- DATA方向与预约链路一致；
- H_ACK方向与DATA相反；
- 下一跳DATA晚于前一跳H_ACK_RX一个SIFS；
- 非ACTIVE预约不能转发；
- 数据包只推进`effective_hops`；
- 时延与字节统计可解析复核；
- Day03—Day11完整回归通过。

## 禁止提前实现

- 失败重试；
- 跨预约段转发；
- 性能对比；
- 强化学习。
