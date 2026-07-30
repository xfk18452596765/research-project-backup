#!/usr/bin/env bash
set -euo pipefail
readonly STAGE_DIR="${1:?stage directory required}"
readonly WINDOWS_STAGE="$(wslpath -w "$STAGE_DIR")"
python.exe "$WINDOWS_STAGE\\code\\run_semantic_checks.py"
python.exe "$WINDOWS_STAGE\\code\\run_baseline_smoke.py"
