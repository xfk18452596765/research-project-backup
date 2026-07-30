# PreDay18 ns-3.43 独立干净源码工作区恢复

本目录是唯一的本阶段仓库写入位置。执行入口：`python code/run_workspace_closure.py`。

该入口以 fail-closed 方式核验历史清单中记录的三份补丁 SHA-256；任何不匹配都会写出 `NS3_WORKSPACE_HOLD`，且绝不尝试恢复源码、应用补丁、构建、测试或运行 smoke。
