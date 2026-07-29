# ns-3 实现

`scratch/preday18-dcf-fixed-prmac.cc` 使用 ns-3.43 的真实 `AdhocWifiMac`、Yans Wi-Fi 信道、UDP socket 和 802.11b 固定速率。DCF 路径直接逐跳发送；Fixed-PRMAC 是位于 `AdhocWifiMac` 之上的应用层协议 shim，发送逻辑 PR_REQ、PR_ACK、H_ACK 与 RELEASE，再发送 DATA。底层 DCF 和原生 Wi-Fi ACK 仍存在；逻辑 H_ACK 不替代底层 ACK。

这不是对 ns-3 原生 MAC 的修改，结果只能用于趋势核对。
