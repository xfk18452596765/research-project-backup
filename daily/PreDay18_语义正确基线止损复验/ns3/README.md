# ns-3 复验扩展

`source/preday18-stop-loss-retest.cc` 由
`code/prepare_experiment_source.py` 从已合并且哈希核验通过的语义正确基线
Git blob 确定性生成。扩展仅增加本任务预先冻结的 medium 负载、指数 Poisson
到达、burst、M3、空间复用及逻辑控制帧丢失入口；K、CW、PHY、帧大小和
Fixed-PRMAC 生命周期不变。

生成源码会复制到 WSL 临时 ns-3 工作树的 `scratch/`，不改三个历史证据目录。
