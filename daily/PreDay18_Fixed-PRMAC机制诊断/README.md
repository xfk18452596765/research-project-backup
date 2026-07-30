# PreDay18 Fixed-PRMAC 机制诊断

本目录是 PreDay18 `FAIL` 后的独立根因诊断证据。它不重新判定 PASS，不修改历史
`daily/PreDay18_最小止损路线/`，不进入 Day18，也不运行 RL。

## 冻结参数

`K=2`、`CWmin=15`、`CWmax=1023`、`retry_limit=7`、payload 1024 bytes、
DATA 2 Mbps、control/basic 1 Mbps、slot 20 us。

## 运行

```powershell
$RepoRoot = "C:\research-project-backup"
$DiagDir = Join-Path $RepoRoot "daily\PreDay18_Fixed-PRMAC机制诊断"
Set-Location $RepoRoot
python "$DiagDir\code\run_static_audit.py"
python "$DiagDir\code\run_diagnostic_checks.py"
python "$DiagDir\code\run_diagnostic_closure.py"
```

`run_diagnostic_checks.py` 编译真实 ns-3.43 `AdhocWifiMac + YansWifiPhy + UDP`
诊断参考程序。若 188 组摘要和 trace 已完整存在，入口只复用并验证，避免无意义重跑。

## 结论边界

最终分类为 `MIXED_ROOT_CAUSE`：原 shim 存在已确认的实现伪影；在组合参考语义下
Fixed 仍低于 DCF，协议层风险没有被排除。该参考程序用于定位语义和栈边界，
不是新的性能验收或止损判定。
