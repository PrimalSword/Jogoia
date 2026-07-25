#!/usr/bin/env python3
"""Orbis Core daemon.

Collects local health information with standard-library-only Python and writes an
atomic JSON snapshot for terminal dashboards and future automation modules.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

VERSION = "0.1.0"
STATE_DIR = Path("/var/lib/orbis")
LOG_DIR = Path("/var/log/orbis")
STATE_FILE = STATE_DIR / "status.json"
LOG_FILE = LOG_DIR / "orbisd.log"
INTERVAL_SECONDS = 30


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_text(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return ""


def uptime_seconds() -> int:
    try:
        return int(float(read_text("/proc/uptime").split()[0]))
    except (ValueError, IndexError):
        return 0


def memory() -> dict[str, int]:
    values: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, raw = line.split(":", 1)
            values[key] = int(raw.strip().split()[0]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    total = values.get("MemTotal", 0)
    available = values.get("MemAvailable", values.get("MemFree", 0))
    return {"total_bytes": total, "used_bytes": max(0, total - available), "available_bytes": available}


def cpu_load() -> dict[str, float]:
    try:
        one, five, fifteen = os.getloadavg()
    except OSError:
        one = five = fifteen = 0.0
    return {"load_1m": round(one, 2), "load_5m": round(five, 2), "load_15m": round(fifteen, 2)}


def temperature_c() -> float | None:
    thermal_root = Path("/sys/class/thermal")
    for path in sorted(thermal_root.glob("thermal_zone*/temp")):
        try:
            value = float(path.read_text().strip())
            if value > 1000:
                value /= 1000
            if -20 <= value <= 150:
                return round(value, 1)
        except (OSError, ValueError):
            continue
    return None


def network_ok() -> bool:
    # DNS-independent connectivity check; no data is transmitted beyond TCP setup.
    try:
        with socket.create_connection(("1.1.1.1", 53), timeout=3):
            return True
    except OSError:
        return False


def disk() -> dict[str, int]:
    usage = shutil.disk_usage("/")
    return {"total_bytes": usage.total, "used_bytes": usage.used, "free_bytes": usage.free}


def snapshot() -> dict[str, object]:
    return {
        "orbis_version": VERSION,
        "timestamp_utc": utc_now(),
        "hostname": socket.gethostname(),
        "uptime_seconds": uptime_seconds(),
        "network_ok": network_ok(),
        "cpu": cpu_load(),
        "memory": memory(),
        "disk": disk(),
        "temperature_c": temperature_c(),
        "pid": os.getpid(),
    }


def atomic_write(payload: dict[str, object]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix="status-", suffix=".json", dir=STATE_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_name, STATE_FILE)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def log(message: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(f"{utc_now()} {message}\n")


def main() -> None:
    log(f"Orbis Core {VERSION} started pid={os.getpid()}")
    while True:
        try:
            data = snapshot()
            atomic_write(data)
            log(
                "health "
                f"network={'ok' if data['network_ok'] else 'down'} "
                f"load={data['cpu']['load_1m']}"
            )
        except Exception as exc:  # daemon must survive unexpected probe failures
            log(f"error {type(exc).__name__}: {exc}")
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
