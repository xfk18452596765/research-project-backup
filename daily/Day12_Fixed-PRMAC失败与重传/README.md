# Day12：Fixed-PRMAC失败与重传

## 一、任务定位

Day12严格继承：

```text
Day09：PR_REQ/PR_ACK成功预约
Day10：冲突检测与PR_NACK
Day11：ACTIVE预约段DATA/H_ACK连续转发
```

本日只补齐：

```text
PR_NACK
→ REJECTED
→ DIFS + 二进制指数随机退避
→ 创建新的预约尝试
→ ACTIVE或最终FAILED
```

技术路线保持：

```text
DCF → Fixed-PRMAC → RL-PRMAC
```

本日仍处于Fixed-PRMAC阶段，不进行性能对比和强化学习。

## 二、固定参数

预约参数：

```text
K_fixed     = 2
CWmin       = 15
CWmax       = 1023
retry_limit = 7
```

时隙参数与现有DCF基线对齐：

```text
slot_time   = 20 μs
DIFS        = 50 μs
random_seed = 7
```

第`r`次重试使用：

```text
CW_r = min((CWmin + 1) × 2^r - 1, CWmax)
B_r  ~ UniformInteger[0, CW_r]
T_r  = DIFS + B_r × slot_time
```

默认CW序列：

```text
15 → 31 → 63 → 127 → 255 → 511 → 1023
```

## 三、已新增内容

- `Day12FixedPRMACConfig`：加入DIFS、时隙、CWmax、重试上限和随机种子；
- `ReservationRetryStatus`：重试序列状态；
- `ReservationRetryAttempt`：记录单次预约尝试；
- `ReservationRetryRecord`：连接同一数据包段的全部尝试；
- `Day12ReservationTable`：支持最终`REJECTED → FAILED`；
- `Day12FixedPRMACMetrics`：记录重试次数、退避槽、成功率和完成时延；
- `FixedPRMACRetryController`：实现PR_NACK后的自动退避与重新预约；
- 每次重试生成新的`reservation_id`；
- 旧的REJECTED记录保留，不被覆盖；
- 达到重试上限后，最后一次预约进入`FAILED`，数据包进入`DROPPED`；
- 重试成功后的ACTIVE预约可以继续调用Day11 DATA/H_ACK转发；
- 输出完整CSV轨迹和JSON汇总。

## 四、目录

```text
Day12_Fixed-PRMAC失败与重传/
├─ code/
│  ├─ fixed_prmac_messages.py
│  ├─ fixed_prmac_retry.py
│  ├─ test_fixed_prmac_retry.py
│  ├─ main_fixed_prmac_retry.py
│  └─ run_day03_day12_regression.py
├─ docs/
│  ├─ Day12_任务计划.md
│  └─ Day12_失败与重传设计.md
├─ figures/
├─ logs/
│  ├─ day12_tests.log
│  └─ main_fixed_prmac_retry.log
├─ results/
│  ├─ fixed_prmac_retry_trace.csv
│  └─ fixed_prmac_retry_summary.json
└─ README.md
```

## 五、专项测试

Day12共设置11项测试：

```text
test_day12_retry_defaults_match_existing_dcf_baseline
test_no_conflict_succeeds_on_first_attempt_without_backoff
test_pr_nack_triggers_seeded_beb_and_first_retry_succeeds_after_release
test_each_retry_uses_a_fresh_reservation_id_and_preserves_history
test_retry_event_order_is_rejection_then_backoff_then_new_attempt
test_persistent_conflict_exhausts_limit_and_marks_final_attempt_failed
test_binary_exponential_window_growth_is_capped
test_retry_random_seed_is_reproducible
test_plain_day10_rejection_does_not_enable_automatic_retry
test_successful_retry_can_use_inherited_day11_data_h_ack_forwarding
test_retry_metrics_include_all_attempts_backoff_and_control_overhead
```

沙盒实际结果：

```text
All Day12 Fixed-PRMAC failure-and-retry tests passed.
```

同时重新运行了Day10、Day11专项测试，均通过。

## 六、主程序结果

已有预约：

```text
2 → 3 → 4
```

候选预约：

```text
0 → 1 → 2
```

初始候选在节点2被拒绝：

```text
attempt 1
CW = 15
status = REJECTED
```

固定种子7的第一次重试：

```text
attempt 2
CW = 31
backoff_slots = 20
backoff_delay = 0.000450000 s
status = ACTIVE
```

重试序列：

```text
retry_status          = SUCCEEDED
total_attempts        = 2
retries_used          = 1
retry_completion_delay= 0.002438000 s
```

成功后继承Day11完成两跳转发：

```text
DATA 0→1 → H_ACK 1→0
DATA 1→2 → H_ACK 2→1
```

转发结果：

```text
transfer_status          = COMPLETED
packet_current_node      = 2
packet_current_hop_index = 2
segment_forwarding_delay = 0.008722000 s
```

关键统计：

```text
reservation_requests          = 3
successful_reservations       = 2
rejected_reservations         = 1
released_reservations         = 1
reservation_retries_scheduled = 1
retry_successes               = 1
retry_exhausted_failures      = 0
total_retry_backoff_slots     = 20
control_frames_sent           = 14
control_bytes_sent            = 400
DATA frames                   = 2
H_ACK frames                  = 2
total_frames_sent             = 18
total_bytes_sent              = 2544
```

## 七、运行命令

Day12专项测试：

```powershell
python ".\daily\Day12_Fixed-PRMAC失败与重传\code\test_fixed_prmac_retry.py"
```

Day03—Day12完整回归：

```powershell
python ".\daily\Day12_Fixed-PRMAC失败与重传\code\run_day03_day12_regression.py" |
    Tee-Object ".\daily\Day12_Fixed-PRMAC失败与重传\logs\day03_day12_regression.log"
```

Day12主程序：

```powershell
python ".\daily\Day12_Fixed-PRMAC失败与重传\code\main_fixed_prmac_retry.py" |
    Tee-Object ".\daily\Day12_Fixed-PRMAC失败与重传\logs\main_fixed_prmac_retry.log"
```

## 八、当前验证状态

已实际完成：

```text
Python语法检查：通过
Day12专项测试：通过
Day10专项回归：通过
Day11专项回归：通过
Day03—Day12完整回归：通过
Day12主程序：通过
结果CSV/JSON生成：通过
```

完整回归实际输出：

```text
All Day12 Fixed-PRMAC failure-and-retry tests passed.
All Day03-Day12 regression tests passed.
```

当前可以进入Day13。

## 九、Day12明确不做

- 初始PR_REQ与完整DCF共享信道竞争耦合；
- 退避期间的信道忙冻结和恢复；
- DATA/H_ACK丢失、超时和重传；
- 跨多个预约段的端到端Fixed-PRMAC；
- DCF与Fixed-PRMAC公平性能结论；
- Q-learning、RL状态、动作和奖励；
- 动态路由、真实海面信道、隐藏终端或空间复用。

Day12的退避用于验证PR_NACK后的失败恢复闭环。完整公平接入与端到端集成必须在Day13完成。

## 十、下一步衔接

只有Day03—Day12完整回归和本地主程序均通过后，才进入：

```text
Day13_Fixed-PRMAC验证
```

Day13必须完成：

```text
完整最小Fixed-PRMAC
+ DCF公平预实验
+ 2/4/6跳
+ 低/中/高负载
+ 多随机种子
+ 止损检查点
```

若Fixed-PRMAC不能在重点场景稳定优于DCF，必须停止RL阶段并重新评估协议机制。
