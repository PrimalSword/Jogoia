import unittest

from orbis_backtest import evaluate_signal
from orbis_trade import Candle


class TimeExitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.signal = {
            "symbol": "EUR_USD",
            "side": "BUY",
            "entry": 1.1000,
            "stop": 1.0980,
            "target": 1.1030,
        }

    def test_closes_at_market_when_max_bars_is_reached(self) -> None:
        candle = Candle(1_700_000_000, 1.1005, 1.1010, 1.1000, 1.1008)
        result = evaluate_signal(
            self.signal,
            [candle],
            bars_already_held=4,
            max_bars_held=5,
            spread_pips=0.8,
            slippage_pips_per_side=0.1,
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.exit_reason, "TIMEOUT")
        self.assertEqual(result.bars_held, 5)
        self.assertEqual(result.exit_price, 1.1008)
        self.assertAlmostEqual(result.gross_pips, 8.0)
        self.assertAlmostEqual(result.result_pips, 7.0)
        self.assertEqual(result.outcome, "WIN")

    def test_level_exit_has_priority_over_timeout(self) -> None:
        candle = Candle(1_700_000_000, 1.1005, 1.1032, 1.1000, 1.1028)
        result = evaluate_signal(
            self.signal,
            [candle],
            bars_already_held=4,
            max_bars_held=5,
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.exit_reason, "TARGET")
        self.assertEqual(result.exit_price, 1.1030)

    def test_remains_open_before_limit(self) -> None:
        candle = Candle(1_700_000_000, 1.1000, 1.1010, 1.0995, 1.1004)
        result = evaluate_signal(
            self.signal,
            [candle],
            bars_already_held=2,
            max_bars_held=5,
        )
        self.assertIsNone(result)

    def test_rejects_invalid_max_bars(self) -> None:
        candle = Candle(1_700_000_000, 1.1000, 1.1010, 1.0995, 1.1004)
        with self.assertRaises(ValueError):
            evaluate_signal(self.signal, [candle], max_bars_held=0)


if __name__ == "__main__":
    unittest.main()
