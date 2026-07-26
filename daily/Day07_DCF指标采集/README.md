# Day07：DCF指标采集

## 一、任务定位

Day07在Day06碰撞与重传基础上实现固定路由多跳DCF。每个中继节点重新入队、重新等待DIFS、重新退避和竞争，以构建传统逐跳竞争DCF基线。

同时建立每跳和端到端指标采集器。

## 二、今日目标

完成：

```text
源节点入队
→ DIFS与随机退避
→ 当前跳DATA/ACK成功
→ 数据包推进到下一中继
→ 中继重新入队
→ 重新执行DCF竞争
→ 逐跳重复
→ 最终目的节点送达
```

## 三、已完成内容

- 实现`DCFMultiHopNetwork`；
- 实现`DCFMultiHopMac`；
- 实现固定路由检查和邻居链路校验；
- 实现ACK驱动的数据包逐跳推进；
- 实现中继重新入队与新一轮DCF；
- 实现每跳独立重传语义；
- 实现`DCFMetricsCollector`；
- 采集每跳排队、接入、发送确认和总时延；
- 采集DIFS、竞争、退避槽、冻结、碰撞、ACK超时和重传；
- 输出逐跳CSV与汇总JSON；
- 建立2、4、6跳确定性验证；
- 完成Day03—Day07回归测试。

## 四、指标范围

每跳记录：

- `queue_delay`；
- `access_delay`；
- `tx_ack_delay`；
- `hop_delay`；
- DIFS启动次数；
- 竞争次数；
- 选中与实际消耗的退避槽数；
- 退避冻结次数；
- 当前跳重传次数。

全局记录：

- 端到端时延；
- 创建、送达和丢弃数量；
- 成功跳数；
- 碰撞与碰撞包尝试；
- ACK超时；
- 累计退避时间；
- 全路径重传次数。

## 五、目录说明

```text
Day07_DCF指标采集/
├─ code/
│  ├─ dcf_multihop_metrics.py
│  ├─ main_dcf_multihop_metrics.py
│  ├─ test_dcf_multihop_metrics.py
│  └─ run_day03_day07_regression.py
├─ docs/
├─ figures/
├─ logs/
├─ results/
└─ README.md
```

## 六、运行方法

Day07自动测试：

```powershell
python ".\daily\Day07_DCF指标采集\code\test_dcf_multihop_metrics.py"
```

完整回归：

```powershell
python ".\daily\Day07_DCF指标采集\code\run_day03_day07_regression.py"
```

运行2、4、6跳指标实验：

```powershell
python ".\daily\Day07_DCF指标采集\code\main_dcf_multihop_metrics.py"
```

## 七、测试结果

自动测试：

```text
All Day07 multi-hop DCF and metric-collection tests passed.
```

完整回归：

```text
All Day03-Day07 regression tests passed.
```

## 八、关键实验结果

每跳固定退避10槽：

| 跳数 | 端到端时延 | 竞争次数 | DIFS次数 | 累计退避槽 |
|---:|---:|---:|---:|---:|
| 2 | 0.009212秒 | 2 | 2 | 20 |
| 4 | 0.018424秒 | 4 | 4 | 40 |
| 6 | 0.027636秒 | 6 | 6 | 60 |

所有场景均满足：

```text
delivered = 1
queues_empty = True
channel_idle = True
```

结果表明无竞争条件下，传统DCF端到端时延随跳数线性累计。

## 九、结果文件

```text
results/
├─ dcf_2hop_records.csv
├─ dcf_2hop_summary.json
├─ dcf_4hop_records.csv
├─ dcf_4hop_summary.json
├─ dcf_6hop_records.csv
├─ dcf_6hop_summary.json
└─ dcf_hop_scaling.csv
```

## 十、当前实现边界

当前2、4、6跳实验使用：

- 单业务流；
- 确定性固定退避；
- 无持续业务负载；
- 无最终论文统计规模。

因此结果用于验证多跳逻辑和指标实现，不直接作为最终性能实验结论。

Day07仍未实现：

- Fixed-PRMAC；
- 路径预约；
- Q-learning；
- 动态路由；
- 真实海面信道。

## 十一、今日结论

Day07完成了可测量的多跳DCF基线。每个中继重新竞争的机制已经实现，能够量化逐跳竞争造成的时延累计。

## 十二、明日衔接

Day08验证随机退避、多数据包、不同负载和共享中继场景，并修正日志与指标边界问题。
