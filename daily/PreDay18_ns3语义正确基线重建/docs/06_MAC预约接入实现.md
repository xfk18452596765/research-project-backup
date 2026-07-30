# 06 MAC 预约接入实现

补丁为 `Txop` 增加三个公开语义接口：

- `SetFixedPrmacReservedAccess(enabled, expires)`
- `SetFixedPrmacBlockedUntil(until)`
- `HasFixedPrmacReservedAccess()`

reserved 状态不会直接调用 PHY；它只改变接入请求前的随机退避。随后仍经
`ChannelAccessManager::RequestAccess`，因此介质忙、物理干扰和接收失败保持
真实。普通本地接入在 `blockedUntil` 前延迟，远端 Txop 不受影响。

Gate 4 证据包括 reserved-zero-random-backoff trace、本地
`DCF_ACCESS_DEFERRED`、RELEASE 清理，以及多流 trace 中距离至少三节点且处于
重叠本地窗口的 grant 对。由此证明没有全局锁，同时没有把应用层错峰冒充预约。
