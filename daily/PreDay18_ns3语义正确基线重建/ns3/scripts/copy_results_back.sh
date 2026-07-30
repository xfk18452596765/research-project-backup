#!/usr/bin/env bash
set -euo pipefail

readonly SOURCE_DIR="${1:?WSL result directory required}"
readonly TARGET_DIR="${2:?repository stage directory required}"
mkdir -p "$TARGET_DIR/results" "$TARGET_DIR/logs"
cp -a "$SOURCE_DIR/results/." "$TARGET_DIR/results/"
cp -a "$SOURCE_DIR/logs/." "$TARGET_DIR/logs/"
