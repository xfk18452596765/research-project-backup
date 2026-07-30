# PreDay18 ns-3 语义正确基线重建

本目录是独立阶段 `PreDay18_ns3语义正确基线重建` 的唯一新增内容边界。

目标是构建可复现的 ns-3.43 语义基线：真实位置驱动的链式拓扑、
PacketSocket 显式逐跳路径、接收后才转发的 DCF、K=2 Fixed-PRMAC
预约生命周期、真正作用于 `Txop` 的本地 reserved/block 接入、完整
Socket/MAC/PHY trace 与唯一包终态。

运行顺序：

```powershell
python "daily\PreDay18_ns3语义正确基线重建\code\run_semantic_checks.py"
python "daily\PreDay18_ns3语义正确基线重建\code\run_baseline_smoke.py"
python "daily\PreDay18_ns3语义正确基线重建\code\run_baseline_closure.py"
```

本阶段不执行完整止损复验，不判定 PreDay18 PASS，不开始 Day18，不运行
RL。最终状态只允许 `BASELINE_READY` 或 `BASELINE_HOLD`。
