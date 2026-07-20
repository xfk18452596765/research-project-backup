# Day02_EMAC精读笔记

## 基本信息

- 题目：EMAC: An Asynchronous Routing-Enhanced MAC Protocol in Multi-hop Wireless Networks
- 作者：Shu Du、Yanjun Sun、David B. Johnson
- 出处：IEEE GLOBECOM 2010
- 本课题定位：Fixed-PRMAC路径预约机制的主要参考文献

## 精读问题

1. IEEE 802.11 DCF在多跳网络中的主要问题是什么？
2. 什么是intra-flow contention？
3. PION控制帧包含哪些必要信息？
4. PION如何从源节点沿既定路由向下游传播？
5. 为什么一个中继节点发送的PION同时具有CTS和RTS的作用？
6. 源节点在什么条件下开始发送DATA？
7. 为什么源节点不能在收到第一个转发PION后立即发送DATA？
8. Tdelay与Data Delay Factor解决了什么问题？
9. PION传播在什么情况下终止？
10. 中间节点没有收到下游确认PION时如何处理？
11. EMAC如何解决路径预约与已有调度的冲突？
12. EMAC减少的是流内竞争还是流间竞争？
13. 哪些机制可直接简化为Fixed-PRMAC？
14. 哪些时间同步和调度计算不宜在第一版仿真中完整复现？

## 与本课题的关系

### 直接借鉴

- 使用路由信息确定后续中继节点；
- 控制帧沿多跳路径传播；
- 一个控制帧兼具上游确认和下游请求功能；
- 预约成功后按路径顺序转发DATA；
- 通过预约减少流内竞争。

### 简化处理

- 不完整复现EMAC的异步时钟调度公式；
- 使用离散事件调度器统一维护事件时间；
- 预约长度限制为1、2或3跳；
- Fixed-PRMAC固定预约长度；
- RL-PRMAC由Q-learning选择预约长度。

## 一句话定位

EMAC证明了在异步多跳CSMA/CA网络中，可以借助有限路由信息和沿路径传播的控制帧完成多跳协同预约，从而减少同一业务流内部的重复竞争；本研究在其路径预约思想上进一步研究预约长度与竞争窗口的自适应选择。
