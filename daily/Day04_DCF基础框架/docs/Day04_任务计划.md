# Day04：DCF基础框架任务计划

## 一、任务定位

Day04继续沿用Day03完成的Python离散事件底层框架，在`Node`与`Channel`之间加入`DCFMac`。本阶段只验证传统DCF最基础的单跳接入链路，为后续多跳逐跳竞争、Fixed-PRMAC和RL-PRMAC提供统一基线。

## 二、第一阶段目标

在以下严格条件下完成一个数据包的发送：

- 发送节点：1个；
- 接收节点：1个；
- 路由：固定单跳`(0, 1)`；
- 信道：始终空闲；
- 业务：单个数据包；
- 碰撞：无；
- ACK：必定成功返回。

事件链为：

```text
PACKET_ARRIVAL
→ DIFS_START / DIFS_END
→ BACKOFF_START / BACKOFF_EXPIRE
→ TX_START
→ TX_END
→ ACK
→ DELIVERED
```

## 三、生成文件

```text
Day04_DCF基础框架/
├─ docs/
│  ├─ Day04_任务计划.md
│  └─ Day04_DCF单跳设计.md
├─ code/
│  ├─ dcf_config.py
│  ├─ dcf_mac.py
│  ├─ main_dcf_single_hop.py
│  └─ test_dcf_single_hop.py
├─ figures/
├─ logs/
└─ results/
```

## 四、代码职责

- `dcf_config.py`：集中保存DIFS、SIFS、时隙、CW、速率和帧长度参数；
- `dcf_mac.py`：实现最小DCF状态推进和事件调度；
- `main_dcf_single_hop.py`：构造单跳场景并打印事件轨迹；
- `test_dcf_single_hop.py`：验证事件顺序、最终状态和理论时延。

## 五、本阶段完成标准

1. 数据包能够从`CREATED/QUEUED`进入`CONTENDING`和`TRANSMITTING`；
2. 信道在`TX_START`时占用，在`TX_END`时释放；
3. ACK到达后数据包状态为`DELIVERED`；
4. 源节点队列为空，MAC状态回到`IDLE`；
5. 统计模块记录1个创建包、1个送达包、0个丢弃包；
6. 仿真时延等于DIFS、随机退避、DATA发送、SIFS、ACK发送和传播时延之和；
7. 测试输出：`All Day04 minimum single-hop DCF tests passed.`

## 六、本阶段明确不做

- 双节点碰撞；
- 信道忙时退避冻结与恢复；
- 二进制指数退避和重传；
- 隐藏终端；
- RTS/CTS；
- 多跳转发；
- 路径预约；
- 强化学习。

这些内容不能提前混入第一阶段代码。
