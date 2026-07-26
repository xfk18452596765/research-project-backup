# Day05：DCF信道忙与退避冻结

## 一、任务定位

Day05在Day04最小DCF流程上增加载波侦听、DIFS中断、退避冻结和恢复机制，使DCF能够在共享信道被其他业务占用时正确推迟接入。

本日使用外部忙时段验证机制，不引入第二个完整DCF竞争节点，因此不发生碰撞。

## 二、今日目标

验证三类行为：

1. 数据包到达时信道已忙，等待空闲后再执行DIFS；
2. DIFS期间信道变忙，当前DIFS作废，空闲后重新等待完整DIFS；
3. 退避期间信道变忙，冻结剩余退避槽，空闲后等待完整DIFS并继续倒计时。

## 三、已完成内容

- 实现`DCFBusyMac`；
- 实现`WAIT_CHANNEL`、`DIFS`、`BACKOFF`等阶段状态；
- 将退避改为逐时隙`BACKOFF_TICK`；
- 实现`CHANNEL_BUSY_WAIT`；
- 实现`DIFS_INTERRUPTED`；
- 实现`BACKOFF_FREEZE`与`BACKOFF_RESUME`；
- 使用竞争代次标记使旧DIFS/退避事件失效；
- 实现确定性外部信道忙区间；
- 保证信道忙和退避冻结不会增加重传次数或扩大CW；
- 完成自动测试和主程序轨迹验证。

## 四、核心事件链

```text
PACKET_ARRIVAL
→ DIFS_START
→ DIFS_END
→ BACKOFF_START
→ BACKOFF_TICK
→ EXTERNAL_BUSY_START
→ BACKOFF_FREEZE
→ EXTERNAL_BUSY_END
→ DIFS_START
→ DIFS_END
→ BACKOFF_RESUME
→ BACKOFF_EXPIRE
→ TX_START
→ TX_END
→ ACK
→ DELIVERED
```

## 五、目录说明

```text
Day05_DCF信道忙与退避冻结/
├─ code/
│  ├─ dcf_busy_mac.py
│  ├─ main_dcf_busy_freeze.py
│  └─ test_dcf_busy_freeze.py
├─ docs/
├─ figures/
├─ logs/
├─ results/
└─ README.md
```

## 六、运行方法

自动测试：

```powershell
python ".\daily\Day05_DCF信道忙与退避冻结\code\test_dcf_busy_freeze.py"
```

预期结果：

```text
All Day05 DCF busy-channel and backoff-freeze tests passed.
```

运行演示：

```powershell
python ".\daily\Day05_DCF信道忙与退避冻结\code\main_dcf_busy_freeze.py"
```

## 七、关键验证结果

确定性退避冻结场景：

```text
初始退避槽数   = 10
信道忙开始     = 0.000100秒
冻结剩余槽数   = 8
信道忙结束     = 0.000200秒
恢复后DIFS结束 = 0.000250秒
发送开始       = 0.000410秒
ACK到达        = 0.004766秒
端到端时延     = 0.004766秒
重传次数       = 0
CW             = CWmin
```

最终状态：

- 数据包成功送达；
- 队列为空；
- 节点状态恢复`IDLE`；
- 信道恢复空闲；
- 送达率为1.000。

## 八、当前实现边界

本日尚未实现：

- 两个DCF节点同时竞争；
- 同槽碰撞；
- ACK超时；
- 二进制指数退避；
- 数据包重传与重传上限；
- 隐藏终端和RTS/CTS；
- 多跳转发；
- 路径预约和强化学习。

## 九、今日结论

Day05完成了正确CSMA/CA基线所需的信道忙检测、DIFS重启、退避冻结和恢复，为Day06多节点碰撞与重传提供了稳定基础。

## 十、明日衔接

Day06增加多个发送节点共享碰撞域，实现同槽碰撞、ACK超时、BEB和重传。
