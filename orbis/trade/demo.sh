#!/bin/sh
set -eu

TMP=/tmp/orbis-trade-demo.csv
python3 - "$TMP" <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import csv
import math
import sys

path = Path(sys.argv[1])
start = 1767225600
price = 100.0
with path.open("w", newline="", encoding="utf-8") as handle:
    writer = csv.writer(handle)
    writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
    for i in range(240):
        trend = 0.11 if i < 80 else (-0.08 if i < 145 else 0.14)
        wave = math.sin(i / 5.0) * 0.75
        opening = price
        closing = max(1.0, opening + trend + wave * 0.18)
        high = max(opening, closing) + 0.35 + abs(wave) * 0.08
        low = min(opening, closing) - 0.35 - abs(wave) * 0.08
        writer.writerow([start + i * 3600, f"{opening:.4f}", f"{high:.4f}", f"{low:.4f}", f"{closing:.4f}", 1000 + i * 3])
        price = closing
PY

orbis-trade import-csv "$TMP" --symbol DEMO --timeframe 1h
orbis-trade backtest --symbol DEMO --timeframe 1h --fast 9 --slow 21 --capital 10000 --fee-bps 10
