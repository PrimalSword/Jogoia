from orbis_backtest import evaluate_signal, pip_size
from orbis_trade import Candle


def signal(side="BUY"):
    return {
        "symbol": "EUR_USD",
        "side": side,
        "entry": 1.1000,
        "stop": 1.0990 if side == "BUY" else 1.1010,
        "target": 1.1015 if side == "BUY" else 1.0985,
    }


def test_buy_target():
    result = evaluate_signal(signal(), [Candle(1_700_000_000, 1.1000, 1.1016, 1.0995, 1.1010)])
    assert result is not None
    assert result.outcome == "WIN"
    assert result.result_pips == 15.0


def test_sell_stop():
    result = evaluate_signal(signal("SELL"), [Candle(1_700_000_000, 1.1000, 1.1012, 1.0995, 1.1008)])
    assert result is not None
    assert result.outcome == "LOSS"
    assert result.result_pips == -10.0


def test_ambiguous_is_conservative_by_default():
    result = evaluate_signal(signal(), [Candle(1_700_000_000, 1.1000, 1.1020, 1.0980, 1.1005)])
    assert result is not None
    assert result.outcome == "LOSS"
    assert result.ambiguous is True


def test_unresolved_signal():
    result = evaluate_signal(signal(), [Candle(1_700_000_000, 1.1000, 1.1008, 1.0994, 1.1002)])
    assert result is None


def test_jpy_pip_size():
    assert pip_size("USD_JPY") == 0.01
