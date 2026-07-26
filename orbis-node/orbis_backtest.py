#!/usr/bin/env python3
"""Avalia sinais de paper trading contra candles posteriores."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

from orbis_trade import Candle


@dataclass(frozen=True)
class Evaluation:
    outcome: str
    exit_price: float
    closed_at: str
    result_pips: float
    bars_held: int
    ambiguous: bool = False
    gross_pips: float = 0.0
    transaction_cost_pips: float = 0.0


def pip_size(symbol: str) -> float:
    return 0.01 if symbol.upper().endswith("JPY") else 0.0001


def evaluate_signal(
    signal: dict,
    future_candles: Sequence[Candle],
    *,
    intrabar_policy: str = "stop_first",
    spread_pips: float = 0.0,
    slippage_pips_per_side: float = 0.0,
) -> Evaluation | None:
    """Retorna o primeiro desfecho alcançado ou ``None`` se seguir aberto.

    O resultado líquido desconta o spread de entrada e o slippage das duas
    pontas da operação. Em candle que toca stop e alvo simultaneamente, usa
    ``stop_first`` por padrão; ``target_first`` também é aceito.
    """
    if intrabar_policy not in {"stop_first", "target_first"}:
        raise ValueError("intrabar_policy deve ser stop_first ou target_first")
    if spread_pips < 0 or slippage_pips_per_side < 0:
        raise ValueError("custos de negociação não podem ser negativos")

    side = str(signal["side"]).upper()
    stop = float(signal["stop"])
    target = float(signal["target"])
    entry = float(signal["entry"])
    symbol = str(signal["symbol"])
    pip = pip_size(symbol)

    for index, candle in enumerate(future_candles, start=1):
        if side == "BUY":
            hit_stop = candle.low <= stop
            hit_target = candle.high >= target
        elif side == "SELL":
            hit_stop = candle.high >= stop
            hit_target = candle.low <= target
        else:
            raise ValueError(f"lado inválido: {side}")

        if not hit_stop and not hit_target:
            continue

        ambiguous = hit_stop and hit_target
        if ambiguous:
            level_outcome = "LOSS" if intrabar_policy == "stop_first" else "WIN"
        else:
            level_outcome = "LOSS" if hit_stop else "WIN"

        exit_price = stop if level_outcome == "LOSS" else target
        signed_move = (exit_price - entry) if side == "BUY" else (entry - exit_price)
        gross_pips = signed_move / pip
        transaction_cost_pips = spread_pips + (2.0 * slippage_pips_per_side)
        net_pips = gross_pips - transaction_cost_pips

        if net_pips > 0:
            outcome = "WIN"
        elif net_pips < 0:
            outcome = "LOSS"
        else:
            outcome = "BREAKEVEN"

        closed_at = datetime.fromtimestamp(candle.timestamp, tz=timezone.utc).isoformat()
        return Evaluation(
            outcome=outcome,
            exit_price=round(exit_price, 6),
            closed_at=closed_at,
            result_pips=round(net_pips, 2),
            bars_held=index,
            ambiguous=ambiguous,
            gross_pips=round(gross_pips, 2),
            transaction_cost_pips=round(transaction_cost_pips, 2),
        )

    return None
