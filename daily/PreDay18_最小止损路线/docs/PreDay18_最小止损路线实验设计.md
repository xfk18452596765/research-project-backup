# 实验设计与接口审计

基线为 `635a7dc38bc135c989baa86f2f856cfd669acca0`。Day01--Day17 与既有 Day18 占位目录完全冻结。本任务只比较 DCF 与固定 K=2、初始 CW=15 的 Fixed-PRMAC，不导入 Day14--Day17 RL 模块。

Python DCF 复用 Day08 `DCFValidatedMultiHopMac`、`CollisionChannel`、`DCFContentionCoordinator` 与统计器；Fixed 复用 Day13 `FixedPRMACEndToEndController`、`Day13FixedPRMACConfig` 和汇总函数。新适配器只替换到达调度与多流包装。3 个原始种子、2/4/6 跳、三负载、8 包回归与 Day13 结果逐项一致。

Python 与 ns-3 共享负载、包长、速率、重试上限、K、CW 和种子。ns-3 是应用层 shim，因此只比较方向，不比较绝对值。
