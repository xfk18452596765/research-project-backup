# Day13-Fix01：Fixed-PRMAC本地FIFO与止损复验

## 1. 修正原因

首次止损结果为 `HOLD`。Fixed-PRMAC在4跳/6跳中高负载下表现出明显时延潜力，但高负载投递率低于DCF。检查发现，周期Fixed-PRMAC此前让同一节点上的多个数据包同时发起预约，把本应属于本地排队的压力误记为预约冲突、PR_NACK和重试耗尽。

## 2. 最小修正

本次不修改K、CW、PHY、负载、种子或重试上限，只在每个预约段起始节点增加FIFO：

```text
SEGMENT_QUEUE_ENQUEUE
→ 只有队首进入SEGMENT_ACCESS_BACKOFF
→ 预约/重试
→ DATA/H_ACK
→ RELEASE完成或重试耗尽
→ 出队并唤醒下一队首
```

队列包含正在服务的队首，`queue_limit=200`，与DCF节点队列一致。

本地等待不会生成PR_NACK，也不会增加预约重试次数。只有真实资源冲突才使用Day12的PR_NACK+BEB流程。

## 3. 新增指标

- `segment_queue_entries`
- `queue_overflow_drops`
- `maximum_segment_queue_length`
- `total_segment_queue_delay`
- `average_segment_queue_delay`
- `maximum_segment_queue_delay`
- `initial_access_attempts`

排队等待从段进入本地FIFO起，统计到该段成为队首并开始DIFS/初始退避为止；该时间自然计入端到端时延。

## 4. 新增测试

新增三项：

1. 高负载同源数据包通过FIFO等待，不产生本地PR_NACK；
2. 后续数据包产生正的段队列时延，但不被计为预约重试；
3. 队列上限包含活动队首，溢出时只丢弃超限数据包。

Day13专项测试现为16项，全部通过。

## 5. 止损复验要求

覆盖本补丁后必须依次重新运行：

```text
Day13专项测试
→ Day03—Day13完整回归
→ 6跳端到端主程序
→ DCF/Fixed完整止损矩阵
```

本次没有调整止损判定标准。只有重新生成的 `day13_stop_loss_decision.json` 为 `PASS` 才能进入Day14；若仍为 `HOLD`，应根据新证据审查判定规则是否与“4—6跳、中高负载”的研究目标一致，但不得为了得到PASS直接改阈值。
