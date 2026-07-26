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


def read_text(path: Path, default: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return default


def run(*args: str) -> str:
    try:
        return subprocess.check_output(
            args,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=2,
        ).strip()
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
            jobs.append(
                {
                    "name": name,
                    "enabled": (JOBS_DIR / f"{name}.enabled").exists(),
                    "mode": mode,
                }
            )
    return {
        "total": len(jobs),
        "active": sum(1 for item in jobs if item["enabled"]),
        "items": jobs,
    }


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


def dashboard_shell() -> str:
    rel = release_info()
    version = html.escape(rel["version"])
    commit = html.escape(rel["commit"])
    return f"""<!doctype html>
<html lang='pt-BR'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Orbis OS</title>
<style>
body{{font-family:system-ui,sans-serif;background:#0b0f14;color:#eaf2ff;margin:0;padding:20px}}
main{{max-width:850px;margin:auto}}
header{{display:flex;justify-content:space-between;align-items:end;border-bottom:1px solid #526070;padding-bottom:14px}}
.online{{font-size:28px;color:#8ef0b1}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin-top:18px}}
.card{{background:#141b24;border:1px solid #273444;border-radius:12px;padding:16px}}
.key{{font-size:12px;color:#93a4b8;text-transform:uppercase}}
.value{{font-size:20px;margin-top:6px;word-break:break-word}}
.warn{{color:#ffd479}}
footer{{color:#7f8da0;font-size:12px;margin-top:18px}}
</style>
</head>
<body>
<main>
<header><div><div class='key'>ORBIS OS</div><div class='online'>ONLINE</div></div><div>v{version} · {commit}</div></header>
<div class='grid'>
<section class='card'><div class='key'>Memória</div><div class='value' id='memory'>carregando…</div></section>
<section class='card'><div class='key'>Carga</div><div class='value' id='load'>carregando…</div></section>
<section class='card'><div class='key'>Disco</div><div class='value' id='disk'>carregando…</div></section>
<section class='card'><div class='key'>Wi-Fi</div><div class='value' id='wifi'>carregando…</div></section>
<section class='card'><div class='key'>IP</div><div class='value' id='ips'>carregando…</div></section>
<section class='card'><div class='key'>Automações</div><div class='value' id='jobs'>carregando…</div></section>
<section class='card'><div class='key'>Relógio</div><div class='value' id='clock'>carregando…</div></section>
<section class='card'><div class='key'>Host</div><div class='value' id='host'>carregando…</div></section>
</div>
<footer id='foot'>Painel carregado. Buscando telemetria…</footer>
</main>
<script>
async function refresh(){{
  const foot=document.getElementById('foot');
  try{{
    const r=await fetch('/api/status?ts='+Date.now(),{{cache:'no-store'}});
    if(!r.ok) throw new Error('HTTP '+r.status);
    const d=await r.json();
    document.getElementById('memory').textContent=`${{d.memory.available_mb}} MB livres / ${{d.memory.total_mb}} MB`;
    document.getElementById('load').textContent=(d.load||[]).join(' ');
    document.getElementById('disk').textContent=d.disk;
    document.getElementById('wifi').textContent=`${{d.wifi.ssid}} · ${{d.wifi.signal}}`;
    document.getElementById('ips').textContent=(d.ips||[]).join(', ')||'desconectado';
    document.getElementById('jobs').textContent=`${{d.automations.active}} ativas / ${{d.automations.total}}`;
    document.getElementById('clock').textContent=d.time;
    document.getElementById('host').textContent=d.hostname;
    foot.textContent='Telemetria atualizada às '+new Date().toLocaleTimeString();
    foot.className='';
  }}catch(e){{
    foot.textContent='Painel aberto, mas a telemetria falhou: '+e.message;
    foot.className='warn';
  }}
}}
refresh(); setInterval(refresh,10000);
</script>
</body>
</html>"""


class OrbisHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 16


class Handler(BaseHTTPRequestHandler):
    server_version = "OrbisCore/2.0.1"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.client_address[0]} - {fmt % args}", flush=True)

    def send_bytes(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Connection", "close")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)
        self.close_connection = True

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        print(f"REQUISIÇÃO {self.client_address[0]} {path}", flush=True)
        try:
            if path == "/health":
                self.send_bytes(b"ok\n", "text/plain; charset=utf-8")
                return
            if path in ("/", "/index.html"):
                self.send_bytes(dashboard_shell().encode("utf-8"), "text/html; charset=utf-8")
                return
            if path == "/api/status":
                payload = status_payload()
                self.send_bytes(
                    json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                    "application/json; charset=utf-8",
                )
                return
            self.send_bytes(b"not found\n", "text/plain; charset=utf-8", 404)
        except (BrokenPipeError, ConnectionResetError):
            print("Cliente encerrou a conexão antes da resposta.", flush=True)
        except Exception as exc:
            print(f"ERRO NA REQUISIÇÃO: {type(exc).__name__}: {exc}", flush=True)
            try:
                body = json.dumps({"error": type(exc).__name__, "message": str(exc)}).encode("utf-8")
                self.send_bytes(body, "application/json; charset=utf-8", 500)
            except Exception:
                pass


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
