#!/usr/bin/env python3
"""Pontuação auditável de qualidade dos sinais do Orbis Trade."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ScoreBreakdown:
    trend: int
    momentum: int
    volatility: int
    structure: int
    liquidity: int
    risk: int
    total: int
    label: str

    def to_dict(self) -> dict:
        return asdict(self)


def calculate_score(indicators, side: str, spread_pips: float, maximum_spread_pips: float,
                    risk_reward: float, last_close: float) -> ScoreBreakdown:
    bullish = side == "BUY"
    aligned_ema = (
        indicators.ema9 > indicators.ema21 > indicators.ema50
        if bullish else indicators.ema9 < indicators.ema21 < indicators.ema50
    )
    long_term = indicators.ema200 is None or (
        last_close > indicators.ema200 if bullish else last_close < indicators.ema200
    )
    trend = 10 + (6 if aligned_ema else 0) + (4 if long_term else 0)

    rsi_ok = 52 <= indicators.rsi14 <= 68 if bullish else 32 <= indicators.rsi14 <= 48
    macd_ok = indicators.macd_histogram > 0 if bullish else indicators.macd_histogram < 0
    momentum = (10 if rsi_ok else 4) + (10 if macd_ok else 2)

    volatility = 15 if indicators.regime == "TREND" else 9 if indicators.regime == "TRANSITION" else 4
    structure_ok = (
        last_close > indicators.bollinger_mid if bullish else last_close < indicators.bollinger_mid
    )
    structure = 10 if structure_ok else 4

    spread_ratio = spread_pips / maximum_spread_pips if maximum_spread_pips > 0 else 1.0
    liquidity = 15 if spread_ratio <= 0.5 else 10 if spread_ratio <= 0.8 else 5
    risk = 20 if risk_reward >= 2.0 else 16 if risk_reward >= 1.5 else 8

    total = max(0, min(100, trend + momentum + volatility + structure + liquidity + risk))
    label = "EXCEPTIONAL" if total >= 92 else "STRONG" if total >= 85 else "WATCH" if total >= 70 else "IGNORE"
    return ScoreBreakdown(trend, momentum, volatility, structure, liquidity, risk, total, label)


def explain_score(score: ScoreBreakdown, indicators, side: str) -> tuple[str, ...]:
    direction = "alta" if side == "BUY" else "baixa"
    reasons = [
        f"Tendência de {direction}: {score.trend}/20",
        f"Momentum: {score.momentum}/20 (RSI {indicators.rsi14:.1f}, MACD hist. {indicators.macd_histogram:.6f})",
        f"Volatilidade/regime: {score.volatility}/15 ({indicators.regime})",
        f"Estrutura: {score.structure}/10",
        f"Liquidez/spread: {score.liquidity}/15",
        f"Risco-retorno: {score.risk}/20",
        f"Orbis Score: {score.total}/100 — {score.label}",
    ]
    return tuple(reasons)
