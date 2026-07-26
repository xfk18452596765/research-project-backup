# Day11：Fixed-PRMAC连续转发

## 一、任务定位

Day11严格继承Day09的成功预约控制平面和Day10的冲突拒绝模型，只实现一个已经处于`ACTIVE`状态的固定预约段内的连续`DATA`转发与逐跳`H_ACK`确认。

技术路线保持：

```text
DCF → Fixed-PRMAC → RL-PRMAC
```

本日仍处于Fixed-PRMAC阶段，不实现预约失败后的退避重试、跨预约段完整端到端传输、性能对比或强化学习。

## 二、固定流程

```text
ACTIVE预约
→ DATA_TX（预约链路第1跳）
→ DATA_RX
→ SIFS
→ H_ACK_TX
→ H_ACK_RX
→ SIFS
→ DATA_TX（预约链路第2跳）
→ DATA_RX
→ SIFS
→ H_ACK_TX
→ H_ACK_RX
→ SEGMENT_FORWARD_COMPLETE
```

固定预约参数继续使用：

```text
K_fixed = 2
CWmin_fixed = 15
K_effective = min(K_fixed, remaining_hops)
```

PHY参数与既有DCF基线保持一致：

```text
DATA rate       = 2 Mbps
Basic rate      = 1 Mbps
MAC header      = 34 bytes
H_ACK size      = 14 bytes
SIFS            = 10 μs
Propagation     = 1 μs
```

## 三、已新增内容

- `Day11FixedPRMACConfig`：增加DATA与H_ACK序列化参数；
- `SegmentForwardingStatus`：`SCHEDULED / IN_PROGRESS / COMPLETED / BLOCKED`；
- `SegmentForwardingRecord`：记录段转发起止时间、跳数和状态；
- `Day11FixedPRMACMetrics`：记录DATA、H_ACK、字节数、完成段数和段转发时延；
- `FixedPRMACForwardingController`：在Day10控制器上增加连续转发；
- `schedule_reserved_forwarding()`：只允许ACTIVE预约发起转发；
- DATA严格沿`reserved_links`传播；
- 每跳DATA接收后返回H_ACK；
- 前一跳H_ACK接收后才允许启动下一跳DATA；
- K=2时只推进两个路径索引，不提前跨预约段；
- 预约剩余窗口必须覆盖完整DATA/H_ACK过程；
- 输出CSV轨迹和JSON汇总结果。

## 四、目录

```text
Day11_Fixed-PRMAC连续转发/
├─ code/
│  ├─ fixed_prmac_messages.py
│  ├─ fixed_prmac_forwarding.py
│  ├─ test_fixed_prmac_forwarding.py
│  ├─ main_fixed_prmac_forwarding.py
│  └─ run_day03_day11_regression.py
├─ docs/
│  ├─ Day11_任务计划.md
│  └─ Day11_连续转发设计.md
├─ figures/
├─ logs/
│  ├─ day11_tests.log
│  └─ main_fixed_prmac_forwarding.log
├─ results/
│  ├─ fixed_prmac_forwarding_trace.csv
│  └─ fixed_prmac_forwarding_summary.json
└─ README.md
```

## 五、专项测试

当前Day11共设置10项测试：

```text
test_day11_phy_defaults_match_existing_dcf_baseline
test_k2_active_reservation_forwards_two_data_and_two_h_ack
test_next_data_waits_for_previous_h_ack_reception
test_remaining_one_hop_uses_one_data_and_one_h_ack
test_long_route_stops_at_reserved_segment_endpoint
test_non_active_reservations_cannot_schedule_data
test_rejected_reservation_cannot_schedule_data
test_packet_must_match_reservation_identity_route_and_segment_start
test_forwarding_delay_and_byte_metrics_match_analytical_values
test_reservation_window_must_cover_complete_segment
```

沙盒实际结果：

```text
All Day11 Fixed-PRMAC continuous-forwarding tests passed.
```

## 六、主程序结果

主程序路径：

```text
0 → 1 → 2 → 3 → 4
```

固定K=2，因此本次只转发：

```text
0 → 1 → 2
```

实际结果：

```text
reservation_status        = ACTIVE
transfer_status           = COMPLETED
requested_k               = 2
effective_k               = 2
packet_current_node       = 2
packet_current_hop_index  = 2
packet_status             = FORWARDED
segment_started_at        = 0.000994000 s
segment_completed_at      = 0.009716000 s
segment_forwarding_delay  = 0.008722000 s
DATA frames               = 2
H_ACK frames              = 2
DATA bytes                = 2116
H_ACK bytes               = 28
```

一次2跳预约建立和段转发共使用：

```text
2 PR_REQ + 2 PR_ACK + 2 DATA + 2 H_ACK = 8 frames
```

总字节数：

```text
120 control bytes + 2116 DATA bytes + 28 H_ACK bytes = 2264 bytes
```

## 七、运行命令

Day11专项测试：

```powershell
python ".\daily\Day11_Fixed-PRMAC连续转发\code\test_fixed_prmac_forwarding.py"
```

Day03—Day11完整回归：

```powershell
python ".\daily\Day11_Fixed-PRMAC连续转发\code\run_day03_day11_regression.py" |
    Tee-Object ".\daily\Day11_Fixed-PRMAC连续转发\logs\day03_day11_regression.log"
```

Day11主程序：

```powershell
python ".\daily\Day11_Fixed-PRMAC连续转发\code\main_fixed_prmac_forwarding.py" |
    Tee-Object ".\daily\Day11_Fixed-PRMAC连续转发\logs\main_fixed_prmac_forwarding.log"
```

## 八、当前验证状态

已实际完成：

```text
Python语法检查：通过
Day11专项测试：通过
Day03—Day11完整回归：通过
Day11主程序：通过
结果CSV/JSON生成：通过
```

实际终端结果：

```text
All Day11 Fixed-PRMAC continuous-forwarding tests passed.
All Day03-Day11 regression tests passed.
```

说明Day11新增的预约段连续DATA/H_ACK转发没有破坏Day03—Day10已有功能，可以进入Day12。

## 九、Day11明确不做

- 预约失败后的退避与重试；
- PR_NACK后的重新预约；
- DATA/H_ACK丢失与超时；
- 跨多个预约段的完整端到端Fixed-PRMAC；
- DCF与Fixed-PRMAC公平性能预实验；
- Q-learning或RL策略；
- 动态路由、真实海面信道和隐藏终端。

## 十、下一步衔接

只有Day03—Day11完整回归和本地主程序均通过后，才进入：

```text
Day12：预约失败、退避与重试
```

Day13完成完整Fixed-PRMAC后仍必须执行既定止损预实验，未通过止损检查点不得进入RL。
