# Day17：RL-PRMAC协议集成

## 今日目标

在不改变 Day13 Fixed-PRMAC 生命周期、Day14 状态接口、Day15 六动作接口和 Day16 奖励/Q 更新机制的前提下，将节点本地 RL 决策接入 Python 离散事件协议控制器。

## 今日实现

- 新增 `RLPRMACProtocolController`，继承 Day13 端到端控制器；
- 在本地 FIFO 队首、初始 DIFS/退避前生成 Day14 状态并选择 Day15 动作；
- 每节点维护独立 `LocalNodeAgent`、Q 表、策略、学习器、历史和随机数；
- 动作 K 直接决定预约记录的跳数，不静默截断；
- 动作 CW 同时用于初始接入和预约重试序列起始窗口；
- PR_NACK 后保持原动作，并从动作 CW 执行 BEB；
- 成功在 RELEASE 完成后结算 Day16 奖励；
- 重试耗尽后结算失败奖励并执行终止更新；
- 非最终经验只在同一节点下一次本地决策时补齐 `s'`；
- 支持在显式仿真 episode 结束时清理仍待完成的节点本地经验；
- 新增协议接入审计快照、指标和 UTF-8 JSON 输出；
- 新增 Day17 专项测试、主验证和 Day03—Day17 全量回归入口。

## 文件说明

- `code/rl_prmac_protocol_controller.py`：Day17 协议接入核心实现；
- `code/test_rl_prmac_protocol_controller.py`：Day17 专项测试；
- `code/main_day17_protocol_integration_validation.py`：确定性主验证；
- `code/run_day03_day17_regression.py`：Day03—Day17 全量回归；
- `code/run_day17_checks.py`：一键完成专项测试、主验证、全量回归、日志和缓存清理；
- `docs/Day17_RL-PRMAC协议集成.md`：接口接入与边界论证；
- `logs/`：本机运行后生成测试日志；
- `results/`：本机运行后生成主验证 JSON。

## 本机验证目录

```text
C:\research-project-backup
```

运行：

```powershell
$RepoRoot = "C:\research-project-backup"
$Day17Dir = Join-Path $RepoRoot "daily\Day17_RL-PRMAC协议集成"
python "$Day17Dir\code\run_day17_checks.py"
```

只有出现以下结果后，Day17 才完成闭环：

```text
All Day17 protocol-controller tests passed.
Day17 main validation JSON is UTF-8 and parseable.
All Day03-Day17 regression tests passed.
Day17 validation closure completed.
```

## 今日边界

Day17 不执行完整 RL 训练、不做超参数搜索、不改固定路由、不引入中心控制，不使用未来信息，也不修改 Day14—Day16 冻结接口。

## 下一步

在 Day17 专项测试、主验证和 Day03—Day17 全量回归通过并合并到 GitHub `main` 前，不进入下一天任务。
