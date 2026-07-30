# PreDay18 语义正确基线止损复验

本目录是本阶段唯一新增内容边界。比较对象严格限定为 DCF 与
Fixed-PRMAC（K=2、初始 CW=15）；不创建 Day18，不运行 RL。

执行顺序：

```powershell
python "daily\PreDay18_语义正确基线止损复验\code\run_retest_checks.py"
python "daily\PreDay18_语义正确基线止损复验\code\run_retest_experiments.py"
python "daily\PreDay18_语义正确基线止损复验\code\run_retest_closure.py"
```
