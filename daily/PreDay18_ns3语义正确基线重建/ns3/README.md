# ns-3.43 semantic baseline

This directory is the reproducible source boundary for the stage. It does not
contain an ns-3 source tree or build products.

- `patches/ns3-3.43-fixed-prmac-access.patch` adds per-Txop reserved and blocked
  access state at the native channel-access request point.
- `overlay/scratch/preday18-semantic-baseline.cc` implements PacketSocket,
  explicit next-hop MAC addressing, receive-before-forward DCF, K=2 control/data
  lifecycle, trace boundaries, calibration, multiflow, and hidden-terminal
  scenarios.
- `scripts/prepare_clean_ns3_worktree.sh` pins official tag `ns-3.43` at commit
  `753817468d611239b1e3c2e272b2bed8ef1f580c`.

Reserved access does not bypass `ChannelAccessManager` or PHY reception. It
removes the per-hop random backoff only while a local PR_ACK-derived grant is
active. A decoded PR_REQ installs a local conflict block; distant nodes have no
global lock and retain spatial reuse.
