# Python 扩展实验说明

核心矩阵为 720 runs：2 协议 × 3 跳数 × 3 负载 × periodic/poisson × 20 固定种子，每 run 200 包。Poisson 到达表先生成并保存，同一场景的两种协议读取同一列表。

敏感性已执行 burst、多流 M1/M2/M3、空间复用包装和 8-hop，共 360 runs。冻结模型存在两个不能隐瞒的能力缺口：Day08/Day13 无逻辑控制帧丢失/超时注入接口；Day08 `CollisionChannel` 为全局信道，没有独立通信、载波侦听和干扰矩阵。因此 Python 控制丢失标记 NOT_RUN、隐藏终端标记 NOT_VALID，不得用 ns-3 结果替代，也不得据此判 PASS。
