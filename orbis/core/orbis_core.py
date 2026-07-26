#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import os
import signal
import socket
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

HOST = "0.0.0.0"
PORT = int(os.environ.get("ORBIS_WEB_PORT", "8080"))
RELEASE_FILE = Path("/etc/orbis-release")
JOBS_DIR = Path("/var/lib/orbis/jobs")
STARTED_AT = time.time()


class OrbisHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def read_text(path: Path, default: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return default


def run(*args: str) -> str:
    try:
        return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL, timeout=3).strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def release_info() -> dict[str, str]:
    data = {"version": "2.0.1", "commit": "desconhecido"}
    for line in read_text(RELEASE_FILE).splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key == "ORBIS_VERSION":
            data["version"] = value
        elif key == "ORBIS_COMMIT":
            data["commit"] = value[:8]
    return data


def memory_info() -> tuple[int, int]:
    total = available = 0
    for line in read_text(Path("/proc/meminfo")).splitlines():
        if line.startswith("MemTotal:"):
            total = int(line.split()[1]) // 1024
        elif line.startswith("MemAvailable:"):
            available = int(line.split()[1]) // 1024
    return total, available


def wifi_info() -> dict[str, str]:
    iface = ""
    net_dir = Path("/sys/class/net")
    if net_dir.exists():
        for entry in net_dir.iterdir():
            if entry.name.startswith(("wlan", "wlp")):
                iface = entry.name
                break
    if not iface:
        return {"interface": "", "ssid": "desconectado", "signal": "indisponível"}
    link = run("iw", "dev", iface, "link")
    ssid = "desconectado"
    signal_dbm = "indisponível"
    for line in link.splitlines():
        line = line.strip()
        if line.startswith("SSID:"):
            ssid = line.split(":", 1)[1].strip()
        elif line.startswith("signal:"):
            signal_dbm = line.split(":", 1)[1].strip()
    return {"interface": iface, "ssid": ssid, "signal": signal_dbm}


def ip_addresses() -> list[str]:
    output = run("ip", "-4", "-o", "addr", "show", "scope", "global")
    result: list[str] = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 4:
            result.append(parts[3])
    return result


def jobs_info() -> dict[str, Any]:
    jobs: list[dict[str, Any]] = []
    if JOBS_DIR.exists():
        for path in sorted(JOBS_DIR.glob("*.job")):
            name = path.stem
            mode = "manual"
            for line in read_text(path).splitlines():
                if line.startswith("SCHEDULE="):
                    mode = line.split("=", 1)[1].strip().strip("'\"")
                    break
            jobs.append({"name": name, "enabled": (JOBS_DIR / f"{name}.enabled").exists(), "mode": mode})
    return {"total": len(jobs), "active": sum(1 for item in jobs if item["enabled"]), "items": jobs}


def status_payload() -> dict[str, Any]:
    total, available = memory_info()
    disk = run("df", "-hP", "/").splitlines()
    disk_value = "indisponível"
    if len(disk) >= 2:
        parts = disk[1].split()
        if len(parts) >= 5:
            disk_value = f"{parts[2]} / {parts[1]} ({parts[4]})"
    load = read_text(Path("/proc/loadavg"), "?").split()[:3]
    rel = release_info()
    return {
        "status": "online",
        "version": rel["version"],
        "commit": rel["commit"],
        "hostname": socket.gethostname(),
        "time": time.strftime("%d/%m/%Y %H:%M:%S"),
        "uptime_seconds": int(float(read_text(Path("/proc/uptime"), "0").split()[0])),
        "core_uptime_seconds": int(time.time() - STARTED_AT),
        "memory": {"total_mb": total, "available_mb": available},
        "load": load,
        "disk": disk_value,
        "wifi": wifi_info(),
        "ips": ip_addresses(),
        "automations": jobs_info(),
    }


def dashboard(payload: dict[str, Any]) -> str:
    cards = [
        ("Memória", f"{payload['memory']['available_mb']} MB livres / {payload['memory']['total_mb']} MB"),
        ("Carga", " ".join(payload["load"])),
        ("Disco", payload["disk"]),
        ("Wi-Fi", f"{payload['wifi']['ssid']} · {payload['wifi']['signal']}"),
        ("IP", ", ".join(payload["ips"]) or "desconectado"),
        ("Automações", f"{payload['automations']['active']} ativas / {payload['automations']['total']}"),
        ("Relógio", payload["time"]),
        ("Host", payload["hostname"]),
    ]
    cards_html = "".join(
        f'<section class="card"><div class="key">{html.escape(k)}</div><div class="value">{html.escape(str(v))}</div></section>'
        for k, v in cards
    )
    return f"""<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><meta http-equiv='refresh' content='10'><title>Orbis OS</title><style>body{{font-family:system-ui,sans-serif;background:#0b0f14;color:#eaf2ff;margin:0;padding:20px}}main{{max-width:850px;margin:auto}}header{{display:flex;justify-content:space-between;align-items:end;border-bottom:1px solid #526070;padding-bottom:14px}}.online{{font-size:28px;color:#8ef0b1}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin-top:18px}}.card{{background:#141b24;border:1px solid #273444;border-radius:12px;padding:16px}}.key{{font-size:12px;color:#93a4b8;text-transform:uppercase}}.value{{font-size:20px;margin-top:6px;word-break:break-word}}footer{{color:#7f8da0;font-size:12px;margin-top:18px}}</style></head><body><main><header><div><div class='key'>ORBIS OS</div><div class='online'>ONLINE</div></div><div>v{html.escape(payload['version'])} · {html.escape(payload['commit'])}</div></header><div class='grid'>{cards_html}</div><footer>Painel somente leitura · API JSON em /api/status · atualização a cada 10 segundos</footer></main></body></html>"""


class Handler(BaseHTTPRequestHandler):
    server_version = "OrbisCore/2.0.1"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}", flush=True)

    def send_bytes(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        payload = status_payload()
        if self.path in ("/", "/index.html"):
            self.send_bytes(dashboard(payload).encode("utf-8"), "text/html; charset=utf-8")
        elif self.path == "/api/status":
            self.send_bytes(json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        elif self.path == "/health":
            self.send_bytes(b"ok\n", "text/plain; charset=utf-8")
        else:
            self.send_bytes(b"not found\n", "text/plain; charset=utf-8", 404)


def main() -> None:
    server = OrbisHTTPServer((HOST, PORT), Handler)

    def shutdown(_signum: int, _frame: object) -> None:
        server.shutdown()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    print(f"Orbis Core online em http://0.0.0.0:{PORT}", flush=True)
    server.serve_forever(poll_interval=0.5)


if __name__ == "__main__":
    main()
