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


def pip_size(symbol: str) -> float:
    return 0.01 if symbol.upper().endswith("JPY") else 0.0001


def evaluate_signal(
    signal: dict,
    future_candles: Sequence[Candle],
    *,
    intrabar_policy: str = "stop_first",
) -> Evaluation | None:
    """Retorna o primeiro desfecho alcançado ou None se permanecer aberto.

    Em candle que toca stop e alvo simultaneamente, usa política conservadora
    ``stop_first`` por padrão. ``target_first`` também é aceito.
    """
    if intrabar_policy not in {"stop_first", "target_first"}:
        raise ValueError("intrabar_policy deve ser stop_first ou target_first")

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
            outcome = "LOSS" if intrabar_policy == "stop_first" else "WIN"
        else:
            outcome = "LOSS" if hit_stop else "WIN"

        exit_price = stop if outcome == "LOSS" else target
        signed_move = (exit_price - entry) if side == "BUY" else (entry - exit_price)
        closed_at = datetime.fromtimestamp(candle.timestamp, tz=timezone.utc).isoformat()
        return Evaluation(
            outcome=outcome,
            exit_price=round(exit_price, 6),
            closed_at=closed_at,
            result_pips=round(signed_move / pip, 2),
            bars_held=index,
            ambiguous=ambiguous,
        )

    return None
