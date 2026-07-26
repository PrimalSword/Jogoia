#!/usr/bin/env python3
"""Provedores de cotações do Orbis Trade.

A primeira implementação usa replay CSV para testes determinísticos e backtest.
O contrato foi mantido pequeno para permitir futuros adaptadores HTTP, MT5 ou
corretora demo sem alterar o motor de sinais.
"""

from __future__ import annotations

import csv
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from orbis_trade import Candle


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    timeframe_minutes: int
    candles: tuple[Candle, ...]
    spread_pips: float
    source: str


class QuoteProvider(ABC):
    """Contrato mínimo para qualquer fonte de mercado."""

    @abstractmethod
    def snapshots(self) -> Iterator[MarketSnapshot]:
        raise NotImplementedError


class CsvReplayProvider(QuoteProvider):
    """Lê candles de um CSV e produz janelas progressivas para simulação.

    Colunas obrigatórias:
    timestamp,open,high,low,close

    Colunas opcionais:
    volume,spread_pips
    """

    def __init__(
        self,
        csv_path: Path,
        symbol: str,
        timeframe_minutes: int,
        window_size: int = 60,
        default_spread_pips: float = 0.8,
    ) -> None:
        if window_size < 30:
            raise ValueError("window_size deve ser pelo menos 30")
        if timeframe_minutes not in (1, 5):
            raise ValueError("timeframe_minutes deve ser 1 ou 5")
        self.csv_path = csv_path
        self.symbol = symbol
        self.timeframe_minutes = timeframe_minutes
        self.window_size = window_size
        self.default_spread_pips = default_spread_pips

    def _load_rows(self) -> list[tuple[Candle, float]]:
        if not self.csv_path.exists():
            raise FileNotFoundError(self.csv_path)

        rows: list[tuple[Candle, float]] = []
        with self.csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {"timestamp", "open", "high", "low", "close"}
            missing = required.difference(reader.fieldnames or [])
            if missing:
                raise ValueError(f"CSV sem colunas obrigatórias: {sorted(missing)}")

            for line_number, row in enumerate(reader, start=2):
                try:
                    candle = Candle(
                        timestamp=int(row["timestamp"]),
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row.get("volume") or 0.0),
                    )
                    spread = float(row.get("spread_pips") or self.default_spread_pips)
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"CSV inválido na linha {line_number}: {exc}") from exc

                if candle.high < max(candle.open, candle.close):
                    raise ValueError(f"máxima inválida na linha {line_number}")
                if candle.low > min(candle.open, candle.close):
                    raise ValueError(f"mínima inválida na linha {line_number}")
                if spread < 0:
                    raise ValueError(f"spread negativo na linha {line_number}")
                rows.append((candle, spread))

        if len(rows) < self.window_size:
            raise ValueError(
                f"CSV precisa de pelo menos {self.window_size} candles; recebeu {len(rows)}"
            )
        return rows

    def snapshots(self) -> Iterator[MarketSnapshot]:
        rows = self._load_rows()
        for end in range(self.window_size, len(rows) + 1):
            window = rows[end - self.window_size : end]
            yield MarketSnapshot(
                symbol=self.symbol,
                timeframe_minutes=self.timeframe_minutes,
                candles=tuple(item[0] for item in window),
                spread_pips=window[-1][1],
                source=f"csv:{self.csv_path.name}",
            )
