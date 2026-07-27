#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import html
import json
import os
import secrets
import signal
import socket
import subprocess
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

HOST = "0.0.0.0"
PORT = int(os.environ.get("ORBIS_WEB_PORT", "8080"))
RELEASE_FILE = Path("/etc/orbis-release")
TOKEN_FILE = Path("/etc/orbis-web-token")
JOBS_DIR = Path("/var/lib/orbis/jobs")
SHARED_DIR = Path("/var/lib/orbis/shared")
LOG_FILES = {
    "orbis": Path("/var/log/orbis.log"),
    "core": Path("/var/log/orbis-core.log"),
    "tailscale": Path("/var/log/tailscaled.log"),
}
STARTED_AT = time.time()
MAX_UPLOAD = 25 * 1024 * 1024


def read_text(path: Path, default: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return default


def run(*args: str, timeout: int = 8) -> str:
    try:
        return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=timeout).strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def ensure_runtime() -> str:
    SHARED_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    token = read_text(TOKEN_FILE)
    if len(token) < 24:
        token = secrets.token_urlsafe(24)
        tmp = TOKEN_FILE.with_suffix(".tmp")
        tmp.write_text(token + "\n", encoding="utf-8")
        os.chmod(tmp, 0o600)
        tmp.replace(TOKEN_FILE)
    return token


CONTROL_TOKEN = ensure_runtime()


def release_info() -> dict[str, str]:
    data = {"version": "2.2.0", "commit": "desconhecido"}
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
    link = run("iw", "dev", iface, "link", timeout=3)
    ssid, signal_dbm = "desconectado", "indisponível"
    for line in link.splitlines():
        line = line.strip()
        if line.startswith("SSID:"):
            ssid = line.split(":", 1)[1].strip()
        elif line.startswith("signal:"):
            signal_dbm = line.split(":", 1)[1].strip()
    return {"interface": iface, "ssid": ssid, "signal": signal_dbm}


def ip_addresses() -> list[str]:
    output = run("ip", "-4", "-o", "addr", "show", "scope", "global", timeout=3)
    result: list[str] = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 4:
            result.append(parts[3])
    return result


def tailscale_info() -> dict[str, str]:
    ip = run("tailscale", "ip", "-4", timeout=3).splitlines()
    dns = run("tailscale", "status", "--json", timeout=3)
    name = ""
    if dns:
        try:
            name = json.loads(dns).get("Self", {}).get("DNSName", "").rstrip(".")
        except (json.JSONDecodeError, AttributeError):
            pass
    return {"ip": ip[0] if ip else "", "dns": name}


def jobs_info() -> dict[str, Any]:
    jobs: list[dict[str, Any]] = []
    if JOBS_DIR.exists():
        for path in sorted(JOBS_DIR.glob("*.job")):
            name = path.stem
            jobs.append({"name": name, "enabled": (JOBS_DIR / f"{name}.enabled").exists()})
    return {"total": len(jobs), "active": sum(1 for item in jobs if item["enabled"]), "items": jobs}


def file_info() -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for path in sorted(SHARED_DIR.iterdir(), key=lambda p: p.name.lower()):
        if path.is_file():
            stat = path.stat()
            files.append({"name": path.name, "size": stat.st_size, "modified": int(stat.st_mtime)})
    return files


def status_payload() -> dict[str, Any]:
    total, available = memory_info()
    disk = run("df", "-hP", "/", timeout=3).splitlines()
    disk_value = "indisponível"
    if len(disk) >= 2:
        parts = disk[1].split()
        if len(parts) >= 5:
            disk_value = f"{parts[2]} / {parts[1]} ({parts[4]})"
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
        "load": read_text(Path("/proc/loadavg"), "?").split()[:3],
        "disk": disk_value,
        "wifi": wifi_info(),
        "ips": ip_addresses(),
        "tailscale": tailscale_info(),
        "automations": jobs_info(),
        "files": file_info(),
    }


