#!/usr/bin/env python3
"""Executa replay CSV e grava os sinais simulados no SQLite."""

from __future__ import annotations

import argparse
from pathlib import Path

from orbis_provider import CsvReplayProvider
from orbis_storage import SignalStore
from orbis_trade import analyze

ROOT = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay de candles do Orbis Trade")
    parser.add_argument("csv", type=Path, help="arquivo CSV de candles")
    parser.add_argument("--symbol", default="EUR_USD", help="par no formato EUR_USD")
    parser.add_argument("--timeframe", type=int, choices=(1, 5), default=1)
    parser.add_argument("--window", type=int, default=60)
    parser.add_argument("--spread", type=float, default=0.8)
    parser.add_argument("--max-spread", type=float, default=1.5)
    parser.add_argument("--min-rr", type=float, default=1.5)
    parser.add_argument(
        "--database",
        type=Path,
        default=ROOT / "data" / "orbis.db",
        help="caminho do SQLite",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="analisa sem gravar sinais no banco",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    provider = CsvReplayProvider(
        csv_path=args.csv,
        symbol=args.symbol,
        timeframe_minutes=args.timeframe,
        window_size=args.window,
        default_spread_pips=args.spread,
    )
    store = None if args.dry_run else SignalStore(args.database)

    snapshots = 0
    generated = 0
    for snapshot in provider.snapshots():
        snapshots += 1
        signal = analyze(
            symbol=snapshot.symbol,
            timeframe_minutes=snapshot.timeframe_minutes,
            candles=snapshot.candles,
            spread_pips=snapshot.spread_pips,
            maximum_spread_pips=args.max_spread,
            minimum_risk_reward=args.min_rr,
        )
        if signal is None:
            continue

        data = signal.to_dict()
        data["source"] = snapshot.source
        generated += 1
        if store is not None:
            stored = store.save_signal(data)
            print(
                f"#{stored['id']} {stored['symbol']} M{stored['timeframe_minutes']} "
                f"{stored['side']} entrada={stored['entry']} confiança={stored['confidence']}%"
            )
        else:
            print(
                f"DRY {data['symbol']} M{data['timeframe_minutes']} "
                f"{data['side']} entrada={data['entry']} confiança={data['confidence']}%"
            )

    print(f"Replay concluído: {snapshots} janelas, {generated} sinais.")
    if store is not None:
        print(f"Resumo: {store.summary()}")


if __name__ == "__main__":
    main()
