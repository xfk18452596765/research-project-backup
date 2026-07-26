# Day10：Fixed-PRMAC冲突模型设计

## 1. 继承边界

Day10直接继承Day09的固定参数与成功预约控制平面：

```text
K_fixed = 2
CWmin_fixed = 15
PR_REQ前向传播
PR_ACK反向确认
RELEASE释放
ACTIVE预约表
```

只新增：

```text
ACTIVE预约资源检查
PR_NACK反向返回
PENDING → REJECTED
```

不实现预约失败重试、预约段DATA/H_ACK转发、完整端到端Fixed-PRMAC或强化学习。

## 2. 冲突资源模型

Day10采用保守且可实现的局部资源互斥规则：

1. 只有`ACTIVE`预约占用资源；
2. 时间窗口采用半开区间`[start, end)`；
3. 同一物理链路无论方向是否相同均视为链路冲突；
4. 不同链路若共享端点节点，则视为节点冲突；
5. 节点和链路均不重叠时，时间窗口即使重叠也可并存；
6. 时间窗口不重叠时，相同资源可再次预约。

该模型用于Day10验证冲突控制机制，不代表已经实现距离相关空间复用、隐藏终端或真实海面信道。

## 3. 分布式检测位置

冲突不是由中心控制器一次性全局裁决，而是在`PR_REQ`逐跳到达接收节点时进行本地资源检查：

```text
PR_REQ_RX(link_index=i)
→ 清理已过期ACTIVE预约
→ 检查当前候选物理链路
→ 检查当前链路两端节点
→ 无冲突：继续向下一跳传播
→ 有冲突：当前节点生成PR_NACK
```

因此，下游资源冲突会在PR_REQ到达对应跳时被发现，PR_NACK只沿已经通过的部分路径反向返回。

## 4. 时间窗口

候选请求在当前检查时刻使用：

```text
candidate_start = now
candidate_end = now + reservation_duration
```

已有活动预约使用：

```text
existing_start = activated_at
existing_end = expires_at
```

两个半开区间重叠条件：

```text
candidate_start < existing_end
and
existing_start < candidate_end
```

当新请求到达时，控制器会先把`expires_at <= now`的活动预约转入`EXPIRED`，避免过期资源继续阻塞新预约。

## 5. PR_NACK反向传播

冲突在第`i`条候选链路接收端发现后：

```text
冲突节点
→ PR_NACK_TX(reverse_index=i)
→ PR_NACK_RX
→ reverse_index逐跳减1
→ 发起节点收到PR_NACK
→ PENDING → REJECTED
```

`PR_NACK`携带：

- 原流与数据包标识；
- 原路径和预约段信息；
- 已经过的部分预约链路；
- 冲突类型；
- 冲突资源；
- 已有预约标识；
- 候选与已有预约时间窗口。

## 6. 状态机

Day10新增状态转换：

```text
PENDING → REJECTED
```

保留Day09状态转换：

```text
PENDING → ACTIVE
ACTIVE → RELEASED
ACTIVE → EXPIRED
```

被拒绝请求保留在预约记录表中用于审计，但不会出现在`active_records`中，也不会修改已有活动预约的激活时间、过期时间或状态。

## 7. 指标

在Day09指标基础上新增：

```text
rejected_reservations
link_conflicts
node_conflicts
pr_nack_frames_sent
```

`PR_NACK`大小冻结为24字节，仅用于当前Fixed-PRMAC基线控制开销统计。

## 8. 测试覆盖

Day10自动测试覆盖：

1. 无资源重叠预约可并存；
2. 同链路时间重叠被拒绝；
3. 共享节点时间重叠被拒绝；
4. 时间窗口不重叠时可接受；
5. PR_NACK沿反向部分路径返回；
6. 发起者进入REJECTED；
7. 被拒绝请求不污染已有活动预约；
8. RELEASE后资源可再次预约；
9. EXPIRED后资源可再次预约；
10. 反向链路视为同一物理链路资源。

## 9. 当前边界

Day10仍然假设`schedule_reservation()`的调用方已经获得发送`PR_REQ`的机会。`CWmin_fixed=15`尚未与预约控制帧的DCF竞争过程完整耦合。

Day10结果只能证明冲突检测和拒绝控制平面工作正确，不能用于宣称Fixed-PRMAC已经优于DCF。
