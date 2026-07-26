#!/usr/bin/env python3
"""Persistência SQLite do Orbis Trade, usando apenas biblioteca-padrão."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class SignalStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timeframe_minutes INTEGER NOT NULL,
                    side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
                    entry REAL NOT NULL,
                    stop REAL NOT NULL,
                    target REAL NOT NULL,
                    risk_reward REAL NOT NULL,
                    confidence INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    reasons_json TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT 'paper',
                    status TEXT NOT NULL DEFAULT 'OPEN',
                    exit_price REAL,
                    closed_at TEXT,
                    result_pips REAL,
                    outcome TEXT CHECK (outcome IN ('WIN', 'LOSS', 'BREAKEVEN') OR outcome IS NULL),
                    bars_held INTEGER,
                    ambiguous INTEGER NOT NULL DEFAULT 0,
                    exit_reason TEXT
                )
                """
            )
            columns = {row[1] for row in connection.execute("PRAGMA table_info(signals)")}
            if "bars_held" not in columns:
                connection.execute("ALTER TABLE signals ADD COLUMN bars_held INTEGER")
            if "ambiguous" not in columns:
                connection.execute("ALTER TABLE signals ADD COLUMN ambiguous INTEGER NOT NULL DEFAULT 0")
            if "exit_reason" not in columns:
                connection.execute("ALTER TABLE signals ADD COLUMN exit_reason TEXT")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_signals_created_at ON signals(created_at DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_signals_symbol_timeframe ON signals(symbol, timeframe_minutes)"
            )

    def save_signal(self, signal: dict[str, Any]) -> dict[str, Any]:
        reasons = signal.get("reasons", [])
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO signals (
                    symbol, timeframe_minutes, side, entry, stop, target,
                    risk_reward, confidence, created_at, reasons_json, mode
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(signal["symbol"]), int(signal["timeframe_minutes"]),
                    str(signal["side"]), float(signal["entry"]), float(signal["stop"]),
                    float(signal["target"]), float(signal["risk_reward"]),
                    int(signal["confidence"]), str(signal["created_at"]),
                    json.dumps(reasons, ensure_ascii=False), str(signal.get("mode", "paper")),
                ),
            )
            signal_id = int(cursor.lastrowid)
        stored = dict(signal)
        stored.update({"id": signal_id, "status": "OPEN", "outcome": None})
        return stored

    def close_signal(self, signal_id: int, evaluation: Any) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE signals
                SET status='CLOSED', outcome=?, exit_price=?, closed_at=?,
                    result_pips=?, bars_held=?, ambiguous=?, exit_reason=?
                WHERE id=? AND status='OPEN'
                """,
                (
                    evaluation.outcome, evaluation.exit_price, evaluation.closed_at,
                    evaluation.result_pips, evaluation.bars_held,
                    1 if evaluation.ambiguous else 0, evaluation.exit_reason, int(signal_id),
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError(f"sinal #{signal_id} inexistente ou já fechado")

    def list_signals(self, limit: int = 50) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 500))
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM signals ORDER BY id DESC LIMIT ?", (safe_limit,)
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def summary(self) -> dict[str, Any]:
        with self._connect() as connection:
            aggregate = connection.execute(
                """
                SELECT COUNT(*) total,
                       SUM(CASE WHEN status='OPEN' THEN 1 ELSE 0 END) open_count,
                       SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END) wins,
                       SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END) losses,
                       SUM(CASE WHEN outcome='BREAKEVEN' THEN 1 ELSE 0 END) breakeven,
                       SUM(CASE WHEN ambiguous=1 THEN 1 ELSE 0 END) ambiguous,
                       SUM(CASE WHEN exit_reason='TIMEOUT' THEN 1 ELSE 0 END) timed_out,
                       COALESCE(SUM(result_pips), 0) net_pips,
                       AVG(CASE WHEN status='CLOSED' THEN bars_held END) avg_bars
                FROM signals
                """
            ).fetchone()
        wins = int(aggregate["wins"] or 0)
        losses = int(aggregate["losses"] or 0)
        breakeven = int(aggregate["breakeven"] or 0)
        closed = wins + losses + breakeven
        return {
            "total": int(aggregate["total"] or 0),
            "open": int(aggregate["open_count"] or 0),
            "closed": closed,
            "wins": wins,
            "losses": losses,
            "breakeven": breakeven,
            "ambiguous": int(aggregate["ambiguous"] or 0),
            "timed_out": int(aggregate["timed_out"] or 0),
            "win_rate": round((wins / closed) * 100, 2) if closed else None,
            "net_pips": round(float(aggregate["net_pips"] or 0), 2),
            "average_bars_held": round(float(aggregate["avg_bars"]), 2) if aggregate["avg_bars"] is not None else None,
        }

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["reasons"] = json.loads(data.pop("reasons_json"))
        data["ambiguous"] = bool(data.get("ambiguous", 0))
        return data
