# Day09：Fixed-PRMAC报文与预约任务计划

## 一、任务定位

Day09严格使用原目录：

```text
daily/Day09_Fixed-PRMAC报文与预约/
```

Day08已经完成传统DCF基线的多跳验证与调试。Day09开始进入Fixed-PRMAC，但只实现报文模型和“无冲突条件下的成功预约控制流程”。

本日把一次预约理解为：

```text
当前预约段起始节点已经通过固定CW的DCF竞争获得控制帧发送机会
→ PR_REQ沿固定K跳向前传播
→ 预约段末端返回PR_ACK
→ PR_ACK反向到达发起节点
→ 预约记录变为ACTIVE
```

## 二、冻结参数

Fixed-PRMAC第一版固定：

```text
K_fixed = 2
CWmin_fixed = 15
```

当剩余跳数小于2时：

```text
K_effective = min(K_fixed, remaining_hops)
```

Fixed-PRMAC不读取网络状态，不执行Q-learning，也不动态改变K或CW。

## 三、报文类型

本日建立统一枚举：

- `PR_REQ`：发起路径段预约；
- `PR_ACK`：反向确认预约成功；
- `PR_NACK`：预约失败，Day10以后使用；
- `RELEASE`：提前释放预约；
- `DATA`：预约段数据帧，Day11使用；
- `H_ACK`：单跳确认，Day11使用。

Day09实际运行：

```text
PR_REQ
PR_ACK
RELEASE
```

## 四、核心字段

统一控制帧保存：

- FlowID；
- PacketID；
- Path；
- SegmentStartIndex；
- RequestedHops；
- EffectiveHops；
- Priority；
- Duration；
- Sender；
- Receiver；
- ReservedLinks；
- CreatedAt；
- Reason。

## 五、实现内容

1. Fixed-PRMAC配置对象；
2. 报文类型和报文数据结构；
3. 预约记录及生命周期状态；
4. PR_REQ逐跳前向传播；
5. PR_ACK逐跳反向确认；
6. ACTIVE预约表；
7. RELEASE逐跳传播；
8. 基于Duration的手动超时清理；
9. 控制帧数量和字节开销统计；
10. 预约建立时延统计；
11. Day03—Day09回归脚本。

## 六、完成标准

1. `K_fixed=2`且`CWmin_fixed=15`；
2. 四节点路径从节点0发起时预约`0→1、1→2`；
3. PR_REQ前向传播2跳；
4. PR_ACK反向返回2跳；
5. 发起节点收到PR_ACK后预约状态变为ACTIVE；
6. 剩余1跳时`K_effective=1`；
7. 所有控制帧字段保持一致；
8. RELEASE能够清除ACTIVE预约；
9. Duration到期时预约能够标记为EXPIRED；
10. 非邻居链路在事件开始前被拒绝；
11. Day09不执行冲突拒绝，两条重叠预约均可成功；
12. Day03—Day09回归测试全部通过。

## 七、本日明确不做

- 预约冲突检查；
- 链路冲突图；
- PR_NACK处理；
- 预约失败重传；
- 预约段DATA连续转发；
- H_ACK；
- 批量数据预约；
- 动态K；
- 动态CW；
- Q-learning；
- 真实海面信道；
- ns-3。
