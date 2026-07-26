#!/usr/bin/env python3

import unittest

from orbis_indicators import bollinger, ema, rsi, snapshot
from orbis_score import calculate_score
from orbis_trade import Candle, analyze


def candles(count: int = 220, bullish: bool = True) -> list[Candle]:
    result = []
    price = 1.1000
    for index in range(count):
        drift = 0.00012 if bullish else -0.00012
        open_price = price
        close = price + drift + (0.00002 if index % 3 else -0.00001)
        high = max(open_price, close) + 0.00015
        low = min(open_price, close) - 0.00015
        result.append(Candle(1_700_000_000 + index * 60, open_price, high, low, close, 100 + index))
        price = close
    return result


class IndicatorTests(unittest.TestCase):
    def test_core_indicators(self):
        values = [float(index) for index in range(1, 60)]
        self.assertGreater(ema(values, 9), ema(values, 21))
        self.assertGreaterEqual(rsi(values), 99.0)
        middle, upper, lower = bollinger(values)
        self.assertGreater(upper, middle)
        self.assertLess(lower, middle)

    def test_snapshot_has_long_term_ema(self):
        data = snapshot(candles())
        self.assertIsNotNone(data.ema200)
        self.assertIn(data.regime, {"TREND", "RANGE", "TRANSITION"})

    def test_score_is_bounded(self):
        data = snapshot(candles())
        score = calculate_score(data, "BUY", 0.5, 1.5, 2.0, candles()[-1].close)
        self.assertGreaterEqual(score.total, 0)
        self.assertLessEqual(score.total, 100)

    def test_signal_contains_audit_data(self):
        signal = analyze("EUR_USD", 1, candles(), 0.5, minimum_risk_reward=2.0, minimum_score=0)
        self.assertIsNotNone(signal)
        payload = signal.to_dict()
        self.assertIn("score_breakdown", payload)
        self.assertIn("indicators", payload)
        self.assertIn("setup", payload)
        self.assertIn("regime", payload)


if __name__ == "__main__":
    unittest.main()
