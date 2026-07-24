# Day06：DCF碰撞、ACK超时与重传任务计划

## 一、任务定位

Day06继续沿用Day03的Python离散事件仿真底层框架、Day04的最小单跳DCF时序，以及Day05的信道忙检测和退避冻结机制。本日将单发送节点扩展为两个发送节点共享一个碰撞域，建立后续多跳DCF基线所需的碰撞与重传能力。

本日没有进入多跳、路径预约或强化学习，RL-PRMAC总体技术路线保持不变。

## 二、今日目标

实现以下完整流程：

```text
两个节点同时到达队首数据包
→ 各自独立等待DIFS
→ 各自独立选择随机退避
→ 两节点同一时隙退避归零
→ 同时发送DATA并发生碰撞
→ 均未收到ACK
→ ACK_TIMEOUT
→ retries增加
→ CW按二进制指数退避扩大
→ 重新等待DIFS并随机退避
→ 退避值分离
→ 两个数据包依次成功送达
```

## 三、今日实现范围

1. 两个发送节点共享一个单跳碰撞域；
2. 同一退避时隙归零时判定为碰撞；
3. 碰撞后不返回ACK；
4. ACK超时后增加数据包重传次数；
5. 竞争窗口按照 `CW_new=min(2×CW_old+1,CWmax)` 更新；
6. 重传时重新选择随机退避；
7. 达到重传上限后丢弃数据包；
8. 成功送达后CW恢复为CWmin；
9. 统计碰撞、重传、送达和丢弃结果。

## 四、生成文件

```text
Day06_DCF碰撞与重传/
├─ docs/
│  ├─ Day06_任务计划.md
│  └─ Day06_DCF碰撞与重传设计.md
├─ code/
│  ├─ dcf_collision_mac.py
│  ├─ main_dcf_two_node_collision.py
│  └─ test_dcf_collision_retry.py
├─ figures/
├─ logs/
└─ results/
```

## 五、完成标准

1. 单节点场景仍保持Day04的成功时延；
2. 两节点同一时隙发送时只计为一次共享信道碰撞；
3. 两个碰撞包均触发ACK_TIMEOUT；
4. 两个包的retries均增加1；
5. CW由15扩大为31；
6. 重传退避值分离后两个数据包依次送达；
7. 送达后两个节点均恢复IDLE；
8. 信道最终为空闲；
9. retry_limit=0时两个碰撞包均被丢弃；
10. 输出：`All Day06 DCF collision and retransmission tests passed.`

## 六、本日明确不做

- 隐藏终端；
- 捕获效应；
- 非碰撞信道误码；
- RTS/CTS；
- 多跳转发；
- 动态路由；
- 路径预约；
- Fixed-PRMAC；
- Q-learning；
- 真实海面传播模型；
- ns-3。
