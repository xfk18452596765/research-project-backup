# 04 DCF 因果逐跳基线

固定路径为 `source → source+direction → … → destination`。应用不预先调度
后续 hop；中继必须先出现 `HOP_MAC_RX` 和 `HOP_VALIDATE`，随后才允许
`HOP_FORWARD_ENQUEUE` 与 `HOP_MAC_SEND`。

每个节点持有独立 FIFO，限制 200 包。Wi-Fi 属性冻结为 802.11b、
`DsssRate2Mbps` data、`DsssRate1Mbps` control、CWmin=15、CWmax=1023、
MaxSlrc=7。1/2/4/6-hop 单包 seed 7 全部交付；2/4/6-hop、两种流量、三个
seed 的 18 个低负载 DCF case 共 180/180 包交付。

验证器逐包检查 receive-before-forward、hop 上界、交付边界、重复和终态。
