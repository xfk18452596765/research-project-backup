# PreDay18 最小止损路线

本目录执行 Day17 后、Day18 前的 DCF 与 Fixed-PRMAC（固定 K=2、初始
CW=15）训练前止损验证。它不导入 Day14--Day17 的 RL 模块，不运行训练，
也不修改任何既有 Day 目录。

基线：`635a7dc38bc135c989baa86f2f856cfd669acca0`

完整入口：

```powershell
python daily/PreDay18_最小止损路线/code/run_preday18_full_closure.py
```

ns-3 源文件和脚本保存在 `ns3/`；构建产物仅留在 WSL ns-3 工作区，不提交。
