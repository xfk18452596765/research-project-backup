# Day09：Fixed-PRMAC报文与预约

## 一、任务定位

Day09在已经完成验证的多跳DCF基线上，正式进入Fixed-PRMAC阶段。本日只实现Fixed-PRMAC的报文模型和最小成功预约流程，验证固定预约长度、`PR_REQ`前向传播、`PR_ACK`反向确认、预约激活、释放和过期等控制逻辑。

本日不实现预约冲突拒绝、预约失败重试、预约段连续DATA转发或强化学习。

## 二、今日目标

完成以下最小成功预约流程：

```text
预约段起始节点发起预约
→ PR_REQ沿固定路径前向传播
→ 预约段末端生成PR_ACK
→ PR_ACK沿原路径反向传播
→ 发起节点收到PR_ACK
→ 预约状态进入ACTIVE
```

固定参数：

```text
K_fixed = 2
CWmin_fixed = 15
```

当剩余路径不足2跳时：

```text
K_effective = min(K_fixed, remaining_hops)
```

## 三、已完成内容

- 定义Fixed-PRMAC控制报文类型；
- 实现`PR_REQ`前向预约请求；
- 实现`PR_ACK`反向预约确认；
- 预留`PR_NACK`、`DATA`和`H_ACK`；
- 实现`RELEASE`预约释放；
- 冻结`K_fixed=2`和`CWmin_fixed=15`；
- 实现有效预约长度截断；
- 实现控制帧逐跳传播；
- 实现预约状态管理与自动过期；
- 实现固定路由与邻接链路校验；
- 实现控制帧数量、控制字节和建立时延统计；
- 完成Day09自动测试；
- 完成Day03—Day09完整回归；
- 完成主程序和结果文件输出。

## 四、报文与状态

| 报文 | Day09状态 | 作用 |
|---|---|---|
| `PR_REQ` | 已实现并使用 | 沿预约段前向请求预约 |
| `PR_ACK` | 已实现并使用 | 沿原路径反向确认成功 |
| `RELEASE` | 已实现并测试 | 提前释放活动预约 |
| `PR_NACK` | 仅定义 | Day10冲突拒绝使用 |
| `DATA` | 仅定义 | Day11预约段连续转发使用 |
| `H_ACK` | 仅定义 | Day11逐跳确认使用 |

预约状态包括：

```text
PENDING
ACTIVE
RELEASED
EXPIRED
REJECTED
```

Day09实际完成：

```text
PENDING → ACTIVE
ACTIVE → RELEASED
ACTIVE → EXPIRED
```

`REJECTED`将在Day10冲突模型中使用。

## 五、目录说明

```text
Day09_Fixed-PRMAC报文与预约/
├─ code/
│  ├─ fixed_prmac_messages.py
│  ├─ fixed_prmac_reservation.py
│  ├─ main_fixed_prmac_reservation.py
│  ├─ test_fixed_prmac_reservation.py
│  └─ run_day03_day09_regression.py
├─ docs/
│  ├─ Day09_任务计划.md
│  └─ Day09_Fixed-PRMAC报文与预约设计.md
├─ figures/
├─ logs/
│  ├─ day03_day09_regression.log
│  └─ main_fixed_prmac_reservation.log
├─ results/
│  ├─ fixed_prmac_reservation_trace.csv
│  └─ fixed_prmac_reservation_summary.json
└─ README.md
```

## 六、运行方法

Day09自动测试：

```powershell
python ".\daily\Day09_Fixed-PRMAC报文与预约\code\test_fixed_prmac_reservation.py"
```

Day03—Day09完整回归：

```powershell
python ".\daily\Day09_Fixed-PRMAC报文与预约\code\run_day03_day09_regression.py" |
    Tee-Object ".\daily\Day09_Fixed-PRMAC报文与预约\logs\day03_day09_regression.log"
```

Day09主程序：

```powershell
python ".\daily\Day09_Fixed-PRMAC报文与预约\code\main_fixed_prmac_reservation.py" |
    Tee-Object ".\daily\Day09_Fixed-PRMAC报文与预约\logs\main_fixed_prmac_reservation.log"
```

## 七、自动测试结果

Day09共完成8项测试：

```text
[PASS] test_fixed_baseline_parameters_are_frozen
[PASS] test_k2_pr_req_and_reverse_pr_ack_activate_reservation
[PASS] test_remaining_one_hop_truncates_effective_k
[PASS] test_control_frames_preserve_required_fields_and_overhead
[PASS] test_release_propagates_and_clears_active_record
[PASS] test_active_reservation_expires_at_duration_boundary
[PASS] test_invalid_route_edge_is_rejected_before_events_are_scheduled
[PASS] test_day09_intentionally_has_no_conflict_rejection
```

最终结果：

```text
All Day09 Fixed-PRMAC message and reservation tests passed.
```

这些测试验证了固定参数、K=2成功预约、剩余1跳自动截断、控制帧字段与开销、预约释放、自动过期、非法路由拒绝，以及Day09尚未提前实现冲突拒绝。

## 八、完整回归结果

Day03—Day09全部测试通过：

