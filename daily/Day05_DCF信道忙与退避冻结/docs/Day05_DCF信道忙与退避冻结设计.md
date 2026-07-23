# Day05：DCF信道忙检测与退避冻结设计

## 一、为什么Day05先做这一步

Day04只验证了信道始终空闲时的理想DCF链路。真实竞争型MAC中，节点在DIFS或退避期间可能侦听到其他节点占用信道。如果此时仍按原定时间发送，就无法形成正确的CSMA/CA基线。因此，在进入碰撞、重传和多跳之前，必须先实现载波侦听、DIFS重启和退避冻结。

## 二、核心规则

### 1. 到达时信道忙

数据包进入发送队列，但不开始发送。节点保持竞争状态并等待信道恢复空闲。

### 2. DIFS期间信道变忙

当前DIFS不能保留已经等待的部分，信道恢复空闲后必须重新等待一个完整DIFS。

### 3. 退避期间信道变忙

已完成的空闲时隙有效，尚未完成的退避槽数被冻结。信道恢复空闲后，节点先等待完整DIFS，然后从剩余退避槽数继续倒计时，不重新抽取退避值。

## 三、事件链

```text
PACKET_ARRIVAL
→ DIFS_START
→ DIFS_END
→ BACKOFF_START
→ BACKOFF_TICK × n
→ EXTERNAL_BUSY_START
→ BACKOFF_FREEZE
→ EXTERNAL_BUSY_END
→ DIFS_START
→ DIFS_END
→ BACKOFF_RESUME
→ BACKOFF_TICK × remaining
→ BACKOFF_EXPIRE
→ TX_START
→ TX_END
→ ACK
→ DELIVERED
```

## 四、实现方法

### 1. 逐槽退避

Day04直接调度一个总退避时长。Day05改为每个时隙调度一次`BACKOFF_TICK`：

```text
信道空闲 → remaining_slots减1
信道忙   → remaining_slots保持不变并冻结
remaining_slots=0 → TX_START
```

### 2. 失效事件令牌

离散事件队列中已经加入的DIFS_END或BACKOFF_TICK无法直接删除，因此使用`contention_generation`标记当前有效竞争轮次。信道变忙时递增标记，旧事件执行时发现标记不一致便直接返回，从而避免旧事件错误推进状态。

### 3. 外部忙时段

` schedule_external_busy()`用于创建确定性的信道忙区间，便于测试载波侦听逻辑。它只代表其他业务已经占用共享信道，不代表一个完整的第二DCF节点，因此Day05仍不处理碰撞。

## 五、确定性算例

采用Day04相同参数和随机种子7：

- 初始退避：10个时隙；
- DIFS：50 μs；
- 时隙：20 μs；
- 外部忙开始：100 μs；
- 外部忙持续：100 μs。

在100 μs之前，70 μs和90 μs两个退避时隙已经完成，因此剩余8个时隙被冻结。200 μs信道恢复空闲，随后重新等待50 μs DIFS，再继续8个时隙，发送开始时刻为：

\[
T_{\mathrm{TX\_START}}
=200+50+8\times20
=410\ \mu s
\]

DATA与ACK阶段总时长沿用Day04，为4356 μs，因此端到端时延为：

\[
D=410+4356=4766\ \mu s=0.004766\ s
\]

## 六、职责边界

- `Simulator`只调度事件；
- `Channel`只保存忙闲与占用信息；
- `DCFBusyMac`决定DIFS重启、退避冻结和恢复；
- `MetricsCollector`只记录结果；
- 本日不在`Channel`中加入碰撞判决，不在`Node`中加入协议逻辑。
