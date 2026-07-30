# 05 Fixed-PRMAC K=2 生命周期

段起点按 route index 0、2、4 划分，段终点为
`min(start+2, flow_hops)`。每段执行：

`LOCAL_FIFO_HEAD → INITIAL_DIFS_AND_BACKOFF → PR_REQ forward → PR_ACK reverse
→ RESERVATION_ACTIVE → DATA/H_ACK causal forwarding → RELEASE reverse
→ SEGMENT_COMPLETED`。

下一段只在前段 RELEASE 回到段起点并记录 `SEGMENT_COMPLETED` 后开始。
2/4/6-hop 单包分别完成 1/2/3 段，且每段 `effective_hops<=2`。

`reservation-conflict` 场景向首个接收节点注入一次可审计的本地 active-table
冲突。节点发送 PR_NACK；源端收到后使用
`min((15+1)*2^n-1,1023)`，首重试 CW=31，从 `[0,CW]` 抽取 slots，
等待 `DIFS + slots*20us`，以新 attempt 重新发送 PR_REQ，随后交付。
