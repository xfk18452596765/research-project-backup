# ns-3 实现说明与局限

实现类型：`AdhocWifiMac` 之上的应用层 Fixed-PRMAC shim，不是修改后的原生 Wi-Fi MAC。底层 802.11 DCF、退避和 ACK 继续存在；逻辑 H_ACK 是独立 UDP 控制帧。控制帧也经过底层 DCF。预约 DATA 仍可能受底层退避影响。

shim 按本地逐跳状态推进，不创建全局预约决策表。逻辑控制丢失使用冻结 Bernoulli 序列，最多 7 次重试并终止；hiddenTerminal 为压力故障注入，不是完整传播矩阵复现。`./ns3 --version` 在本地 ns-3.43 wrapper 不受支持，版本取自根目录 `VERSION` 文件；`hello-simulator` 已通过。

绝对时延包含 ns-3 Wi-Fi/UDP 与 shim 双层开销，不能与 Python 绝对值对齐。
