#!/usr/bin/env python3
"""Testes unitários dos custos e desfechos do backtest."""

from __future__ import annotations

import unittest

from orbis_backtest import evaluate_signal, pip_size
from orbis_trade import Candle


class BacktestCostTests(unittest.TestCase):
    def test_buy_target_discounts_spread_and_roundtrip_slippage(self) -> None:
        signal = {
            "symbol": "EUR_USD",
            "side": "BUY",
            "entry": 1.1000,
            "stop": 1.0990,
            "target": 1.1020,
        }
        candle = Candle(timestamp=1_700_000_000, open=1.1000, high=1.1021, low=1.1000, close=1.1020)
        result = evaluate_signal(
            signal,
            [candle],
            spread_pips=0.8,
            slippage_pips_per_side=0.1,
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.outcome, "WIN")
        self.assertEqual(result.gross_pips, 20.0)
        self.assertEqual(result.transaction_cost_pips, 1.0)
        self.assertEqual(result.result_pips, 19.0)

    def test_costs_can_turn_small_profit_into_loss(self) -> None:
        signal = {
            "symbol": "EUR_USD",
            "side": "BUY",
            "entry": 1.1000,
            "stop": 1.0990,
            "target": 1.10005,
        }
        candle = Candle(timestamp=1_700_000_000, open=1.1000, high=1.1001, low=1.1000, close=1.10005)
        result = evaluate_signal(signal, [candle], spread_pips=0.8, slippage_pips_per_side=0.1)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.outcome, "LOSS")
        self.assertEqual(result.result_pips, -0.5)

    def test_jpy_pip_size(self) -> None:
        self.assertEqual(pip_size("USD_JPY"), 0.01)
        self.assertEqual(pip_size("EUR_USD"), 0.0001)

    def test_negative_cost_is_rejected(self) -> None:
        signal = {
            "symbol": "EUR_USD",
            "side": "SELL",
            "entry": 1.1000,
            "stop": 1.1010,
            "target": 1.0990,
        }
        with self.assertRaises(ValueError):
            evaluate_signal(signal, [], spread_pips=-0.1)


if __name__ == "__main__":
    unittest.main()
