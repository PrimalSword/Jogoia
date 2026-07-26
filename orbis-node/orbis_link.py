#!/usr/bin/env python3
"""Orbis Link: API HTTP leve para Alpine/Atom N455.

Somente biblioteca-padrão. Nesta fase expõe diagnóstico e sinais de paper
trading; não executa shell nem ordens financeiras.
"""

from __future__ import annotations

import json
import os
import platform
import socket
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from orbis_trade import analyze, candles_from_rows

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
STARTED_AT = time.time()
SIGNALS: list[dict[str, Any]] = []


def load_config() -> dict[str, Any]:
    path = CONFIG_PATH if CONFIG_PATH.exists() else ROOT / "config.example.json"
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def memory_status() -> dict[str, int | None]:
    result: dict[str, int | None] = {"total_kb": None, "available_kb": None}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, value = line.split(":", 1)
            if key == "MemTotal":
                result["total_kb"] = int(value.strip().split()[0])
            elif key == "MemAvailable":
                result["available_kb"] = int(value.strip().split()[0])
    except (OSError, ValueError):
        pass
    return result


def local_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("1.1.1.1", 80))
        return str(sock.getsockname()[0])
    except OSError:
        return "indisponível"
    finally:
        sock.close()


def node_status(config: dict[str, Any]) -> dict[str, Any]:
    load_average = None
    try:
        load_average = [round(value, 2) for value in os.getloadavg()]
    except OSError:
        pass
    return {
        "node_name": config.get("node_name", "Orbis Node"),
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "ip": local_ip(),
        "uptime_seconds": int(time.time() - STARTED_AT),
        "load_average": load_average,
        "memory": memory_status(),
        "trade_mode": config.get("trade", {}).get("mode", "paper"),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "OrbisLink/0.1"

    @property
    def config(self) -> dict[str, Any]:
        return self.server.config  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[orbis-link] {self.address_string()} - {fmt % args}")

    def send_json(self, status: int, payload: dict[str, Any] | list[Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def authorized(self) -> bool:
        expected = str(self.config.get("api_token", ""))
        supplied = self.headers.get("Authorization", "")
        return bool(expected) and supplied == f"Bearer {expected}"

    def require_authorization(self) -> bool:
        if self.authorized():
            return True
        self.send_json(401, {"error": "unauthorized"})
        return False

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self.send_json(200, {"status": "ok", "service": "orbis-link"})
            return
        if not self.path.startswith("/api/") or not self.require_authorization():
            if not self.path.startswith("/api/"):
                self.send_json(404, {"error": "not_found"})
            return
        if self.path == "/api/v1/status":
            self.send_json(200, node_status(self.config))
        elif self.path == "/api/v1/trade/signals":
            self.send_json(200, {"signals": SIGNALS[-50:]})
        else:
            self.send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if not self.path.startswith("/api/") or not self.require_authorization():
            if not self.path.startswith("/api/"):
                self.send_json(404, {"error": "not_found"})
            return
        if self.path != "/api/v1/trade/scan":
            self.send_json(404, {"error": "not_found"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 1_000_000:
                raise ValueError("invalid content length")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            trade_config = self.config.get("trade", {})
            signal = analyze(
                symbol=str(payload["symbol"]),
                timeframe_minutes=int(payload["timeframe_minutes"]),
                candles=candles_from_rows(payload["candles"]),
                spread_pips=float(payload["spread_pips"]),
                maximum_spread_pips=float(trade_config.get("maximum_spread_pips", 1.5)),
                minimum_risk_reward=float(trade_config.get("minimum_risk_reward", 1.5)),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self.send_json(400, {"error": "invalid_request", "detail": str(exc)})
            return

        if signal is None:
            self.send_json(200, {"signal": None, "reason": "criteria_not_met"})
            return
        data = signal.to_dict()
        SIGNALS.append(data)
        self.send_json(201, {"signal": data})


def main() -> None:
    config = load_config()
    host = str(config.get("listen_host", "0.0.0.0"))
    port = int(config.get("listen_port", 8765))
    server = ThreadingHTTPServer((host, port), Handler)
    server.config = config  # type: ignore[attr-defined]
    print(f"Orbis Link ativo em http://{host}:{port}")
    print("Modo de negociação: somente paper/análise; nenhuma ordem será enviada.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
