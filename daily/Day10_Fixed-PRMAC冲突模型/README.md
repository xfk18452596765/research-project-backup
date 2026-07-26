# Day10：Fixed-PRMAC冲突模型

## 一、任务定位

Day10严格继承Day09的Fixed-PRMAC最小成功预约控制平面，只实现活动预约与新请求之间的链路、节点和时间窗口冲突检测，以及`PR_NACK`反向拒绝流程。

本日不实现预约失败后的退避重试、预约段连续DATA转发、H_ACK、完整端到端Fixed-PRMAC或强化学习。

## 二、继承的固定设定

```text
K_fixed = 2
CWmin_fixed = 15
K_effective = min(K_fixed, remaining_hops)
```

技术路线保持：

```text
DCF → Fixed-PRMAC → RL-PRMAC
```

当前仍处于Fixed-PRMAC阶段，尚未进入RL。

## 三、Day10新增内容

- 新增`REJECTED`预约状态；
- 保留Day09消息与预约记录公共字段；
- 新增`PR_NACK`序列化和开销统计；
- 新增半开时间窗口重叠判断；
- 新增同一物理链路双向互斥规则；
- 新增共享端点节点互斥规则；
- 在`PR_REQ_RX`处逐跳进行本地冲突检查；
- 冲突节点沿已通过路径反向发送`PR_NACK`；
- 发起节点收到`PR_NACK`后进入`REJECTED`；
- 被拒绝请求不会进入活动预约表；
- 过期或释放后资源可再次预约；
- 新增冲突、拒绝和PR_NACK指标。

## 四、冲突规则

仅`ACTIVE`预约占用资源。

时间窗口采用：

```text
[start, end)
```

重叠条件：

```text
start_a < end_b and start_b < end_a
```

资源判定顺序：

```text
同一无向物理链路 → LINK_CONFLICT
否则共享端点节点 → NODE_CONFLICT
否则 → 无冲突
```

该规则是Day10用于验证预约冲突控制机制的保守模型，不扩展为中心式全网调度。

## 五、目录

```text
Day10_Fixed-PRMAC冲突模型/
├─ code/
│  ├─ fixed_prmac_messages.py
│  ├─ fixed_prmac_conflict.py
│  ├─ main_fixed_prmac_conflict.py
│  ├─ test_fixed_prmac_conflict.py
│  └─ run_day03_day10_regression.py
├─ docs/
│  └─ Day10_冲突模型设计.md
├─ figures/
├─ logs/
│  ├─ day10_tests.log
│  └─ main_fixed_prmac_conflict.log
├─ results/
│  ├─ fixed_prmac_conflict_trace.csv
│  └─ fixed_prmac_conflict_summary.json
└─ README.md
```

## 六、运行方法

Day10自动测试：

```powershell
python ".\daily\Day10_Fixed-PRMAC冲突模型\code\test_fixed_prmac_conflict.py"
```

Day03—Day10完整回归：

```powershell
python ".\daily\Day10_Fixed-PRMAC冲突模型\code\run_day03_day10_regression.py" |
    Tee-Object ".\daily\Day10_Fixed-PRMAC冲突模型\logs\day03_day10_regression.log"
```

Day10主程序：

```powershell
python ".\daily\Day10_Fixed-PRMAC冲突模型\code\main_fixed_prmac_conflict.py" |
    Tee-Object ".\daily\Day10_Fixed-PRMAC冲突模型\logs\main_fixed_prmac_conflict.log"
```

## 七、已实际运行的Day10测试

沙盒中已运行8个Day10自动测试：

```text
[PASS] test_disjoint_overlapping_time_reservations_can_coexist
[PASS] test_same_link_overlap_is_rejected
[PASS] test_shared_node_overlap_is_rejected_without_same_link
[PASS] test_non_overlapping_time_window_is_accepted_and_old_record_expires
[PASS] test_pr_nack_returns_along_reverse_partial_path
[PASS] test_rejected_request_does_not_pollute_existing_active_reservation
[PASS] test_release_frees_resources_for_new_reservation
[PASS] test_reverse_direction_uses_same_physical_link_resource

All Day10 Fixed-PRMAC conflict tests passed.
```

同时已通过Python语法编译检查。

## 八、主程序实际结果

主程序先建立活动预约：

```text
2 → 3 → 4
```

随后发起新预约：

```text
0 → 1 → 2
```

新请求在第二跳`1→2`到达节点2时，与已有预约共享节点2，触发：

```text
RESERVATION_CONFLICT
→ PR_NACK_TX 2→1
→ PR_NACK_RX node=1
→ PR_NACK_TX 1→0
→ PR_NACK_RX node=0
→ RESERVATION_REJECTED
```

结果：

```text
existing_status        = ACTIVE
rejected_status        = REJECTED
reservation_requests   = 2
successful_reservations= 1
rejected_reservations  = 1
node_conflicts         = 1
link_conflicts         = 0
pr_nack_frames_sent    = 2
control_frames_sent    = 8
control_bytes_sent     = 240
```

拒绝完成时刻：

```text
rejected_at = 0.001988秒
```

已有活动预约保持不变，被拒绝请求未进入`active_records`。

## 九、回归状态说明

GitHub `main`上的Day09接口已通过连接器逐文件核对。由于当前沙盒不能直接解析GitHub域名，无法克隆完整仓库，因此本次没有在沙盒中真实运行Day03—Day10全量回归，不能把全回归写成“已通过”。

`run_day03_day10_regression.py`已严格继承Day09回归列表并追加Day10测试。将本目录放入本地项目`daily/`后，应在本地运行该脚本；若任一旧测试失败，应定位具体接口并做最小修复，不得跳到Day11。

## 十、接口兼容与导入顺序修复

Day09代码中的预约状态枚举实际保留了`FAILED`，而Day09 README和阶段摘要均要求Day10使用`REJECTED`。Day10没有修改Day09稳定文件，而是在Day10目录提供兼容消息模型。

在Windows中直接运行Day10脚本时，脚本所在目录会预先出现在`sys.path`。旧版代码只在路径“不存在”时才插入路径，结果Day09目录被插入到Day10目录之前，错误加载了Day09的`fixed_prmac_messages.py`，从而触发：

```text
AttributeError: type object 'ReservationStatus' has no attribute 'REJECTED'
```

修正版会先移除三个相关路径，再按以下确定顺序重新放到`sys.path`首部：

```text
Day10 code
→ Day09 code
→ Day03 code
```

因此Day09控制器会复用Day10兼容消息模型，同时不需要修改Day09稳定文件。

```text
保留Day09全部公共字段
+ REJECTED
+ rejected_at
```

Day10运行时让Day09预约控制器加载该兼容模型，从而实现最小扩展。

## 十一、当前边界

Day10尚未实现：

- 预约失败退避与重试；
- PR_REQ竞争接入与`CWmin_fixed`完整耦合；
- 预约段连续DATA转发；
- H_ACK；
- 完整端到端Fixed-PRMAC；
- DCF与Fixed-PRMAC公平性能比较；
- Q-learning或其他RL内容；
- 动态路由；
- 真实海面传播；
- 隐藏终端和距离相关空间复用。

因此，Day10不能用于宣称Fixed-PRMAC具有端到端性能优势。

## 十二、下一检查点

当前只应先完成：

```text
本地Day03—Day10完整回归
```

只有回归通过并检查日志、结果文件后，才进入既定Day11“预约段连续DATA转发与H_ACK”。止损检查点仍固定在Day13完整Fixed-PRMAC后的公平预实验，不能提前进入RL。
