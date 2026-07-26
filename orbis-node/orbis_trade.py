#!/usr/bin/env python3
"""Motor mínimo do Orbis Trade.

Não envia ordens. Recebe candles já fechados, calcula indicadores simples e
retorna apenas candidatos a sinal para validação, paper trading e backtest.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from statistics import fmean
from typing import Iterable, Sequence


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
    mode: str = "paper"

    def to_dict(self) -> dict:
        data = asdict(self)
        data["reasons"] = list(self.reasons)
        return data


def ema(values: Sequence[float], period: int) -> float:
    if len(values) < period:
        raise ValueError(f"São necessários ao menos {period} valores")
    multiplier = 2.0 / (period + 1.0)
    current = fmean(values[:period])
    for value in values[period:]:
        current = (value - current) * multiplier + current
    return current


def atr(candles: Sequence[Candle], period: int = 14) -> float:
    if len(candles) < period + 1:
        raise ValueError(f"São necessários ao menos {period + 1} candles")
    ranges: list[float] = []
    for previous, current in zip(candles[-period - 1 : -1], candles[-period:]):
        ranges.append(
            max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close),
            )
        )
    return fmean(ranges)


def rsi(values: Sequence[float], period: int = 14) -> float:
    if len(values) < period + 1:
        raise ValueError(f"São necessários ao menos {period + 1} valores")
    changes = [b - a for a, b in zip(values[-period - 1 : -1], values[-period:])]
    gains = fmean(max(change, 0.0) for change in changes)
    losses = fmean(max(-change, 0.0) for change in changes)
    if losses == 0:
        return 100.0
    relative_strength = gains / losses
    return 100.0 - (100.0 / (1.0 + relative_strength))


def analyze(
    symbol: str,
    timeframe_minutes: int,
    candles: Sequence[Candle],
    spread_pips: float,
    maximum_spread_pips: float = 1.5,
    minimum_risk_reward: float = 1.5,
) -> Signal | None:
    """Retorna um candidato simples ou None.

    Critérios iniciais deliberadamente conservadores:
    tendência EMA 9/21, RSI não extremo, candle de confirmação, ATR positivo,
    spread abaixo do limite e alvo mínimo configurável.
    """
    if len(candles) < 30 or spread_pips > maximum_spread_pips:
        return None

    closes = [candle.close for candle in candles]
    fast = ema(closes, 9)
    slow = ema(closes, 21)
    momentum = rsi(closes, 14)
    volatility = atr(candles, 14)
    last = candles[-1]

    bullish = fast > slow and last.close > last.open and 52.0 <= momentum <= 70.0
    bearish = fast < slow and last.close < last.open and 30.0 <= momentum <= 48.0
    if not bullish and not bearish:
        return None

    side = "BUY" if bullish else "SELL"
    entry = last.close
    stop_distance = max(volatility * 0.8, abs(last.close - last.open))
    reward_distance = stop_distance * minimum_risk_reward

    if side == "BUY":
        stop = entry - stop_distance
        target = entry + reward_distance
    else:
        stop = entry + stop_distance
        target = entry - reward_distance

    reasons = (
        "EMA 9 alinhada com EMA 21",
        "RSI em faixa operacional",
        "candle de confirmação",
        "spread dentro do limite",
    )
    confidence = 60
    confidence += 8 if abs(fast - slow) > volatility * 0.15 else 0
    confidence += 7 if 55.0 <= momentum <= 65.0 or 35.0 <= momentum <= 45.0 else 0
    confidence = min(confidence, 82)

    return Signal(
        symbol=symbol,
        timeframe_minutes=timeframe_minutes,
        side=side,
        entry=round(entry, 6),
        stop=round(stop, 6),
        target=round(target, 6),
        risk_reward=round(minimum_risk_reward, 2),
        confidence=confidence,
        created_at=datetime.now(timezone.utc).isoformat(),
        reasons=reasons,
    )


def candles_from_rows(rows: Iterable[dict]) -> list[Candle]:
    return [
        Candle(
            timestamp=int(row["timestamp"]),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row.get("volume", 0.0)),
        )
        for row in rows
    ]
