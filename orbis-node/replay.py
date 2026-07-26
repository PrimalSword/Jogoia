#!/usr/bin/env python3
"""Executa backtest CSV, avalia desfechos e grava no SQLite."""

from __future__ import annotations

import argparse
from pathlib import Path

from orbis_backtest import evaluate_signal
from orbis_provider import CsvReplayProvider
from orbis_storage import SignalStore
from orbis_trade import analyze

ROOT = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest de candles do Orbis Trade")
    parser.add_argument("csv", type=Path, help="arquivo CSV de candles")
    parser.add_argument("--symbol", default="EUR_USD", help="par no formato EUR_USD")
    parser.add_argument("--timeframe", type=int, choices=(1, 5), default=1)
    parser.add_argument("--window", type=int, default=60)
    parser.add_argument("--spread", type=float, default=0.8)
    parser.add_argument("--max-spread", type=float, default=1.5)
    parser.add_argument("--min-rr", type=float, default=1.5)
    parser.add_argument(
        "--intrabar-policy",
        choices=("stop_first", "target_first"),
        default="stop_first",
        help="critério quando stop e alvo são tocados no mesmo candle",
    )
    parser.add_argument(
        "--database", type=Path, default=ROOT / "data" / "orbis.db",
        help="caminho do SQLite",
    )
    parser.add_argument("--dry-run", action="store_true", help="não altera o banco")
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
    pending: list[dict] = []
    snapshots = generated = closed = wins = losses = ambiguous = 0
    next_dry_id = 1

    for snapshot in provider.snapshots():
        snapshots += 1
        current_candle = snapshot.candles[-1]

        still_open: list[dict] = []
        for item in pending:
            evaluation = evaluate_signal(
                item["signal"], [current_candle], intrabar_policy=args.intrabar_policy
            )
            if evaluation is None:
                still_open.append(item)
                continue
            closed += 1
            wins += evaluation.outcome == "WIN"
            losses += evaluation.outcome == "LOSS"
            ambiguous += evaluation.ambiguous
            if store is not None:
                store.close_signal(item["id"], evaluation)
            print(
                f"FECHOU #{item['id']} {evaluation.outcome} "
                f"{evaluation.result_pips:+.2f} pips em {item['bars'] + 1} candle(s)"
                + (" [AMBÍGUO]" if evaluation.ambiguous else "")
            )
        pending = still_open
        for item in pending:
            item["bars"] += 1

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
            signal_id = stored["id"]
        else:
            signal_id = next_dry_id
            next_dry_id += 1
        pending.append({"id": signal_id, "signal": data, "bars": 0})
        print(
            f"ABRIU #{signal_id} {data['symbol']} M{data['timeframe_minutes']} "
            f"{data['side']} entrada={data['entry']} confiança={data['confidence']}%"
        )

    print(
        f"Backtest concluído: {snapshots} janelas, {generated} sinais, "
        f"{closed} fechados, {len(pending)} abertos."
    )
    if closed:
        print(
            f"Resultados: {wins} wins, {losses} losses, "
            f"taxa de acerto={(wins / closed) * 100:.2f}%, ambíguos={ambiguous}."
        )
    if store is not None:
        print(f"Resumo persistido: {store.summary()}")


if __name__ == "__main__":
    main()
