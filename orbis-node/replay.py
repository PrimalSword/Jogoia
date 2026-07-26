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
    parser.add_argument("--slippage", type=float, default=0.1,
                        help="slippage estimado por ponta, em pips")
    parser.add_argument("--min-rr", type=float, default=1.5)
    parser.add_argument("--cooldown-bars", type=int, default=3,
                        help="candles mínimos antes de aceitar sinal igual")
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
    if args.cooldown_bars < 0:
        raise SystemExit("--cooldown-bars não pode ser negativo")
    if args.slippage < 0:
        raise SystemExit("--slippage não pode ser negativo")

    provider = CsvReplayProvider(
        csv_path=args.csv,
        symbol=args.symbol,
        timeframe_minutes=args.timeframe,
        window_size=args.window,
        default_spread_pips=args.spread,
    )
    store = None if args.dry_run else SignalStore(args.database)
    pending: list[dict] = []
    last_signal_bar: dict[tuple[str, int, str], int] = {}
    snapshots = generated = suppressed = closed = wins = losses = breakeven = ambiguous = 0
    gross_total = cost_total = net_total = 0.0
    next_dry_id = 1

    for bar_index, snapshot in enumerate(provider.snapshots(), start=1):
        snapshots += 1
        current_candle = snapshot.candles[-1]

        still_open: list[dict] = []
        for item in pending:
            evaluation = evaluate_signal(
                item["signal"],
                [current_candle],
                intrabar_policy=args.intrabar_policy,
                spread_pips=float(item["spread_pips"]),
                slippage_pips_per_side=args.slippage,
            )
            if evaluation is None:
                item["bars"] += 1
                still_open.append(item)
                continue

            closed += 1
            wins += evaluation.outcome == "WIN"
            losses += evaluation.outcome == "LOSS"
            breakeven += evaluation.outcome == "BREAKEVEN"
            ambiguous += evaluation.ambiguous
            gross_total += evaluation.gross_pips
            cost_total += evaluation.transaction_cost_pips
            net_total += evaluation.result_pips
            if store is not None:
                store.close_signal(item["id"], evaluation)
            print(
                f"FECHOU #{item['id']} {evaluation.outcome} "
                f"bruto={evaluation.gross_pips:+.2f} custo={evaluation.transaction_cost_pips:.2f} "
                f"líquido={evaluation.result_pips:+.2f} pips em {item['bars'] + 1} candle(s)"
                + (" [AMBÍGUO]" if evaluation.ambiguous else "")
            )
        pending = still_open

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
        key = (data["symbol"], int(data["timeframe_minutes"]), data["side"])
        same_setup_open = any(
            (item["signal"]["symbol"], int(item["signal"]["timeframe_minutes"]), item["signal"]["side"]) == key
            for item in pending
        )
        last_bar = last_signal_bar.get(key)
        in_cooldown = last_bar is not None and (bar_index - last_bar) <= args.cooldown_bars
        if same_setup_open or in_cooldown:
            suppressed += 1
            reason = "posição equivalente ainda aberta" if same_setup_open else "cooldown ativo"
            print(f"IGNOROU {data['symbol']} M{data['timeframe_minutes']} {data['side']}: {reason}")
            continue

        generated += 1
        last_signal_bar[key] = bar_index
        if store is not None:
            stored = store.save_signal(data)
            signal_id = stored["id"]
        else:
            signal_id = next_dry_id
            next_dry_id += 1
        pending.append({
            "id": signal_id,
            "signal": data,
            "bars": 0,
            "spread_pips": snapshot.spread_pips,
        })
        print(
            f"ABRIU #{signal_id} {data['symbol']} M{data['timeframe_minutes']} "
            f"{data['side']} entrada={data['entry']} confiança={data['confidence']}% "
            f"spread={snapshot.spread_pips:.2f}"
        )

    print(
        f"Backtest concluído: {snapshots} janelas, {generated} sinais aceitos, "
        f"{suppressed} repetidos ignorados, {closed} fechados, {len(pending)} abertos."
    )
    if closed:
        print(
            f"Resultados: {wins} wins, {losses} losses, {breakeven} breakeven, "
            f"taxa de acerto={(wins / closed) * 100:.2f}%, ambíguos={ambiguous}."
        )
        print(
            f"Pips: bruto={gross_total:+.2f}, custos={cost_total:.2f}, líquido={net_total:+.2f}."
        )
    if store is not None:
        print(f"Resumo persistido: {store.summary()}")


if __name__ == "__main__":
    main()
