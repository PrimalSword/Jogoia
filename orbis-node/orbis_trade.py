#!/usr/bin/env python3
"""Motor quantitativo do Orbis Trade.

Não envia ordens. Recebe candles fechados, calcula indicadores, classifica o
regime e retorna apenas candidatos auditáveis para paper trading e backtest.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Iterable, Sequence

from orbis_indicators import snapshot
from orbis_score import calculate_score, explain_score


@dataclass(frozen=True)
class Candle:
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(frozen=True)
class Signal:
    symbol: str
    timeframe_minutes: int
    side: str
    entry: float
    stop: float
    target: float
    risk_reward: float
    confidence: int
    created_at: str
    reasons: tuple[str, ...]
    score_breakdown: dict
    indicators: dict
    setup: str
    regime: str
    mode: str = "paper"

    def to_dict(self) -> dict:
        data = asdict(self)
        data["reasons"] = list(self.reasons)
        return data


def _detect_setup(candles: Sequence[Candle], indicators, side: str) -> str | None:
    last = candles[-1]
    previous = candles[-2]
    bullish = side == "BUY"
    continuation = (
        last.close > indicators.ema9 and previous.low <= indicators.ema21
        if bullish else last.close < indicators.ema9 and previous.high >= indicators.ema21
    )
    breakout = (
        last.close >= indicators.resistance and previous.close < indicators.resistance
        if bullish else last.close <= indicators.support and previous.close > indicators.support
    )
    confirmation = last.close > last.open if bullish else last.close < last.open
    if breakout and confirmation:
        return "BREAKOUT"
    if continuation and confirmation:
        return "PULLBACK"
    if confirmation:
        return "TREND_CONTINUATION"
    return None


def analyze(
    symbol: str,
    timeframe_minutes: int,
    candles: Sequence[Candle],
    spread_pips: float,
    maximum_spread_pips: float = 1.5,
    minimum_risk_reward: float = 1.5,
    minimum_score: int = 70,
) -> Signal | None:
    if len(candles) < 60 or spread_pips > maximum_spread_pips:
        return None

    indicators = snapshot(candles)
    last = candles[-1]
    bullish = (
        indicators.ema9 > indicators.ema21
        and indicators.macd_histogram > 0
        and 50.0 <= indicators.rsi14 <= 72.0
    )
    bearish = (
        indicators.ema9 < indicators.ema21
        and indicators.macd_histogram < 0
        and 28.0 <= indicators.rsi14 <= 50.0
    )
    if not bullish and not bearish:
        return None

    side = "BUY" if bullish else "SELL"
    setup = _detect_setup(candles, indicators, side)
    if setup is None:
        return None

    entry = last.close
    structural_distance = (
        entry - max(indicators.support, entry - indicators.atr14 * 1.5)
        if side == "BUY"
        else min(indicators.resistance, entry + indicators.atr14 * 1.5) - entry
    )
    stop_distance = max(indicators.atr14 * 0.9, abs(last.close - last.open), structural_distance)
    reward_distance = stop_distance * minimum_risk_reward
    if side == "BUY":
        stop, target = entry - stop_distance, entry + reward_distance
    else:
        stop, target = entry + stop_distance, entry - reward_distance

    score = calculate_score(
        indicators, side, spread_pips, maximum_spread_pips,
        minimum_risk_reward, last.close,
    )
    if score.total < minimum_score:
        return None

    indicator_data = asdict(indicators)
    reasons = (
        f"Setup identificado: {setup}",
        *explain_score(score, indicators, side),
    )
    return Signal(
        symbol=symbol,
        timeframe_minutes=timeframe_minutes,
        side=side,
        entry=round(entry, 6),
        stop=round(stop, 6),
        target=round(target, 6),
        risk_reward=round(minimum_risk_reward, 2),
        confidence=score.total,
        created_at=datetime.fromtimestamp(last.timestamp, tz=timezone.utc).isoformat(),
        reasons=reasons,
        score_breakdown=score.to_dict(),
        indicators=indicator_data,
        setup=setup,
        regime=indicators.regime,
    )


def candles_from_rows(rows: Iterable[dict]) -> list[Candle]:
    return [
        Candle(
            timestamp=int(row["timestamp"]), open=float(row["open"]),
            high=float(row["high"]), low=float(row["low"]),
            close=float(row["close"]), volume=float(row.get("volume", 0.0)),
        )
        for row in rows
    ]
