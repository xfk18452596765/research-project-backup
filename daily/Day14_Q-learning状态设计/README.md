# Day14：Q-learning状态设计

## 今日目标

面向分布式 RL-PRMAC，在每个预约段起始节点的决策时刻，定义仅依赖本地可观测信息的离散状态，并验证状态编码边界与状态空间规模。

## 今日完成内容

- 定义本地原始观测 `LocalObservation`；
- 定义可作为表格 Q-learning 键的离散状态 `RLState`；
- 定义确定性状态编码器 `StateEncoder`；
- 状态包含：
  - 剩余跳数；
  - 本地 FIFO 队列长度；
  - 最近预约成功/失败；
  - 最近重试强度；
  - 业务优先级；
  - 本地信道忙占比；
- 当当前 Python 信道模型尚不能提供真实忙占比时，使用显式 `UNKNOWN`；
- 验证最大状态空间为 `1536`；
- 验证状态中不包含全网队列、全网信道、未来时延或中心控制器信息。

## 文件说明

- `code/rl_prmac_state.py`：Day14 状态模型与状态编码；
- `code/test_rl_prmac_state.py`：Day14 状态设计测试；
- `code/main_day14_state_validation.py`：状态编码示例；
- `docs/Day14_Q-learning状态设计.md`：详细设计说明；
- `logs`：运行日志；
- `results`：验证输出；
- `figures`：预留图表目录。

## 今日结论

Day14 只完成状态设计，不实现 `(K, CW)` 动作策略、不计算奖励、不更新 Q 表、不启动训练，也不使用中心控制器。

## 明日衔接

Day15 在 Day14 状态键的基础上设计 `(K, CW)` 联合动作集合、合法动作掩码和分布式动作选择策略。
