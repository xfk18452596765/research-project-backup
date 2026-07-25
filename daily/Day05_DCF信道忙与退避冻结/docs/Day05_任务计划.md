# Day05：DCF信道忙检测与退避冻结任务计划

## 一、任务定位

Day05严格承接Day04已经完成的单节点、单跳、无竞争DCF流程，不修改Day03底层框架，也不覆盖Day04基线代码。本日只补齐DCF在共享信道中的两个基础行为：

1. 信道忙时推迟接入；
2. 退避期间信道变忙时冻结计数，信道恢复空闲后重新等待DIFS并继续剩余退避。

## 二、今日目标

验证三种场景：

```text
场景A：数据包到达时信道已忙
→ 等待信道空闲
→ DIFS
→ 随机退避
→ DATA
→ ACK
→ DELIVERED
```

```text
场景B：DIFS期间信道变忙
→ 当前DIFS作废
→ 等待信道空闲
→ 重新等待完整DIFS
→ 随机退避
→ 发送
```

```text
场景C：退避期间信道变忙
→ 冻结剩余退避槽数
→ 等待信道空闲
→ 重新等待完整DIFS
→ 从剩余槽数继续退避
→ 发送
```

## 三、目录结构

```text
research-project-backup-main/
└─ daily/
   └─ Day05_DCF信道忙与退避冻结/
      ├─ docs/
      │  ├─ Day05_任务计划.md
      │  └─ Day05_DCF信道忙与退避冻结设计.md
      ├─ code/
      │  ├─ dcf_busy_mac.py
      │  ├─ main_dcf_busy_freeze.py
      │  └─ test_dcf_busy_freeze.py
      ├─ figures/
      ├─ logs/
      └─ results/
```

## 四、实现原则

- 继续复用Day03的`Simulator`、`Node`、`Packet`、`Channel`和`MetricsCollector`；
- 继续复用Day04的`DCFConfig`和成功发送/ACK流程；
- 新增`DCFBusyMac`，不直接改写Day04已经通过测试的`DCFMac`；
- 退避计数改为逐时隙`BACKOFF_TICK`，以便在任意退避阶段冻结；
- 外部忙时段仅表示“其他发送已经占用信道”，不模拟第二个DCF节点；
- Day05不产生碰撞，不增加重传次数，也不改变竞争窗口。

## 五、完成标准

1. Day03测试继续通过；
2. Day04测试继续通过；
3. 数据包到达时信道忙，节点不会报错或发送；
4. DIFS期间信道变忙，旧DIFS事件失效并重新等待完整DIFS；
5. 退避期间信道变忙，剩余槽数保持不变；
6. 信道空闲后先等待DIFS，再继续剩余退避；
7. 三种场景最终均成功送达；
8. 重传次数保持0，`CW`保持`CWmin`；
9. 测试输出：

```text
All Day05 DCF busy-channel and backoff-freeze tests passed.
```

## 六、本日明确不做

- 两个DCF节点同时竞争；
- 碰撞检测；
- ACK超时；
- 二进制指数退避；
- 重传与重试上限；
- 隐藏终端；
- RTS/CTS；
- 多跳转发；
- 路径预约；
- 强化学习。
