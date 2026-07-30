# Fixed-PRMAC 生命周期 Trace 闭合

本目录是本阶段唯一的可写证据目录。`code/run_lifecycle_audit.py` 从上一阶段只读 overlay 生成生命周期 instrumentation patch，并保存 SHA 与 scope 审计；它不修改历史目录、协议实现或 ns-3 源树。

运行顺序：`run_lifecycle_audit.py`、`run_lifecycle_calibration.py`、`run_lifecycle_closure.py`。
