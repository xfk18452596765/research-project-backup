# Day02：核心文献精读与相关工作

## 今日总目标

围绕EMAC、Kanodia多跳调度和EASO-TDMA三篇核心文献，完成机制拆解、与本课题的对应关系分析，并形成可直接用于论文“相关工作”“问题分析”和“协议设计”部分的材料。

## 今日任务

1. 精读EMAC，明确PION传播、路径预约、数据转发和冲突处理；
2. 精读Kanodia多跳调度，明确priority tag、局部调度表和多跳协调；
3. 精读EASO-TDMA，明确SANET中继瓶颈、subscribing ships与自适应时隙分配；
4. 完成三篇文献横向对比；
5. 明确三篇文献分别支撑论文哪一部分；
6. 提取可用于Python离散事件仿真的机制；
7. 标记不应直接照搬的机制。

## 今日完成标准

能够明确回答：

- EMAC解决了什么问题，核心机制是什么？
- PION与RTS/CTS是什么关系？
- Kanodia的priority tag如何影响竞争？
- multi-hop coordination为什么能补偿上游累计时延？
- SANET中继瓶颈如何形成？
- subscribing ships数量代表什么？
- 三篇文献分别支撑RL-PRMAC的哪一部分？
