# PreDay18 最终止损报告

## 执行摘要

最终判定：**FAIL**。

Day18 保持锁定；不得开始 RL 训练。最小下一步是回到 Fixed-PRMAC/ns-3 shim 的交付率与逐跳发送机制诊断，不得调整 K=2、CW=15、固定种子或判定门槛。

## 实验范围

- Python 核心：720/720 runs（periodic/poisson，2/4/6 hops，三负载，20 seeds，200 packets）。
- Python 敏感性：360 runs（burst、M1/M2/M3、多流、空间复用包装、8-hop）。
- ns-3 核心：360/360 runs（10 seeds，100 packets）。
- ns-3 敏感性：160/160 runs（burst、M1/M2、hidden stress、1%/5% control loss）。
- 所有已生成结果可解析、有限、终止，活动预约为 0。

## 公平性与实现边界

共享配置固定 K=2、初始 CW=15、CWmax=1023、retry=7、1024-byte payload、2/1 Mbps 数据/控制速率及同一成对种子/到达表。Python 复用 Day08 DCF 和 Day13 Fixed-PRMAC 实现。

ns-3 为 `AdhocWifiMac` 上的应用层 Fixed-PRMAC shim，底层 DCF/ACK 仍存在。因此只做趋势核对，不宣称修改了原生 Wi-Fi MAC。

## Python 结果

Python 核心门槛通过。周期业务 4-high、6-medium、6-high 的 Fixed−DCF 平均时延差均小于 0，配对 bootstrap 95% CI 上界均小于 0；四个关键格中 3 个获益。Poisson 的四个关键格均获益且核心目标 CI 为负。

Python 鲁棒性门槛未完成：冻结 Day08/Day13 API 没有可安全复用的逻辑控制帧丢失与超时钩子；全局 `CollisionChannel` 也不能表达独立载波侦听/干扰矩阵。因此控制丢失为 `NOT_RUN`，隐藏终端为 `NOT_VALID`，没有伪造结果或用 ns-3 替代。

## ns-3 结果与 FAIL 依据

ns-3 smoke、CLI 编译和 520 个结果 schema 检查通过，但核心性能硬门槛失败。关键单元格中 Fixed 相对 DCF 的平均交付率下降约 15.0–34.1 个百分点，明显超过冻结的 2 个百分点上限。多数 6-hop 周期/Poisson 核心格 Fixed 平均时延也更差。

这同时触发：

- `ns3_delivery_hard_fail = true`
- `ns3_persistent_worse = true`
- `ns3_core = false`
- `cross_platform_trend = false`

## 测试

PreDay18 Python 专项测试通过；ns-3 520-run 完整性测试通过；Day03--Day17 全量回归通过。Day01--Day17 与 Day18 未修改，未运行 RL。

## 下一步

停止 Day18 和 RL 路线。仅允许新任务诊断 ns-3 Fixed shim 的大量交付丢失，包括应用层逐跳调度与底层 DCF/UDP 接收边界；不得在本任务中调参制造收益。
