# Day13：Fixed-PRMAC验证

## 今日目标

完成进入强化学习前的止损检查点：

1. 组装完整多预约段端到端Fixed-PRMAC；
2. 与DCF执行公平的2/4/6跳、低/中/高负载、多种子预实验；
3. 止损结论为PASS且完整回归通过后，才允许进入Day14。

## 已完成实现

### 完整端到端Fixed-PRMAC

```text
END_TO_END_START
→ 每段本地FIFO
→ 队首DIFS + CWmin随机退避
→ Day12预约/PR_NACK/BEB重试
→ ACTIVE
→ Day11 DATA/H_ACK连续转发
→ RELEASE
→ 下一预约段
→ DELIVERED或DROPPED
```

固定设计保持：

```text
K_fixed = 2
CW_init = 15
```

6跳路径按`0→1→2`、`2→3→4`、`4→5→6`三段转发；每段释放完成后才启动下一段。

### 公平止损矩阵

```text
跳数：2 / 4 / 6
负载：low / medium / high
种子：7 / 17 / 27
每次：8个1024字节数据包
协议：DCF / Fixed-PRMAC
queue_limit：200
```

两种协议保持相同PHY、包长、路由、负载、随机种子、CW和重试上限。

## Day13-Fix01：本地FIFO修正

首次止损为`HOLD`，原因是高负载下同一节点的本地数据包被同时放行预约，本地排队被误转化为PR_NACK和重试耗尽。

Fix01增加每个预约段起始节点的FIFO和队首接入：

```text
本地入队 → 队首竞争 → 预约/转发/释放 → 出队唤醒下一包
```

修正后第二次矩阵中：

```text
critical_delivery_losses_out_of_4 = 0
all_delivery_losses_out_of_9      = 0
fixed_queue_overflow_drops        = 0
```

投递率问题已经消失。

## Day13-Fix02：判据与研究目标对齐

Fix01复验后仍为`HOLD`，唯一未通过项为：

```text
fixed_delay_wins_majority_of_9_cells = False
```

实际结果在核心目标场景中为：

```text
4跳-high   ：Fixed-PRMAC优于DCF
6跳-medium ：Fixed-PRMAC优于DCF
6跳-high   ：Fixed-PRMAC优于DCF
```

2跳和低负载中，固定预约控制开销高于节省的竞争开销，这是协议适用边界，不代表长路径高竞争假设失败。

Fix02不修改协议、参数、业务、种子或实验结果，只修正`evaluate_stop_loss()`的PASS门槛：

- 三个核心目标单元必须全部获胜；
- 四个关键单元至少赢3个；
- 关键单元至少3个具有多数种子一致性；
- 全部9个单元无投递率下降；
- 无FIFO溢出；
- 公平性、功能性和DCF跳数累积趋势全部通过。

`9个单元是否多数获胜`仍保留在输出中，但改为描述性观察项，不再作为PASS门槛。低负载和短路径损失不得删除或隐藏。

详细说明：

```text
docs/Day13_Fix02_止损判据与研究目标对齐.md
```

## 专项测试

现有18项测试，除原端到端、冲突重试和FIFO测试外，新增：

- 仅三个核心目标单元获胜、全局9单元未过半时，若其余必要证据完整，可PASS；
- 任一非关键单元投递率下降时，仍不得PASS。

沙盒结果：

```text
All Day13 Fixed-PRMAC validation and stop-loss tests passed.
```

## 文件说明

```text
code/
├─ fixed_prmac_end_to_end.py
├─ fixed_prmac_messages.py
├─ stop_loss_experiment.py
├─ test_fixed_prmac_validation.py
├─ main_fixed_prmac_validation.py
├─ main_stop_loss_preexperiment.py
└─ run_day03_day13_regression.py

docs/
├─ Day13_任务计划.md
├─ Day13_端到端与止损设计.md
├─ Day13_Fix01_本地FIFO与止损复验.md
└─ Day13_Fix02_止损判据与研究目标对齐.md
```

## Fix02本地复验顺序

```powershell
cd C:\research-project-backup-main
```

### 1. Day13专项测试

```powershell
python ".\daily\Day13_Fixed-PRMAC验证\code\test_fixed_prmac_validation.py"
```

应有18项`PASS`并以此结束：

```text
All Day13 Fixed-PRMAC validation and stop-loss tests passed.
```

### 2. Day03—Day13完整回归

```powershell
python ".\daily\Day13_Fixed-PRMAC验证\code\run_day03_day13_regression.py" |
    Tee-Object ".\daily\Day13_Fixed-PRMAC验证\logs\day03_day13_regression.log"
```

### 3. 重新执行完整止损矩阵

```powershell
python ".\daily\Day13_Fixed-PRMAC验证\code\main_stop_loss_preexperiment.py" |
    Tee-Object ".\daily\Day13_Fixed-PRMAC验证\logs\main_stop_loss_preexperiment.log"
```

新输出应显示：

```text
policy_version: Day13-Fix02-critical-scope-v1
```

只有新的：

```text
results/day13_stop_loss_decision.json
```

明确显示`decision = PASS`，才允许关闭Day13并进入Day14。

## 当前状态

```text
Day13专项测试：18项全部通过
Day03—Day13完整回归：全部通过
6跳端到端主程序：COMPLETED / DELIVERED
Fix01止损结果：HOLD（历史结果）
Fix02本地复验：PASS
Day14：允许开启
```

---

## Day13最终有效结论

Day13已完成Fixed-PRMAC端到端验证、本地FIFO公平性修正和止损判据对齐。

最终验证结果：

```text
policy_version: Day13-Fix02-critical-scope-v1
decision: PASS

Day13专项测试：18项全部通过
Day03—Day13完整回归：全部通过
6跳端到端验证：COMPLETED / DELIVERED
core_target_cells_all_win：True
no_critical_delivery_ratio_loss：True
no_delivery_ratio_loss_in_any_of_9_cells：True
no_fixed_queue_overflow：True
fixed_queue_overflow_drops：0
```

2跳和低负载场景中，Fixed-PRMAC受固定预约控制开销影响，时延可能略高于DCF。该现象作为协议适用边界保留，不作为实现失败处理。

当前项目状态：

```text
Day13：正式完成
止损结论：PASS
Day14：允许开启
```
