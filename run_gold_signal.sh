#!/usr/bin/env bash
# Wrapper script for cron.
# 1) Runs the signal model (gold_signal.py) — pushes LINE on signal flip
# 2) Runs the portfolio tracker — paper-trades and pushes LINE on trade

set -euo pipefail
cd "$(dirname "$0")"

if [ -f ".env" ]; then
  set -a; source ./.env; set +a
fi

# Run signal model first (updates state, pushes signal alerts)
python3 gold_signal.py "$@"

# Run portfolio tracker (paper trade based on signal)
python3 portfolio_tracker.py "$@"
