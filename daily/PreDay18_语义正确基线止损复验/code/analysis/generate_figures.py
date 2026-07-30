from __future__ import annotations

import json
from pathlib import Path

STAGE = Path(__file__).resolve().parents[2]
payload = json.loads((STAGE / "results/ns3/confirmatory/aggregate/paired_statistics.json").read_text(encoding="utf-8"))
cells = payload["cells"]
labels = [cell["cell"] for cell in cells]
dcf = [cell["metrics"]["average_e2e_delay"]["dcf_mean"] for cell in cells]
fixed = [cell["metrics"]["average_e2e_delay"]["fixed_mean"] for cell in cells]
width, height, margin = 1200, 560, 70
maximum = max(dcf + fixed)
plot_height = height - 2 * margin
cell_width = (width - 2 * margin) / len(labels)
parts = [
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
    '<rect width="100%" height="100%" fill="white"/>',
    '<text x="600" y="32" text-anchor="middle" font-family="sans-serif" font-size="22">Confirmatory matrix: paired mean delay</text>',
    f'<line x1="{margin}" y1="{height-margin}" x2="{width-margin}" y2="{height-margin}" stroke="black"/>',
]
for index, (label, dcf_value, fixed_value) in enumerate(zip(labels, dcf, fixed)):
    center = margin + (index + 0.5) * cell_width
    for offset, value, color in ((-16, dcf_value, "#4c78a8"), (16, fixed_value, "#e45756")):
        bar_height = value / maximum * plot_height
        parts.append(f'<rect x="{center+offset-13:.1f}" y="{height-margin-bar_height:.1f}" width="26" height="{bar_height:.1f}" fill="{color}"/>')
    parts.append(f'<text x="{center:.1f}" y="{height-margin+20}" text-anchor="middle" font-family="sans-serif" font-size="11">{label}</text>')
parts += [
    '<rect x="930" y="45" width="16" height="16" fill="#4c78a8"/><text x="952" y="58" font-family="sans-serif" font-size="13">DCF</text>',
    '<rect x="1010" y="45" width="16" height="16" fill="#e45756"/><text x="1032" y="58" font-family="sans-serif" font-size="13">Fixed-PRMAC</text>',
    f'<text x="18" y="{height/2}" transform="rotate(-90 18 {height/2})" text-anchor="middle" font-family="sans-serif" font-size="14">Mean end-to-end delay (s)</text>',
    "</svg>",
]
(STAGE / "figures").mkdir(parents=True, exist_ok=True)
(STAGE / "figures/confirmatory_mean_delay.svg").write_text("\n".join(parts) + "\n", encoding="utf-8")
