# Day12任务计划：Fixed-PRMAC失败与重传

## 1. 前置状态

Day11已经完成并合并：

```text
ACTIVE预约
→ DATA/H_ACK逐跳连续转发
→ 预约段末端完成
```

Day12只在此基础上补齐预约控制面的失败恢复，不修改Day03—Day11稳定代码。

## 2. 今日目标

实现：

```text
PR_NACK
→ 当前预约尝试进入REJECTED
→ DIFS + 随机退避
→ 二进制指数扩大CW
→ 创建新的预约尝试
→ 成功进入ACTIVE
→ 超过重试上限进入FAILED
```

## 3. 固定参数

与现有DCF基线对齐：

```text
CWmin       = 15
CWmax       = 1023
slot_time   = 20 μs
DIFS        = 50 μs
retry_limit = 7
random_seed = 7
```

固定预约长度继续为：

```text
K_fixed = 2
```

## 4. 最小验收项

1. 无冲突时第一次预约直接成功；
2. PR_NACK到达发起端后才开始退避；
3. 第一次重试CW由15扩大到31；
4. 随机退避在`[0, CW]`内；
5. 每次重试创建新的预约记录；
6. 旧的REJECTED记录保留；
7. 冲突释放后重试能够成功；
8. 持续冲突时达到上限并进入FAILED；
9. 最终失败时数据包进入DROPPED；
10. 固定随机种子可复现；
11. 重试成功后的ACTIVE预约仍可调用Day11 DATA/H_ACK转发；
12. Day03—Day12完整回归在本地完整项目中通过。

## 5. 今日不做

- 初始PR_REQ接入与完整共享信道竞争耦合；
- 退避期间的信道忙冻结/恢复；
- DATA或H_ACK丢失、超时与重传；
- 跨多个预约段的端到端传输；
- DCF与Fixed-PRMAC公平性能预实验；
- Q-learning或RL策略。

上述完整耦合和止损预实验留给Day13。
