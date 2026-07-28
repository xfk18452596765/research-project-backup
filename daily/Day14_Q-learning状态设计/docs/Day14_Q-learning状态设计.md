# Day14：Q-learning状态设计

## 1. 任务边界

Day14 严格按照仓库原始计划，仅完成分布式表格 Q-learning 的状态设计。

本日不实现：

- `(K, CW)` 动作选择；
- ε-greedy 策略；
- 奖励函数；
- Q 值更新；
- 完整强化学习训练；
- 集中式全局控制。

## 2. 决策主体与决策时刻

决策主体仍为每个路径预约段的起始节点。

决策时刻为：

```text
本地 FIFO 队首准备发起一个新预约段之前
```

状态只能来自该节点当前可获得或通过本地历史统计得到的信息。

## 3. 原始本地观测

```text
LocalObservation = {
    node_id,
    packet_id,
    flow_id,
    observed_at,
    remaining_hops,
    local_queue_length,
    queue_limit,
    priority,
    last_reservation_succeeded,
    recent_mean_retries,
    channel_busy_ratio
}
```

其中：

- `remaining_hops`：数据包沿固定路由尚需转发的跳数；
- `local_queue_length`：包含当前活动队首的本地 FIFO 长度；
- `last_reservation_succeeded`：本节点最近一次预约结果；
- `recent_mean_retries`：本节点最近预约段的平均重试次数；
- `priority`：数据包优先级标签；
- `channel_busy_ratio`：本地 CCA 忙占比。当前模型无法提供时必须为 `None`，编码成 `UNKNOWN`。

## 4. 离散状态

```text
s = (
    remaining_hops_bin,
    queue_length_bin,
    last_reservation_outcome,
    retry_intensity_bin,
    priority_bin,
    channel_busy_bin
)
```

### 4.1 剩余跳数

| 原始值 | 分箱 |
|---|---:|
| 1 | 0 |
| 2 | 1 |
| 3—4 | 2 |
| ≥5 | 3 |

### 4.2 本地队列长度

| 原始值 | 分箱 |
|---|---:|
| 1 | 0 |
| 2—3 | 1 |
| 4—7 | 2 |
| ≥8 | 3 |

### 4.3 最近预约结果

| 结果 | 分箱 |
|---|---:|
| 无历史 | 0 |
| 成功 | 1 |
| 失败 | 2 |

### 4.4 最近重试强度

| 平均重试数 | 分箱 |
|---|---:|
| 0 | 0 |
| `(0,1]` | 1 |
| `(1,2]` | 2 |
| `>2` | 3 |

### 4.5 优先级

| 优先级 | 分箱 |
|---|---:|
| 普通业务 `priority=0` | 0 |
| 高优先级 `priority>0` | 1 |

### 4.6 本地信道忙占比

默认阈值：

| 忙占比 | 分箱 |
|---|---:|
| 当前不可测 | 0：UNKNOWN |
| `[0,0.25)` | 1：LOW |
| `[0.25,0.60)` | 2：MEDIUM |
| `[0.60,1]` | 3：HIGH |

`UNKNOWN` 与 `LOW` 必须区分，避免把缺失观测错误解释为空闲信道。

## 5. 状态空间规模

```text
4 × 4 × 3 × 4 × 2 × 4 = 1536
```

该规模适合后续表格 Q-learning 的初始实现。它是状态键上界，不表示每个节点一定会访问全部状态。

## 6. 分布式可实现性

状态不包含：

- 全网队列总长度；
- 所有节点状态；
- 全局完整信道信息；
- 未来端到端时延；
- 中心控制器决策结果。

`node_id`、`packet_id` 和 `flow_id` 用于追踪与日志，不进入离散 Q 状态元组，避免状态空间被标识符无意义扩大。

## 7. 与后续日期的边界

- Day15：联合动作 `(K,CW)`、动作掩码、动作索引和策略；
- Day16：奖励函数与 Q 值更新；
- 完整 RL 训练前：继续执行扩大 Python 现实性实验和最小 ns-3 Fixed-PRMAC 验证。

## 8. 验收条件

- 状态编码边界测试通过；
- `channel_busy_ratio=None` 显式编码为 `UNKNOWN`；
- 状态编码确定且可哈希；
- 状态空间为 `1536`；
- 状态字段不存在全局或未来信息；
- 主验证输出显示：
  - `action_policy_implemented=false`；
  - `reward_update_implemented=false`；
  - `training_started=false`；
  - `central_controller_used=false`。
