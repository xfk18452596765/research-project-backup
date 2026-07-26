# Day08：DCF验证与调试

## 一、任务定位

Day08不开发新协议，而是对Day07多跳DCF基线进行验证与调试，确保随机退避、多数据包、不同负载、碰撞重传和指标统计能够稳定联合运行。

Day08完成后，DCF基线进入可用于后续Fixed-PRMAC对比的状态。

## 二、今日目标

1. 修复底层日志中的`GENERIC`事件名称；
2. 修正排队时延和信道接入时延的统计边界；
3. 验证相同随机种子的可重复性；
4. 验证不同随机种子产生不同退避结果；
5. 验证高负载下队列与时延增长；
6. 验证两条业务流共享中继时的碰撞和重传；
7. 建立2、4、6跳×低、中、高负载×3个随机种子的DCF验证矩阵；
8. 完成Day03—Day08完整回归。

## 三、已完成内容

- 新增`DCFValidatedMultiHopMac`；
- 保留`PACKET_ARRIVAL`、`FORWARD_ARRIVAL`和`TX_SLOT_RESOLVE`等真实事件名；
- 新增`head_of_line_at`；
- 修正时延分解：

  ```text
  queue_delay = head_of_line_at - queue_enter_at

  access_delay = successful_TX_START - head_of_line_at

  tx_ack_delay = ACK - successful_TX_START

  hop_delay
  = queue_delay
  + access_delay
  + tx_ack_delay
  ```

- 实现周期多数据包链式场景；
- 实现相同种子复现和不同种子差异测试；
- 实现汇聚业务流碰撞烟雾测试；
- 完成27组验证矩阵；
- 输出原始CSV、聚合CSV和JSON汇总；
- 完成Day03—Day08回归测试。

## 四、负载与实验设置

| 负载 | 包间隔 |
|---|---:|
| low | 0.050秒 |
| medium | 0.020秒 |
| high | 0.008秒 |

验证矩阵：

```text
跳数：2、4、6
负载：low、medium、high
随机种子：7、17、27
每组数据包：8
总运行数：27
```

## 五、目录说明

```text
Day08_DCF验证与调试/
├─ code/
│  ├─ dcf_validation.py
│  ├─ test_dcf_validation.py
│  ├─ main_dcf_validation_matrix.py
│  └─ run_day03_day08_regression.py
├─ docs/
├─ figures/
├─ logs/
├─ results/
└─ README.md
```

## 六、运行方法

Day08自动测试：

```powershell
python ".\daily\Day08_DCF验证与调试\code\test_dcf_validation.py"
```

完整回归：

```powershell
python ".\daily\Day08_DCF验证与调试\code\run_day03_day08_regression.py"
```

验证矩阵：

```powershell
python ".\daily\Day08_DCF验证与调试\code\main_dcf_validation_matrix.py"
```

## 七、测试结果

Day08自动测试：

```text
All Day08 DCF validation and debugging tests passed.
```

完整回归：

```text
All Day03-Day08 regression tests passed.
```

验证内容包括：

- Day08日志中不再出现`GENERIC`；
- 相同种子结果一致；
- 不同种子结果不同；
- 时延分解误差小于`1e-12`；
- 高负载排队时延高于低负载；
- 汇聚场景碰撞后两个数据包均成功完成多跳转发。

## 八、聚合实验结果

三次随机种子的平均结果：

| 跳数 | 负载 | 平均端到端时延 | 平均碰撞 | 平均重传 |
|---:|---|---:|---:|---:|
| 2 | low | 0.009109秒 | 0.00 | 0.00 |
| 2 | medium | 0.009109秒 | 0.00 | 0.00 |
| 2 | high | 0.017752秒 | 1.00 | 2.00 |
| 4 | low | 0.018196秒 | 0.00 | 0.00 |
| 4 | medium | 0.018196秒 | 0.00 | 0.00 |
| 4 | high | 0.081354秒 | 3.00 | 6.00 |
| 6 | low | 0.027350秒 | 0.00 | 0.00 |
| 6 | medium | 0.086996秒 | 3.00 | 6.33 |
| 6 | high | 0.154250秒 | 4.67 | 9.33 |

所有27组场景送达率均为：

```text
delivery_ratio = 1.000
```

最大时延分解误差为：

```text
2.7755575615628914e-17
```

该数值属于浮点误差，可视为0。

## 九、汇聚碰撞烟雾测试

拓扑：

```text
0 ─┐
   ├→ 2 → 3
1 ─┘
```

结果：

```text
created_packets          = 2
delivered_packets        = 2
dropped_packets          = 0
successful_hops          = 4
shared_collision_events  = 1
collided_packet_attempts = 2
retransmissions          = 2
backoff_freezes          = 2
queues_empty             = 1
channel_idle             = 1
```

## 十、结果文件

```text
results/
├─ dcf_validation_raw.csv
├─ dcf_validation_aggregate.csv
├─ dcf_converging_collision_smoke.json
└─ dcf_validation_summary.json
```

## 十一、结果解释

低负载下，端到端时延近似随跳数线性增长。

高负载和长路径下，同一路径中的多个数据包会同时位于不同中继，产生：

```text
逐跳重新竞争
+ 中继排队
+ 流内竞争
+ 碰撞
+ ACK超时
+ 重传
→ 端到端时延快速放大
```

这正是后续Fixed-PRMAC需要缓解的问题。

## 十二、当前实现边界

当前矩阵用于功能验证和趋势检查，尚不是论文最终实验规模。当前限制包括：

- 每组只有8个数据包；
- 只有3个随机种子；
- 使用周期到达；
- 所有节点位于同一共享碰撞域；
- 未建立距离相关冲突图和空间复用；
- 未加入真实海面传播模型；
- 未加入动态路由。

## 十三、今日结论

Day08完成了多跳DCF基线的验证与调试。随机性、负载趋势、碰撞重传、共享中继和指标分解均已通过测试，DCF基线可以进入Fixed-PRMAC阶段。

## 十四、明日衔接

Day09实现Fixed-PRMAC的报文模型和最小成功预约流程：

```text
PR_REQ前向传播
→ PR_ACK反向确认
→ 固定K=2预约建立
```

Day09不提前实现预约冲突、连续DATA转发或强化学习。
