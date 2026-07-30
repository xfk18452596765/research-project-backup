from __future__ import annotations

import json
import shutil
from pathlib import Path

from audit.evidence import DIAG_ROOT, HISTORY, write_or_verify

SOURCE = HISTORY / "ns3" / "scratch" / "preday18-dcf-fixed-prmac.cc"
AUDIT_DIR = DIAG_ROOT / "results" / "audit"
COPY = DIAG_ROOT / "ns3" / "scratch" / "preday18-diagnostic-baseline.cc"


def finding(check_id: str, status: str, lines: str, evidence: str, impact: str) -> dict:
    return {
        "check_id": check_id,
        "status": status,
        "file": "daily/PreDay18_最小止损路线/ns3/scratch/preday18-dcf-fixed-prmac.cc",
        "lines": lines,
        "evidence": evidence,
        "impact": impact,
    }


def main() -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    COPY.parent.mkdir(parents=True, exist_ok=True)
    write_or_verify(AUDIT_DIR / "original_evidence_sha256.json")
    shutil.copyfile(SOURCE, COPY)

    findings = [
        finding("TOPOLOGY_TRUE_MULTIHOP", "FAIL", "61-66",
                "所有节点没有设置坐标；FixedRssLossModel 对任意节点对固定为 -80 dBm。",
                "源与终点具有和相邻节点相同的传播损耗，原拓扑等效全连接。"),
        finding("CAUSAL_FORWARDING_FIXED", "FAIL", "72-82",
                "业务生成时在双重循环中预先调度所有 hop；没有接收回调触发下一跳。",
                "NON_CAUSAL_PRE_SCHEDULING=true；上游失败不能阻止下游发送。"),
        finding("CAUSAL_FORWARDING_DCF", "FAIL", "72-82",
                "DCF 使用同一预调度 hop 循环，ReceiveData 只统计终点。",
                "DCF 也是非因果假多跳，不能作为有效端到端基线。"),
        finding("K2_SEGMENT", "FAIL", "74-81",
                "每个 hop 都独立发送 PR_REQ、PR_ACK、DATA、H_ACK、RELEASE。",
                "K2_SEGMENT_NOT_IMPLEMENTED=true；控制开销随 hop 重复。"),
        finding("RESERVATION_MEDIUM_EFFECT", "FAIL", "75-81",
                "预约仅改变应用层发送时间，DATA 仍由普通 UDP socket 进入 AdhocWifiMac/DCF。",
                "RESERVATION_HAS_NO_MEDIUM_EFFECT=true；没有保护窗口或 MAC 接入豁免。"),
        finding("STACK_BOUNDARY_TRACE", "FAIL", "33-45,84",
                "未检查 Socket::Send 返回值，未连接 MAC/PHY trace source。",
                "无法把未交付包定位到 socket、MAC、PHY 或协议层。"),
        finding("LOSS_ACCOUNTING", "FAIL", "24,82,84",
                "最终 dropped 被覆盖为 packets-delivered。",
                "丢包边界过粗，且可能掩盖非因果转发造成的统计异常。"),
        finding("PAYLOAD_SIZE", "FAIL", "43-45,80",
                "Create<Packet>(1024+34) 后又 AddHeader(SeqTsHeader)。",
                "线上包长大于配置 payload，并重复混入头部预算。"),
        finding("BEB_SLOT", "FAIL", "70,76-77",
                "初始 backoff 使用 20 us，但失败等待使用 10 us；CW 使用 15*2^n 而非 (15+1)*2^n-1。",
                "退避时隙与冻结定义不一致，BEB 上界存在 off-by-one。"),
        finding("HIDDEN_TERMINAL", "FAIL", "76",
                "hiddenTerminal 仅额外注入 0.05 Bernoulli 控制丢失。",
                "HIDDEN_TERMINAL_NOT_IMPLEMENTED=true。"),
        finding("MULTIFLOW", "FAIL", "52,55",
                "flows 仅由命令行解析，后续从未参与节点、socket 或业务生成。",
                "MULTIFLOW_NOT_IMPLEMENTED=true。"),
    ]
    flags = {
        "NON_CAUSAL_PRE_SCHEDULING": True,
        "K2_SEGMENT_NOT_IMPLEMENTED": True,
        "RESERVATION_HAS_NO_MEDIUM_EFFECT": True,
        "HIDDEN_TERMINAL_NOT_IMPLEMENTED": True,
        "MULTIFLOW_NOT_IMPLEMENTED": True,
    }
    result = {
        "source_sha256": write_or_verify(AUDIT_DIR / "original_evidence_sha256.json")["files"][
            "daily/PreDay18_最小止损路线/ns3/scratch/preday18-dcf-fixed-prmac.cc"
        ],
        "summary": {"pass": 0, "fail": len(findings), "unknown": 0},
        "flags": flags,
        "findings": findings,
    }
    (AUDIT_DIR / "static_audit.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    rows = "\n".join(
        f"| {x['check_id']} | {x['status']} | {x['lines']} | {x['evidence']} | {x['impact']} |"
        for x in findings
    )
    (DIAG_ROOT / "docs").mkdir(parents=True, exist_ok=True)
    (DIAG_ROOT / "docs" / "02_ns3静态代码审计.md").write_text(
        "# ns-3 静态代码审计\n\n"
        "审计对象是原 FAIL 证据中的 87 行 ns-3 shim；原文件未修改。\n\n"
        "| 检查项 | 结果 | 原文件行号 | 证据 | 影响 |\n"
        "|---|---|---:|---|---|\n" + rows + "\n\n"
        f"机器可读结果：`results/audit/static_audit.json`。失败项：{len(findings)}，未知项：0。\n",
        encoding="utf-8",
    )
    semantic = """# 协议语义差异表

| 语义 | 原 ns-3 shim | 最小参考语义 | 诊断 |
|---|---|---|---|
| 多跳拓扑 | FixedRss -80 dBm，全节点对相同 | 相邻可达、非相邻不可直达 | 原实现不是真多跳 |
| 逐跳因果 | 所有 hop 预先调度 | 上一跳成功接收后才触发下一跳 | 原 DCF/Fixed 都不因果 |
| K=2 | 每 hop 完整预约 | 一次预约覆盖最多 2 hop | 原 K=2 未实现 |
| 介质效果 | DATA 仍独立竞争 DCF | 已预约段有声明的保护窗口 | 原预约没有介质效果 |
| 丢失边界 | created-delivered | 每包唯一终态 | 原结果不能定位损失层 |
| hidden terminal | 5% 随机控制丢失 | 由拓扑、载波侦听和干扰产生 | 原敏感项不代表隐藏终端 |
| multi-flow | 参数解析后未使用 | 独立流、socket 和源终点 | 原敏感项实际仍为单流 |
| BEB | 20 us 与 10 us 混用，CW 公式偏差 | CW(n)=min((CWmin+1)2^n-1,CWmax)，slot=20 us | 原退避语义不一致 |
"""
    (DIAG_ROOT / "docs" / "03_协议语义差异表.md").write_text(semantic, encoding="utf-8")
    print(f"Static audit complete: {len(findings)} FAIL findings; evidence files={result['source_sha256'][:12]}...")


if __name__ == "__main__":
    main()
