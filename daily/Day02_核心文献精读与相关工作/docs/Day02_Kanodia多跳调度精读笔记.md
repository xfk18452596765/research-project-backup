# Day02_Kanodia多跳调度精读笔记

## 基本信息

- 题目：Distributed Multi-Hop Scheduling and Medium Access with Delay and Throughput Constraints
- 作者：V. Kanodia、C. Li、A. Sabharwal、B. Sadeghi、E. Knightly
- 出处：ACM MobiCom 2001
- 本课题定位：业务优先级、竞争窗口调整和上游时延补偿的理论参考

## 精读问题

1. priority index和priority tag分别表示什么？
2. 节点将优先级信息捎带在哪些报文中？
3. 周围节点如何通过监听建立本地调度表？
4. 本地调度表为什么只能近似全局理想调度？
5. 节点如何根据相对优先级调整退避？
6. 什么是multi-hop coordination？
7. 数据包在上游发生额外延迟后，下游节点如何提高其优先级？
8. 数据包提前到达下游时，为什么可以降低其优先级？
9. 哪些思想可用于突发告警业务？
10. 哪些机制不需要在第一版RL-PRMAC中完整实现？

## 与本课题的关系

- 业务优先级应影响MAC竞争过程；
- 可以通过退避参数体现业务紧迫程度；
- 多跳端到端目标需要在中继节点持续修正；
- 上游已累计较大时延的数据包应在下游获得补偿；
- 第一版不完整复现EDF、Virtual Clock和完整邻居优先级表。

## 一句话定位

Kanodia等人的工作说明，端到端时延约束不能只在源节点处理，而应通过分布式优先级传播和下游补偿映射到各跳的信道竞争过程；本研究将这一思想简化为业务优先级状态、竞争窗口动作和时延敏感奖励。