def dashboard_shell() -> str:
    rel = release_info()
    return f"""<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Orbis OS</title>
<style>
body{{font-family:system-ui,sans-serif;background:#0b0f14;color:#eaf2ff;margin:0;padding:18px}}main{{max-width:900px;margin:auto}}header{{display:flex;justify-content:space-between;align-items:end;border-bottom:1px solid #526070;padding-bottom:14px}}.online{{font-size:28px;color:#8ef0b1}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin-top:18px}}.card{{background:#141b24;border:1px solid #273444;border-radius:12px;padding:16px}}.key{{font-size:12px;color:#93a4b8;text-transform:uppercase}}.value{{font-size:20px;margin-top:6px;word-break:break-word}}button,.button{{background:#26384b;color:#eef6ff;border:1px solid #40556d;border-radius:10px;padding:11px 14px;margin:4px;display:inline-block;text-decoration:none}}button.danger{{background:#4b2528}}input{{background:#0f151d;color:#fff;border:1px solid #40556d;border-radius:8px;padding:10px;max-width:100%}}pre{{white-space:pre-wrap;background:#080b0f;padding:12px;border-radius:8px;max-height:350px;overflow:auto}}.hidden{{display:none}}.warn{{color:#ffd479}}footer{{color:#7f8da0;font-size:12px;margin-top:18px}}
</style></head><body><main><header><div><div class='key'>ORBIS OS</div><div class='online'>ONLINE</div></div><div>v{html.escape(rel['version'])} · {html.escape(rel['commit'])}</div></header>
<div class='grid'><section class='card'><div class='key'>Memória</div><div class='value' id='memory'>carregando…</div></section><section class='card'><div class='key'>Carga</div><div class='value' id='load'>carregando…</div></section><section class='card'><div class='key'>Disco</div><div class='value' id='disk'>carregando…</div></section><section class='card'><div class='key'>Wi-Fi</div><div class='value' id='wifi'>carregando…</div></section><section class='card'><div class='key'>IP remoto</div><div class='value' id='remote'>carregando…</div></section><section class='card'><div class='key'>Automações</div><div class='value' id='jobs'>carregando…</div></section><section class='card'><div class='key'>Relógio</div><div class='value' id='clock'>carregando…</div></section><section class='card'><div class='key'>Host</div><div class='value' id='host'>carregando…</div></section></div>
<section class='card' style='margin-top:14px'><div class='key'>Administração segura</div><p>Digite o token exibido no menu “Acesso remoto”. O token fica somente neste aparelho.</p><input id='token' type='password' placeholder='Token de controle'><button onclick='saveToken()'>Salvar neste navegador</button><div id='controls' class='hidden'><p><button onclick="action('update')">Atualizar Orbis</button><button onclick="action('restart-core')">Reiniciar Core</button><button class='danger' onclick="action('reboot')">Reiniciar computador</button><button class='danger' onclick="action('poweroff')">Desligar</button></p><p><button onclick="loadLog('orbis')">Log Orbis</button><button onclick="loadLog('core')">Log Core</button><button onclick="loadLog('tailscale')">Log remoto</button></p><pre id='log'>Selecione um log.</pre></div></section>
<section class='card' style='margin-top:14px'><div class='key'>Arquivos compartilhados</div><p>Envio limitado a 25 MB por arquivo.</p><input id='upload' type='file'><button onclick='uploadFile()'>Enviar</button><div id='files'></div></section>
<footer id='foot'>Buscando telemetria…</footer></main>
<script>
const tokenInput=document.getElementById('token');tokenInput.value=localStorage.getItem('orbisToken')||'';function saveToken(){{localStorage.setItem('orbisToken',tokenInput.value.trim());showControls();}}function token(){{return localStorage.getItem('orbisToken')||'';}}function showControls(){{document.getElementById('controls').classList.toggle('hidden',!token());}}showControls();
async function refresh(){{try{{const r=await fetch('/api/status?ts='+Date.now(),{{cache:'no-store'}});const d=await r.json();memory.textContent=`${{d.memory.available_mb}} MB livres / ${{d.memory.total_mb}} MB`;load.textContent=(d.load||[]).join(' ');disk.textContent=d.disk;wifi.textContent=`${{d.wifi.ssid}} · ${{d.wifi.signal}}`;remote.textContent=d.tailscale.dns||d.tailscale.ip||'desconectado';jobs.textContent=`${{d.automations.active}} ativas / ${{d.automations.total}}`;clock.textContent=d.time;host.textContent=d.hostname;files.innerHTML=(d.files||[]).map(f=>`<p><a class='button' href='/files/${{encodeURIComponent(f.name)}}'>Baixar</a> ${{f.name}} · ${{Math.ceil(f.size/1024)}} KB <button class='danger' onclick='deleteFile(${{JSON.stringify(f.name)}})'>Excluir</button></p>`).join('')||'<p>Nenhum arquivo.</p>';foot.textContent='Atualizado às '+new Date().toLocaleTimeString();}}catch(e){{foot.textContent='Falha: '+e.message;foot.className='warn';}}}}
async function admin(path,opts={{}}){{opts.headers=Object.assign({{'X-Orbis-Token':token()}},opts.headers||{{}});const r=await fetch(path,opts);const txt=await r.text();if(!r.ok)throw new Error(txt||('HTTP '+r.status));return txt;}}
async function action(name){{if(!confirm('Executar '+name+'?'))return;try{{alert(await admin('/api/action',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{action:name}})}}));}}catch(e){{alert(e.message);}}}}
async function loadLog(name){{try{{log.textContent=await admin('/api/log?name='+encodeURIComponent(name));}}catch(e){{log.textContent=e.message;}}}}
async function uploadFile(){{const f=upload.files[0];if(!f)return;try{{await admin('/api/files?name='+encodeURIComponent(f.name),{{method:'PUT',headers:{{'Content-Type':'application/octet-stream'}},body:f}});upload.value='';refresh();}}catch(e){{alert(e.message);}}}}
async function deleteFile(name){{if(!confirm('Excluir '+name+'?'))return;try{{await admin('/api/files?name='+encodeURIComponent(name),{{method:'DELETE'}});refresh();}}catch(e){{alert(e.message);}}}}
refresh();setInterval(refresh,10000);
</script></body></html>"""


class OrbisHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 16


class Handler(BaseHTTPRequestHandler):
    server_version = "OrbisCore/2.2"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.client_address[0]} - {fmt % args}", flush=True)

    def send_bytes(self, body: bytes, content_type: str, status: int = 200, disposition: str = "") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        if disposition:
            self.send_header("Content-Disposition", disposition)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)
        self.close_connection = True

    def json_response(self, data: Any, status: int = 200) -> None:
        self.send_bytes(json.dumps(data, ensure_ascii=False).encode(), "application/json; charset=utf-8", status)

    def authorized(self) -> bool:
        supplied = self.headers.get("X-Orbis-Token", "")
        return secrets.compare_digest(supplied, CONTROL_TOKEN)

    def require_auth(self) -> bool:
        if self.authorized():
            return True
        self.json_response({"error": "não autorizado"}, 401)
        return False

    def safe_name(self) -> str:
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        name = Path(query.get("name", [""])[0]).name
        return name if name not in ("", ".", "..") else ""

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        path = urllib.parse.urlsplit(self.path).path
        try:
            if path == "/health":
                self.send_bytes(b"ok\n", "text/plain; charset=utf-8")
            elif path in ("/", "/index.html"):
                self.send_bytes(dashboard_shell().encode(), "text/html; charset=utf-8")
            elif path == "/api/status":
                self.json_response(status_payload())
            elif path == "/api/log":
                if not self.require_auth(): return
                name = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("name", [""])[0]
                target = LOG_FILES.get(name)
                if not target: self.send_bytes(b"log invalido\n", "text/plain", 400); return
                lines = read_text(target, "sem log").splitlines()[-250:]
                self.send_bytes(("\n".join(lines)+"\n").encode(), "text/plain; charset=utf-8")
            elif path.startswith("/files/"):
                name = Path(urllib.parse.unquote(path[len("/files/"):])).name
                target = SHARED_DIR / name
                if not target.is_file(): self.send_bytes(b"not found\n", "text/plain", 404); return
                self.send_bytes(target.read_bytes(), "application/octet-stream", disposition=f'attachment; filename="{name}"')
            else:
                self.send_bytes(b"not found\n", "text/plain", 404)
        except Exception as exc:
            self.json_response({"error": type(exc).__name__, "message": str(exc)}, 500)

    def do_PUT(self) -> None:
        if urllib.parse.urlsplit(self.path).path != "/api/files" or not self.require_auth(): return
        name = self.safe_name()
        length = int(self.headers.get("Content-Length", "0") or 0)
        if not name or length < 0 or length > MAX_UPLOAD:
            self.json_response({"error": "arquivo inválido ou maior que 25 MB"}, 400); return
        data = self.rfile.read(length)
        tmp = SHARED_DIR / ("." + hashlib.sha256(name.encode()).hexdigest()[:12] + ".tmp")
        tmp.write_bytes(data); tmp.replace(SHARED_DIR / name)
        self.json_response({"ok": True, "name": name})

    def do_DELETE(self) -> None:
        if urllib.parse.urlsplit(self.path).path != "/api/files" or not self.require_auth(): return
        name = self.safe_name(); target = SHARED_DIR / name
        if not name or not target.is_file(): self.json_response({"error": "arquivo não encontrado"}, 404); return
        target.unlink(); self.json_response({"ok": True})

    def do_POST(self) -> None:
        if urllib.parse.urlsplit(self.path).path != "/api/action" or not self.require_auth(): return
        length = min(int(self.headers.get("Content-Length", "0") or 0), 4096)
        try: action = json.loads(self.rfile.read(length)).get("action", "")
        except json.JSONDecodeError: self.json_response({"error": "json inválido"}, 400); return
        commands = {
            "update": ["/usr/local/bin/orbis-update"],
            "restart-core": ["/usr/local/bin/orbis-web", "--restart"],
            "reboot": ["reboot"],
            "poweroff": ["poweroff"],
        }
        command = commands.get(action)
        if not command: self.json_response({"error": "ação não permitida"}, 400); return
        subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        self.json_response({"ok": True, "message": f"ação {action} iniciada"})


def main() -> None:
    server = OrbisHTTPServer((HOST, PORT), Handler)
    def shutdown(_signum: int, _frame: object) -> None: server.shutdown()
    signal.signal(signal.SIGTERM, shutdown); signal.signal(signal.SIGINT, shutdown)
    print(f"Orbis Core online em http://0.0.0.0:{PORT}", flush=True)
    server.serve_forever(poll_interval=0.5)


if __name__ == "__main__":
    main()
