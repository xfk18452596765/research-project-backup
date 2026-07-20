# Day02_EASO_TDMA精读笔记

## 基本信息

- 题目：EASO-TDMA: Enhanced Ad Hoc Self-Organizing TDMA MAC Protocol for Shipborne Ad Hoc Networks
- 作者：Changho Yun、Yong-kon Lim
- 出处：EURASIP Journal on Wireless Communications and Networking，2015
- 本课题定位：海面船舶场景、中继瓶颈与负载自适应依据

## 精读问题

1. SANET由哪些节点组成？
2. 船舶在什么情况下需要其他船舶中继？
3. subscribing ship的准确定义是什么？
4. subscribing ships数量反映中继节点的哪种负载？
5. ASO-TDMA为什么会出现中继瓶颈？
6. 固定分配相同时隙为什么会造成负载失配？
7. EASO-TDMA如何从路由表获得subscribing ships数量？
8. EASO-TDMA如何据此决定下一周期的时隙数量？
9. 为什么允许在更多子帧中分配时隙可以降低端到端时延？
10. 哪些拓扑和指标可以迁移到RL-PRMAC？
11. TDMA资源分配与竞争型路径预约的本质区别是什么？

## 与本课题的关系

### 直接借鉴

- 船舶无法直连岸站时依靠邻近船舶多跳中继；
- 转发多个下游船舶数据的节点形成中继瓶颈；
- 路由表可用于估计节点承担的中继负载；
- 资源配置必须适应中继负载变化；
- 端到端时延、接收成功率、碰撞率和信道利用率可作为参考指标。

### 不直接照搬

- 不采用完整EASO-TDMA帧结构；
- 不采用GPS全网时隙同步；
- 不以每周期分配时隙数量作为动作；
- 本研究仍采用CSMA/CA竞争接入与路径预约。

## 一句话定位

EASO-TDMA表明，海面船舶网络中承担更多下游船舶转发任务的节点容易形成瓶颈，固定资源分配无法适应这种负载差异；本研究据此设置汇聚拓扑、信道忙碌率和队列状态，并研究竞争型路径预约的自适应选择。
