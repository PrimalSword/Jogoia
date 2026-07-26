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
                    outcome TEXT CHECK (outcome IN ('WIN', 'LOSS', 'BREAKEVEN') OR outcome IS NULL)
                )
                """
            )
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
                    str(signal["symbol"]),
                    int(signal["timeframe_minutes"]),
                    str(signal["side"]),
                    float(signal["entry"]),
                    float(signal["stop"]),
                    float(signal["target"]),
                    float(signal["risk_reward"]),
                    int(signal["confidence"]),
                    str(signal["created_at"]),
                    json.dumps(reasons, ensure_ascii=False),
                    str(signal.get("mode", "paper")),
                ),
            )
            signal_id = int(cursor.lastrowid)
        stored = dict(signal)
        stored["id"] = signal_id
        stored["status"] = "OPEN"
        stored["outcome"] = None
        return stored

    def list_signals(self, limit: int = 50) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 500))
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM signals ORDER BY id DESC LIMIT ?", (safe_limit,)
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def summary(self) -> dict[str, Any]:
        with self._connect() as connection:
            total = connection.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
            open_count = connection.execute(
                "SELECT COUNT(*) FROM signals WHERE status = 'OPEN'"
            ).fetchone()[0]
            outcomes = connection.execute(
                """
                SELECT outcome, COUNT(*) AS quantity
                FROM signals
                WHERE outcome IS NOT NULL
                GROUP BY outcome
                """
            ).fetchall()
        by_outcome = {row["outcome"]: row["quantity"] for row in outcomes}
        closed = sum(by_outcome.values())
        wins = int(by_outcome.get("WIN", 0))
        return {
            "total": int(total),
            "open": int(open_count),
            "closed": int(closed),
            "wins": wins,
            "losses": int(by_outcome.get("LOSS", 0)),
            "breakeven": int(by_outcome.get("BREAKEVEN", 0)),
            "win_rate": round((wins / closed) * 100, 2) if closed else None,
        }

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["reasons"] = json.loads(data.pop("reasons_json"))
        return data
