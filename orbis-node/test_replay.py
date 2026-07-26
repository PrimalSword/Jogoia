#!/usr/bin/env python3

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from orbis_provider import CsvReplayProvider


class CsvReplayProviderTest(unittest.TestCase):
    def write_csv(self, directory: Path, rows: int = 35) -> Path:
        path = directory / "candles.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=(
                    "timestamp",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "spread_pips",
                ),
            )
            writer.writeheader()
            price = 1.1000
            for index in range(rows):
                close = price + 0.0001
                writer.writerow(
                    {
                        "timestamp": 1_700_000_000 + index * 60,
                        "open": price,
                        "high": close + 0.0001,
                        "low": price - 0.0001,
                        "close": close,
                        "volume": 100 + index,
                        "spread_pips": 0.7,
                    }
                )
                price = close
        return path

    def test_yields_progressive_windows(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = self.write_csv(Path(temp), rows=35)
            provider = CsvReplayProvider(path, "EUR_USD", 1, window_size=30)
            snapshots = list(provider.snapshots())

        self.assertEqual(len(snapshots), 6)
        self.assertEqual(len(snapshots[0].candles), 30)
        self.assertEqual(snapshots[-1].spread_pips, 0.7)
        self.assertEqual(snapshots[-1].source, "csv:candles.csv")

    def test_rejects_short_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = self.write_csv(Path(temp), rows=20)
            provider = CsvReplayProvider(path, "EUR_USD", 1, window_size=30)
            with self.assertRaises(ValueError):
                list(provider.snapshots())


if __name__ == "__main__":
    unittest.main()
