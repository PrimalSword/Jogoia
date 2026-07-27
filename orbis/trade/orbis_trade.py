#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

DB_DEFAULT = Path("/var/lib/orbis/trade/orbis_trade.db")


@dataclass(frozen=True)
class Candle:
    ts: int
    symbol: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: float


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;
        CREATE TABLE IF NOT EXISTS candles (
            ts INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            volume REAL NOT NULL DEFAULT 0,
            PRIMARY KEY (symbol, timeframe, ts)
        );
        CREATE INDEX IF NOT EXISTS idx_candles_lookup
            ON candles(symbol, timeframe, ts);
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            strategy TEXT NOT NULL,
            params_json TEXT NOT NULL,
            result_json TEXT NOT NULL
        );
        """
    )
    return conn


def normalize_symbol(symbol: str) -> str:
    return symbol.upper().replace("/", "").replace("_", "").replace("-", "").strip()


def parse_ts(raw: str) -> int:
    raw = raw.strip()
    if raw.isdigit():
        value = int(raw)
        return value // 1000 if value > 10_000_000_000 else value
    from datetime import datetime

    normalized = raw.replace("Z", "+00:00")
    return int(datetime.fromisoformat(normalized).timestamp())


def import_csv(conn: sqlite3.Connection, path: Path, symbol: str, timeframe: str) -> int:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"timestamp", "open", "high", "low", "close"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError("CSV sem colunas obrigatórias: " + ", ".join(sorted(missing)))
        rows = []
        for row in reader:
            rows.append(
                (
                    parse_ts(row["timestamp"]),
                    normalize_symbol(symbol),
                    timeframe,
                    float(row["open"]),
                    float(row["high"]),
                    float(row["low"]),
                    float(row["close"]),
                    float(row.get("volume") or 0),
                )
            )
        with conn:
            conn.executemany(
                """
                INSERT INTO candles(ts,symbol,timeframe,open,high,low,close,volume)
                VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(symbol,timeframe,ts) DO UPDATE SET
                    open=excluded.open, high=excluded.high, low=excluded.low,
                    close=excluded.close, volume=excluded.volume
                """,
                rows,
            )
        return len(rows)


def load_candles(conn: sqlite3.Connection, symbol: str, timeframe: str) -> list[Candle]:
    rows = conn.execute(
        "SELECT * FROM candles WHERE symbol=? AND timeframe=? ORDER BY ts",
        (normalize_symbol(symbol), timeframe),
    ).fetchall()
    return [Candle(**dict(row)) for row in rows]


def sma(values: list[float], period: int, index: int) -> float | None:
    if index + 1 < period:
        return None
    return statistics.fmean(values[index + 1 - period : index + 1])


def max_drawdown(equity: Iterable[float]) -> float:
    peak = 0.0
    worst = 0.0
    for value in equity:
        peak = max(peak, value)
        if peak > 0:
            worst = max(worst, (peak - value) / peak)
    return worst


def backtest_sma(candles: list[Candle], fast: int, slow: int, initial: float, fee_bps: float) -> dict:
    if fast < 1 or slow <= fast:
        raise ValueError("Use períodos com 1 <= rápida < lenta")
    if len(candles) < slow + 2:
        raise ValueError(f"São necessários pelo menos {slow + 2} candles")

    closes = [c.close for c in candles]
    cash = initial
    qty = 0.0
    entries = exits = wins = 0
    entry_value = 0.0
    equity_curve: list[float] = []
    trades: list[dict] = []
    fee_rate = fee_bps / 10_000

    for i, candle in enumerate(candles):
        fast_now = sma(closes, fast, i)
        slow_now = sma(closes, slow, i)
        fast_prev = sma(closes, fast, i - 1) if i else None
        slow_prev = sma(closes, slow, i - 1) if i else None
        if None not in (fast_now, slow_now, fast_prev, slow_prev):
            crossed_up = fast_prev <= slow_prev and fast_now > slow_now
            crossed_down = fast_prev >= slow_prev and fast_now < slow_now
            if crossed_up and qty == 0 and cash > 0:
                fee = cash * fee_rate
                entry_value = cash
                qty = (cash - fee) / candle.close
                cash = 0.0
                entries += 1
                trades.append({"side": "BUY", "ts": candle.ts, "price": candle.close, "fee": fee})
            elif crossed_down and qty > 0:
                gross = qty * candle.close
                fee = gross * fee_rate
                cash = gross - fee
                pnl = cash - entry_value
                wins += int(pnl > 0)
                qty = 0.0
                exits += 1
                trades.append({"side": "SELL", "ts": candle.ts, "price": candle.close, "fee": fee, "pnl": pnl})
        equity_curve.append(cash + qty * candle.close)

    if qty > 0:
        gross = qty * candles[-1].close
        fee = gross * fee_rate
        cash = gross - fee
        pnl = cash - entry_value
        wins += int(pnl > 0)
        exits += 1
        trades.append({"side": "SELL", "ts": candles[-1].ts, "price": candles[-1].close, "fee": fee, "pnl": pnl, "forced": True})
        equity_curve[-1] = cash

    final = equity_curve[-1]
    return {
        "market": "generic",
        "strategy": "sma_cross",
        "candles": len(candles),
        "fast": fast,
        "slow": slow,
        "initial_capital": round(initial, 2),
        "final_capital": round(final, 2),
        "return_pct": round((final / initial - 1) * 100, 4),
        "max_drawdown_pct": round(max_drawdown(equity_curve) * 100, 4),
        "entries": entries,
        "closed_trades": exits,
        "win_rate_pct": round((wins / exits * 100) if exits else 0, 2),
        "fee_bps": fee_bps,
        "trades": trades[-50:],
    }


def forex_pip_size(symbol: str) -> float:
    return 0.01 if normalize_symbol(symbol).endswith("JPY") else 0.0001


def backtest_forex(
    candles: list[Candle], symbol: str, fast: int, slow: int, initial: float,
    risk_pct: float, stop_pips: float, take_pips: float, spread_pips: float,
    pip_value_per_lot: float, max_lots: float,
) -> dict:
    if fast < 1 or slow <= fast:
        raise ValueError("Use períodos com 1 <= rápida < lenta")
    if len(candles) < slow + 2:
        raise ValueError(f"São necessários pelo menos {slow + 2} candles")
    if not (0 < risk_pct <= 10):
        raise ValueError("Risco por operação deve ficar entre 0 e 10%")
    if stop_pips <= 0 or take_pips <= 0 or pip_value_per_lot <= 0:
        raise ValueError("Stop, alvo e valor do pip precisam ser positivos")

    pip = forex_pip_size(symbol)
    spread = spread_pips * pip
    closes = [c.close for c in candles]
    balance = initial
    equity_curve: list[float] = []
    position: dict | None = None
    trades: list[dict] = []
    wins = losses = 0
    total_pips = 0.0
    gross_profit = gross_loss = 0.0

    def open_position(direction: str, candle: Candle) -> dict:
        nonlocal balance
        risk_amount = balance * risk_pct / 100
        lots = min(max_lots, risk_amount / (stop_pips * pip_value_per_lot))
        lots = max(0.01, round(lots, 2))
        entry = candle.close + spread if direction == "LONG" else candle.close
        stop = entry - stop_pips * pip if direction == "LONG" else entry + stop_pips * pip
        take = entry + take_pips * pip if direction == "LONG" else entry - take_pips * pip
        return {"direction": direction, "entry": entry, "stop": stop, "take": take, "lots": lots, "opened_ts": candle.ts}

    def close_position(candle: Candle, exit_price: float, reason: str) -> None:
        nonlocal position, balance, wins, losses, total_pips, gross_profit, gross_loss
        assert position is not None
        direction = position["direction"]
        effective_exit = exit_price if direction == "LONG" else exit_price + spread
        pips = ((effective_exit - position["entry"]) / pip) * (1 if direction == "LONG" else -1)
        pnl = pips * pip_value_per_lot * position["lots"]
        balance += pnl
        total_pips += pips
        if pnl > 0:
            wins += 1
            gross_profit += pnl
        else:
            losses += 1
            gross_loss += abs(pnl)
        trades.append({
            "side": direction,
            "opened_ts": position["opened_ts"],
            "ts": candle.ts,
            "entry": round(position["entry"], 6),
            "price": round(effective_exit, 6),
            "lots": position["lots"],
            "pips": round(pips, 2),
            "pnl": round(pnl, 2),
            "reason": reason,
        })
        position = None

    for i, candle in enumerate(candles):
        fast_now = sma(closes, fast, i)
        slow_now = sma(closes, slow, i)
        fast_prev = sma(closes, fast, i - 1) if i else None
        slow_prev = sma(closes, slow, i - 1) if i else None

        if position:
            if position["direction"] == "LONG":
                if candle.low <= position["stop"]:
                    close_position(candle, position["stop"], "STOP")
                elif candle.high >= position["take"]:
                    close_position(candle, position["take"], "TAKE")
            else:
                ask_high = candle.high + spread
                ask_low = candle.low + spread
                if ask_high >= position["stop"]:
                    close_position(candle, position["stop"] - spread, "STOP")
                elif ask_low <= position["take"]:
                    close_position(candle, position["take"] - spread, "TAKE")

        if None not in (fast_now, slow_now, fast_prev, slow_prev):
            crossed_up = fast_prev <= slow_prev and fast_now > slow_now
            crossed_down = fast_prev >= slow_prev and fast_now < slow_now
            if position and ((crossed_up and position["direction"] == "SHORT") or (crossed_down and position["direction"] == "LONG")):
                close_position(candle, candle.close, "SIGNAL")
            if position is None:
                if crossed_up:
                    position = open_position("LONG", candle)
                elif crossed_down:
                    position = open_position("SHORT", candle)

        floating = 0.0
        if position:
            mark = candle.close if position["direction"] == "LONG" else candle.close + spread
            floating_pips = ((mark - position["entry"]) / pip) * (1 if position["direction"] == "LONG" else -1)
            floating = floating_pips * pip_value_per_lot * position["lots"]
        equity_curve.append(balance + floating)

    if position:
        close_position(candles[-1], candles[-1].close, "FIM_DADOS")
        equity_curve[-1] = balance

    closed = wins + losses
    profit_factor = gross_profit / gross_loss if gross_loss else (999.0 if gross_profit else 0.0)
    return {
        "market": "forex",
        "strategy": "forex_sma_risk",
        "symbol": normalize_symbol(symbol),
        "candles": len(candles),
        "fast": fast,
        "slow": slow,
        "initial_capital": round(initial, 2),
        "final_capital": round(balance, 2),
        "return_pct": round((balance / initial - 1) * 100, 4),
        "max_drawdown_pct": round(max_drawdown(equity_curve) * 100, 4),
        "closed_trades": closed,
        "win_rate_pct": round((wins / closed * 100) if closed else 0, 2),
        "profit_factor": round(profit_factor, 3),
        "net_pips": round(total_pips, 2),
        "risk_pct": risk_pct,
        "stop_pips": stop_pips,
        "take_pips": take_pips,
        "spread_pips": spread_pips,
        "pip_size": pip,
        "pip_value_per_lot": pip_value_per_lot,
        "account_currency_assumption": "moeda de cotação",
        "trades": trades[-100:],
    }


def save_run(conn: sqlite3.Connection, symbol: str, timeframe: str, strategy: str, params: dict, result: dict) -> int:
    with conn:
        cur = conn.execute(
            "INSERT INTO runs(created_at,symbol,timeframe,strategy,params_json,result_json) VALUES(?,?,?,?,?,?)",
            (int(time.time()), normalize_symbol(symbol), timeframe, strategy, json.dumps(params), json.dumps(result)),
        )
    return int(cur.lastrowid)


def cmd_status(conn: sqlite3.Connection) -> None:
    symbols = conn.execute(
        "SELECT symbol,timeframe,COUNT(*) candles,MIN(ts) first_ts,MAX(ts) last_ts FROM candles GROUP BY symbol,timeframe ORDER BY symbol,timeframe"
    ).fetchall()
    runs = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    print(json.dumps({"datasets": [dict(row) for row in symbols], "runs": runs}, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Orbis Trade — laboratório local de Forex e backtest, sem ordens reais")
    parser.add_argument("--db", type=Path, default=DB_DEFAULT)
    sub = parser.add_subparsers(dest="command", required=True)

    p_import = sub.add_parser("import-csv", help="Importa OHLCV normalizado")
    p_import.add_argument("file", type=Path)
    p_import.add_argument("--symbol", required=True)
    p_import.add_argument("--timeframe", default="1h")

    p_backtest = sub.add_parser("backtest", help="Executa cruzamento de médias genérico")
    p_backtest.add_argument("--symbol", required=True)
    p_backtest.add_argument("--timeframe", default="1h")
    p_backtest.add_argument("--fast", type=int, default=9)
    p_backtest.add_argument("--slow", type=int, default=21)
    p_backtest.add_argument("--capital", type=float, default=10_000.0)
    p_backtest.add_argument("--fee-bps", type=float, default=10.0)

    p_forex = sub.add_parser("forex-backtest", help="Backtest Forex com pips, spread, stop, alvo e lote por risco")
    p_forex.add_argument("--symbol", required=True)
    p_forex.add_argument("--timeframe", default="1h")
    p_forex.add_argument("--fast", type=int, default=9)
    p_forex.add_argument("--slow", type=int, default=21)
    p_forex.add_argument("--capital", type=float, default=10_000.0)
    p_forex.add_argument("--risk-pct", type=float, default=1.0)
    p_forex.add_argument("--stop-pips", type=float, default=30.0)
    p_forex.add_argument("--take-pips", type=float, default=60.0)
    p_forex.add_argument("--spread-pips", type=float, default=1.0)
    p_forex.add_argument("--pip-value", type=float, default=10.0, help="Valor monetário do pip por lote padrão")
    p_forex.add_argument("--max-lots", type=float, default=10.0)

    p_replay = sub.add_parser("replay", help="Reproduz candles no terminal")
    p_replay.add_argument("--symbol", required=True)
    p_replay.add_argument("--timeframe", default="1h")
    p_replay.add_argument("--delay", type=float, default=0.1)
    p_replay.add_argument("--limit", type=int, default=100)

    sub.add_parser("status", help="Mostra bases e execuções")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    conn = connect(args.db)
    try:
        if args.command == "import-csv":
            count = import_csv(conn, args.file, args.symbol, args.timeframe)
            print(json.dumps({"ok": True, "imported": count, "symbol": normalize_symbol(args.symbol), "timeframe": args.timeframe}))
        elif args.command == "backtest":
            candles = load_candles(conn, args.symbol, args.timeframe)
            params = {"fast": args.fast, "slow": args.slow, "capital": args.capital, "fee_bps": args.fee_bps}
            result = backtest_sma(candles, args.fast, args.slow, args.capital, args.fee_bps)
            result["run_id"] = save_run(conn, args.symbol, args.timeframe, "sma_cross", params, result)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.command == "forex-backtest":
            candles = load_candles(conn, args.symbol, args.timeframe)
            params = {
                "fast": args.fast, "slow": args.slow, "capital": args.capital,
                "risk_pct": args.risk_pct, "stop_pips": args.stop_pips,
                "take_pips": args.take_pips, "spread_pips": args.spread_pips,
                "pip_value": args.pip_value, "max_lots": args.max_lots,
            }
            result = backtest_forex(
                candles, args.symbol, args.fast, args.slow, args.capital,
                args.risk_pct, args.stop_pips, args.take_pips, args.spread_pips,
                args.pip_value, args.max_lots,
            )
            result["run_id"] = save_run(conn, args.symbol, args.timeframe, "forex_sma_risk", params, result)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.command == "replay":
            candles = load_candles(conn, args.symbol, args.timeframe)[-args.limit:]
            for candle in candles:
                print(json.dumps(candle.__dict__, ensure_ascii=False), flush=True)
                time.sleep(max(0, args.delay))
        else:
            cmd_status(conn)
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
