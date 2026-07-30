#!/usr/bin/env bash
set -euo pipefail
find "$HOME/workspace" -maxdepth 3 -type d -name 'ns-3.43*' 2>/dev/null | sort
