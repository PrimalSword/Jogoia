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


def parse_ts(raw: str) -> int:
    raw = raw.strip()
    if raw.isdigit():
        value = int(raw)
        return value // 1000 if value > 10_000_000_000 else value
    from datetime import datetime

    normalized = raw.replace("Z", "+00:00")
    return int(datetime.fromisoformat(normalized).timestamp())


def import_csv(conn: sqlite3.Connection, path: Path, symbol: str, timeframe: str) -> int:
    count = 0
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
                    symbol.upper(),
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
        count = len(rows)
    return count


def load_candles(conn: sqlite3.Connection, symbol: str, timeframe: str) -> list[Candle]:
    rows = conn.execute(
        "SELECT * FROM candles WHERE symbol=? AND timeframe=? ORDER BY ts",
        (symbol.upper(), timeframe),
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
    entries = 0
    exits = 0
    wins = 0
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
    closed = exits
    return {
        "strategy": "sma_cross",
        "candles": len(candles),
        "fast": fast,
        "slow": slow,
        "initial_capital": round(initial, 2),
        "final_capital": round(final, 2),
        "return_pct": round((final / initial - 1) * 100, 4),
        "max_drawdown_pct": round(max_drawdown(equity_curve) * 100, 4),
        "entries": entries,
        "closed_trades": closed,
        "win_rate_pct": round((wins / closed * 100) if closed else 0, 2),
        "fee_bps": fee_bps,
        "trades": trades[-50:],
    }


def save_run(conn: sqlite3.Connection, symbol: str, timeframe: str, params: dict, result: dict) -> int:
    with conn:
        cur = conn.execute(
            "INSERT INTO runs(created_at,symbol,timeframe,strategy,params_json,result_json) VALUES(?,?,?,?,?,?)",
            (int(time.time()), symbol.upper(), timeframe, "sma_cross", json.dumps(params), json.dumps(result)),
        )
    return int(cur.lastrowid)


def cmd_status(conn: sqlite3.Connection) -> None:
    symbols = conn.execute(
        "SELECT symbol,timeframe,COUNT(*) candles,MIN(ts) first_ts,MAX(ts) last_ts FROM candles GROUP BY symbol,timeframe ORDER BY symbol,timeframe"
    ).fetchall()
    runs = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    print(json.dumps({"datasets": [dict(row) for row in symbols], "runs": runs}, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Orbis Trade — backtest e replay local, sem ordens reais")
    parser.add_argument("--db", type=Path, default=DB_DEFAULT)
    sub = parser.add_subparsers(dest="command", required=True)

    p_import = sub.add_parser("import-csv", help="Importa OHLCV")
    p_import.add_argument("file", type=Path)
    p_import.add_argument("--symbol", required=True)
    p_import.add_argument("--timeframe", default="1h")

    p_backtest = sub.add_parser("backtest", help="Executa cruzamento de médias")
    p_backtest.add_argument("--symbol", required=True)
    p_backtest.add_argument("--timeframe", default="1h")
    p_backtest.add_argument("--fast", type=int, default=9)
    p_backtest.add_argument("--slow", type=int, default=21)
    p_backtest.add_argument("--capital", type=float, default=10_000.0)
    p_backtest.add_argument("--fee-bps", type=float, default=10.0)

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
            print(json.dumps({"ok": True, "imported": count, "symbol": args.symbol.upper(), "timeframe": args.timeframe}))
        elif args.command == "backtest":
            candles = load_candles(conn, args.symbol, args.timeframe)
            params = {"fast": args.fast, "slow": args.slow, "capital": args.capital, "fee_bps": args.fee_bps}
            result = backtest_sma(candles, args.fast, args.slow, args.capital, args.fee_bps)
            result["run_id"] = save_run(conn, args.symbol, args.timeframe, params, result)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.command == "replay":
            candles = load_candles(conn, args.symbol, args.timeframe)[-args.limit :]
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
