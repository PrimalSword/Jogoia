#!/usr/bin/env python3
"""Indicadores quantitativos leves do Orbis Trade, sem dependências externas."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from statistics import fmean
from typing import Sequence


@dataclass(frozen=True)
class IndicatorSnapshot:
    ema9: float
    ema21: float
    ema50: float
    ema200: float | None
    rsi14: float
    atr14: float
    adx14: float
    macd: float
    macd_signal: float
    macd_histogram: float
    bollinger_mid: float
    bollinger_upper: float
    bollinger_lower: float
    vwap: float | None
    support: float
    resistance: float
    regime: str


def ema_series(values: Sequence[float], period: int) -> list[float]:
    if period <= 0 or len(values) < period:
        raise ValueError(f"São necessários ao menos {period} valores")
    seed = fmean(values[:period])
    result = [seed]
    multiplier = 2.0 / (period + 1.0)
    current = seed
    for value in values[period:]:
        current = (value - current) * multiplier + current
        result.append(current)
    return result


def ema(values: Sequence[float], period: int) -> float:
    return ema_series(values, period)[-1]


def rsi(values: Sequence[float], period: int = 14) -> float:
    if len(values) < period + 1:
        raise ValueError(f"São necessários ao menos {period + 1} valores")
    changes = [b - a for a, b in zip(values[-period - 1:-1], values[-period:])]
    gains = fmean(max(change, 0.0) for change in changes)
    losses = fmean(max(-change, 0.0) for change in changes)
    if losses == 0:
        return 100.0
    return 100.0 - (100.0 / (1.0 + gains / losses))


def true_ranges(candles: Sequence[object]) -> list[float]:
    return [
        max(
            current.high - current.low,
            abs(current.high - previous.close),
            abs(current.low - previous.close),
        )
        for previous, current in zip(candles[:-1], candles[1:])
    ]


def atr(candles: Sequence[object], period: int = 14) -> float:
    if len(candles) < period + 1:
        raise ValueError(f"São necessários ao menos {period + 1} candles")
    return fmean(true_ranges(candles)[-period:])


def adx(candles: Sequence[object], period: int = 14) -> float:
    if len(candles) < period + 1:
        raise ValueError(f"São necessários ao menos {period + 1} candles")
    selected = candles[-period - 1:]
    trs = true_ranges(selected)
    plus_dm: list[float] = []
    minus_dm: list[float] = []
    for previous, current in zip(selected[:-1], selected[1:]):
        up = current.high - previous.high
        down = previous.low - current.low
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
    tr_sum = sum(trs)
    if tr_sum == 0:
        return 0.0
    plus_di = 100.0 * sum(plus_dm) / tr_sum
    minus_di = 100.0 * sum(minus_dm) / tr_sum
    denominator = plus_di + minus_di
    return 0.0 if denominator == 0 else 100.0 * abs(plus_di - minus_di) / denominator


def macd(values: Sequence[float]) -> tuple[float, float, float]:
    if len(values) < 35:
        raise ValueError("São necessários ao menos 35 valores para MACD")
    fast = ema_series(values, 12)
    slow = ema_series(values, 26)
    offset = len(fast) - len(slow)
    line = [fast[index + offset] - slow[index] for index in range(len(slow))]
    signal = ema_series(line, 9)[-1]
    current = line[-1]
    return current, signal, current - signal


def bollinger(values: Sequence[float], period: int = 20, deviations: float = 2.0) -> tuple[float, float, float]:
    if len(values) < period:
        raise ValueError(f"São necessários ao menos {period} valores")
    sample = values[-period:]
    middle = fmean(sample)
    variance = fmean((value - middle) ** 2 for value in sample)
    deviation = sqrt(variance)
    return middle, middle + deviations * deviation, middle - deviations * deviation


def vwap(candles: Sequence[object], period: int = 30) -> float | None:
    sample = candles[-period:]
    total_volume = sum(max(float(candle.volume), 0.0) for candle in sample)
    if total_volume <= 0:
        return None
    weighted = sum(
        ((candle.high + candle.low + candle.close) / 3.0) * max(float(candle.volume), 0.0)
        for candle in sample
    )
    return weighted / total_volume


def support_resistance(candles: Sequence[object], period: int = 20) -> tuple[float, float]:
    sample = candles[-period:]
    return min(candle.low for candle in sample), max(candle.high for candle in sample)


def snapshot(candles: Sequence[object]) -> IndicatorSnapshot:
    if len(candles) < 60:
        raise ValueError("São necessários ao menos 60 candles")
    closes = [float(candle.close) for candle in candles]
    current_atr = atr(candles, 14)
    current_adx = adx(candles, 14)
    macd_line, macd_signal, histogram = macd(closes)
    middle, upper, lower = bollinger(closes)
    support, resistance = support_resistance(candles)
    ema21_value = ema(closes, 21)
    ema50_value = ema(closes, 50)
    ema200_value = ema(closes, 200) if len(closes) >= 200 else None
    band_width = (upper - lower) / middle if middle else 0.0
    if current_adx >= 25 and abs(ema21_value - ema50_value) >= current_atr * 0.25:
        regime = "TREND"
    elif band_width < 0.004 or current_adx < 18:
        regime = "RANGE"
    else:
        regime = "TRANSITION"
    return IndicatorSnapshot(
        ema9=ema(closes, 9), ema21=ema21_value, ema50=ema50_value,
        ema200=ema200_value, rsi14=rsi(closes, 14), atr14=current_atr,
        adx14=current_adx, macd=macd_line, macd_signal=macd_signal,
        macd_histogram=histogram, bollinger_mid=middle,
        bollinger_upper=upper, bollinger_lower=lower,
        vwap=vwap(candles), support=support, resistance=resistance,
        regime=regime,
    )
