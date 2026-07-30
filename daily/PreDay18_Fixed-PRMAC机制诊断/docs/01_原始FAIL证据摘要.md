# 原始 FAIL 证据摘要

基线提交为 `1292d3a0c21199e7baa9184179371f9bf6b69d00`。历史
`stop_loss_decision.json` 的结论为 `FAIL`，Day18 为 `LOCKED`。

原实验数量：

| 平台 | 核心 | 敏感 |
|---|---:|---:|
| Python | 720 | 360 |
| ns-3 | 360 | 160 |

原结论显示 Fixed-PRMAC 在 ns-3 关键场景有显著交付率损失，且 Python 与 ns-3
趋势不一致。本任务没有删除、覆盖或重新解释该原始事实，也没有重新运行原止损矩阵。

历史证据的逐文件 SHA256 位于
`results/audit/original_evidence_sha256.json`。清单在诊断开始和闭环结束各计算一次；
必须逐项完全相等。
