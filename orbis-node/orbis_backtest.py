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
    exit_reason: str = "LEVEL"


def pip_size(symbol: str) -> float:
    return 0.01 if symbol.upper().endswith("JPY") else 0.0001


def _build_evaluation(
    signal: dict,
    candle: Candle,
    *,
    exit_price: float,
    bars_held: int,
    spread_pips: float,
    slippage_pips_per_side: float,
    ambiguous: bool = False,
    exit_reason: str = "LEVEL",
) -> Evaluation:
    side = str(signal["side"]).upper()
    entry = float(signal["entry"])
    pip = pip_size(str(signal["symbol"]))
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

    return Evaluation(
        outcome=outcome,
        exit_price=round(exit_price, 6),
        closed_at=datetime.fromtimestamp(candle.timestamp, tz=timezone.utc).isoformat(),
        result_pips=round(net_pips, 2),
        bars_held=bars_held,
        ambiguous=ambiguous,
        gross_pips=round(gross_pips, 2),
        transaction_cost_pips=round(transaction_cost_pips, 2),
        exit_reason=exit_reason,
    )


def evaluate_signal(
    signal: dict,
    future_candles: Sequence[Candle],
    *,
    intrabar_policy: str = "stop_first",
    spread_pips: float = 0.0,
    slippage_pips_per_side: float = 0.0,
    bars_already_held: int = 0,
    max_bars_held: int | None = None,
) -> Evaluation | None:
    """Retorna o primeiro desfecho alcançado ou ``None`` se seguir aberto.

    O resultado líquido desconta spread e slippage. Quando ``max_bars_held`` é
    atingido sem stop ou alvo, a operação é encerrada pelo fechamento do candle.
    """
    if intrabar_policy not in {"stop_first", "target_first"}:
        raise ValueError("intrabar_policy deve ser stop_first ou target_first")
    if spread_pips < 0 or slippage_pips_per_side < 0:
        raise ValueError("custos de negociação não podem ser negativos")
    if bars_already_held < 0:
        raise ValueError("bars_already_held não pode ser negativo")
    if max_bars_held is not None and max_bars_held < 1:
        raise ValueError("max_bars_held deve ser pelo menos 1")

    side = str(signal["side"]).upper()
    stop = float(signal["stop"])
    target = float(signal["target"])

    for index, candle in enumerate(future_candles, start=1):
        bars_held = bars_already_held + index
        if side == "BUY":
            hit_stop = candle.low <= stop
            hit_target = candle.high >= target
        elif side == "SELL":
            hit_stop = candle.high >= stop
            hit_target = candle.low <= target
        else:
            raise ValueError(f"lado inválido: {side}")

        if hit_stop or hit_target:
            ambiguous = hit_stop and hit_target
            if ambiguous:
                level_outcome = "LOSS" if intrabar_policy == "stop_first" else "WIN"
            else:
                level_outcome = "LOSS" if hit_stop else "WIN"
            exit_price = stop if level_outcome == "LOSS" else target
            return _build_evaluation(
                signal,
                candle,
                exit_price=exit_price,
                bars_held=bars_held,
                spread_pips=spread_pips,
                slippage_pips_per_side=slippage_pips_per_side,
                ambiguous=ambiguous,
                exit_reason="STOP" if level_outcome == "LOSS" else "TARGET",
            )

        if max_bars_held is not None and bars_held >= max_bars_held:
            return _build_evaluation(
                signal,
                candle,
                exit_price=float(candle.close),
                bars_held=bars_held,
                spread_pips=spread_pips,
                slippage_pips_per_side=slippage_pips_per_side,
                exit_reason="TIMEOUT",
            )

    return None