```text
All Day03-Day09 regression tests passed.
```

说明Day09新增功能没有破坏此前的离散事件框架、DCF、信道忙处理、碰撞重传、多跳转发、指标采集和DCF验证模块。

Day04—Day07旧日志中仍可能出现`GENERIC`，这是旧调度封装的历史输出，不影响测试结果。Day08和Day09新增事件均使用明确事件名称。

## 九、主程序场景

固定路径：

```text
0 → 1 → 2 → 3
```

节点0从路径索引0发起固定2跳预约：

```text
requested_k = 2
effective_k = 2
reserved_links = 0→1, 1→2
initiator = 0
endpoint = 2
```

## 十、实际预约时序

```text
0.000000000s  RESERVATION_START
0.000000000s  PR_REQ_TX       0→1
0.000289000s  PR_REQ_RX       node=1
0.000299000s  PR_REQ_TX       1→2
0.000588000s  PR_REQ_RX       node=2
0.000598000s  PR_ACK_TX       2→1
0.000791000s  PR_ACK_RX       node=1
0.000801000s  PR_ACK_TX       1→0
0.000994000s  PR_ACK_RX       node=0
0.000994000s  RESERVATION_ACTIVE
```

完整事件链：

```text
RESERVATION_START
→ PR_REQ_TX
→ PR_REQ_RX
→ PR_REQ_TX
→ PR_REQ_RX
→ PR_ACK_TX
→ PR_ACK_RX
→ PR_ACK_TX
→ PR_ACK_RX
→ RESERVATION_ACTIVE
```

## 十一、关键实验结果

```text
reservation_id          = demo-flow:packet-900:segment-0:request-1
status                  = ACTIVE
requested_k             = 2
effective_k             = 2
reserved_links          = 0->1, 1->2
initiator               = 0
endpoint                = 2
activated_at            = 0.000994000秒
expires_at              = 0.020994000秒
reservation_requests    = 1
successful_reservations = 1
released_reservations   = 0
expired_reservations    = 0
active_reservations     = 1
control_frames_sent     = 4
control_bytes_sent      = 120
average_setup_delay     = 0.000994秒
```

预约建立时间：

```text
0.000994秒 = 0.994毫秒
```

一次2跳预约使用：

```text
2个PR_REQ + 2个PR_ACK = 4个控制帧
```

控制开销：

```text
2 × 36字节 + 2 × 24字节 = 120字节
```

预约持续时间为0.020秒，因此：

```text
expires_at
= activated_at + duration
= 0.000994 + 0.020
= 0.020994秒
```

## 十二、结果文件

```text
results/fixed_prmac_reservation_trace.csv
results/fixed_prmac_reservation_summary.json
```

`fixed_prmac_reservation_trace.csv`记录事件时间、节点、事件类型、数据包、控制帧、发送者、接收者和链路索引。

`fixed_prmac_reservation_summary.json`记录预约状态、预约链路、激活与过期时间、控制帧数量、控制字节和平均建立时延。

## 十三、结果解释

Day09证明Fixed-PRMAC最小预约控制链路能够正确工作：

```text
预约段起始节点
→ PR_REQ前向传播
→ 预约段末端
→ PR_ACK反向传播
→ 发起节点激活预约
```

`K_fixed=2`已经真正进入报文与状态管理逻辑，而不只是一个静态配置值。

当前`ACTIVE`仅表示控制平面成功建立预约。本日尚未在预约段内连续发送DATA，因此不能用Day09结果比较Fixed-PRMAC与DCF的端到端性能。

## 十四、当前实现边界

Day09尚未实现：

- 两个预约请求之间的冲突检测；
- 链路、节点和时间窗口重叠判断；
- `PR_NACK`冲突拒绝；
- 预约失败后的退避与重试；
- Fixed-PRMAC控制帧的DCF竞争接入；
- 预约段内连续DATA转发；
- `H_ACK`逐跳确认；
- 跨预约段衔接；
- 完整Fixed-PRMAC端到端传输；
- 多业务流性能对比；
- Q-learning；
- 动态路由；
- 真实海面传播模型。

Day09中的`schedule_reservation()`表示发起节点已经取得发送`PR_REQ`的机会。虽然`CWmin_fixed=15`已经冻结，但DCF接入和预约控制尚未完整耦合。

## 十五、今日结论

Day09已经完成：

```text
固定K=2参数
+ PR_REQ前向传播
+ PR_ACK反向确认
+ ACTIVE预约建立
+ RELEASE释放
+ 自动过期
+ 控制开销统计
+ 建立时延统计
```

Day09自动测试、Day03—Day09完整回归和主程序均已成功运行，结果文件已经生成。

## 十六、明日衔接

Day10进入Fixed-PRMAC预约冲突模型，重点实现：

```text
已有活动预约
+ 新预约请求
→ 检查链路、节点和时间窗口是否重叠
→ 无冲突：继续PR_REQ/PR_ACK
→ 有冲突：生成PR_NACK
→ 发起节点进入REJECTED或失败状态
```

Day10不提前实现预约失败重试、预约段连续DATA转发或Q-learning。
