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
EVENTS_FILE = Path("/var/log/orbis-events.log")
REPO_DIR = Path("/opt/orbis-src")
LOG_FILES = {
    "orbis": Path("/var/log/orbis.log"),
    "core": Path("/var/log/orbis-core.log"),
    "tailscale": Path("/var/log/tailscaled.log"),
    "events": EVENTS_FILE,
}
STARTED_AT = time.time()
MAX_UPLOAD = 25 * 1024 * 1024
MAX_TEXT_EDIT = 512 * 1024
ALLOWED_TEXT_SUFFIXES = {".txt", ".md", ".json", ".csv", ".log", ".conf", ".ini", ".yaml", ".yml", ".sh", ".py"}
MAX_TERMINAL_COMMAND = 8192
MAX_TERMINAL_OUTPUT = 128 * 1024
TERMINAL_TIMEOUT = 30
TERMINAL_SHELL = "/bin/sh"


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


def event(message: str) -> None:
    try:
        EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with EVENTS_FILE.open("a", encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except OSError:
        pass


def ensure_runtime() -> str:
    SHARED_DIR.mkdir(parents=True, exist_ok=True)
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
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
    data = {"version": "2.4.0", "commit": "desconhecido"}
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


def cpu_info() -> dict[str, Any]:
    load = read_text(Path("/proc/loadavg"), "?").split()[:3]
    model = ""
    for line in read_text(Path("/proc/cpuinfo")).splitlines():
        if line.lower().startswith("model name"):
            model = line.split(":", 1)[1].strip()
            break
    temp = None
    for path in Path("/sys/class/thermal").glob("thermal_zone*/temp"):
        raw = read_text(path)
        if raw.isdigit():
            value = int(raw)
            temp = round(value / 1000 if value >= 1000 else value, 1)
            break
    return {"model": model or os.uname().machine, "load": load, "temperature_c": temp}


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
    state = "desconectado"
    if dns:
        try:
            parsed = json.loads(dns)
            name = parsed.get("Self", {}).get("DNSName", "").rstrip(".")
            state = parsed.get("BackendState", "desconhecido")
        except (json.JSONDecodeError, AttributeError):
            pass
    return {"ip": ip[0] if ip else "", "dns": name, "state": state}


def jobs_info() -> dict[str, Any]:
    jobs: list[dict[str, Any]] = []
    if JOBS_DIR.exists():
        for path in sorted(JOBS_DIR.glob("*.job")):
            name = path.stem
            schedule = "manual"
            for line in read_text(path).splitlines():
                if line.startswith("SCHEDULE="):
                    schedule = line.split("=", 1)[1].strip().strip("'\"")
                    break
            jobs.append({"name": name, "enabled": (JOBS_DIR / f"{name}.enabled").exists(), "schedule": schedule})
    return {"total": len(jobs), "active": sum(1 for item in jobs if item["enabled"]), "items": jobs}


def file_info() -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for path in sorted(SHARED_DIR.iterdir(), key=lambda p: p.name.lower()):
        if path.is_file():
            stat = path.stat()
            files.append({"name": path.name, "size": stat.st_size, "modified": int(stat.st_mtime), "editable": path.suffix.lower() in ALLOWED_TEXT_SUFFIXES and stat.st_size <= MAX_TEXT_EDIT})
    return files


def git_info() -> dict[str, Any]:
    if not (REPO_DIR / ".git").exists():
        return {"available": False, "branch": "", "local": "", "remote": "", "behind": None, "dirty": False}
    branch = run("git", "-C", str(REPO_DIR), "rev-parse", "--abbrev-ref", "HEAD", timeout=3)
    local = run("git", "-C", str(REPO_DIR), "rev-parse", "--short", "HEAD", timeout=3)
    remote = run("git", "-C", str(REPO_DIR), "rev-parse", "--short", "origin/main", timeout=3)
    dirty = bool(run("git", "-C", str(REPO_DIR), "status", "--porcelain", timeout=3))
    behind_raw = run("git", "-C", str(REPO_DIR), "rev-list", "--count", "HEAD..origin/main", timeout=3)
    return {"available": True, "branch": branch, "local": local, "remote": remote, "behind": int(behind_raw) if behind_raw.isdigit() else None, "dirty": dirty}


def process_info() -> list[dict[str, str]]:
    output = run("ps", "-eo", "pid,comm,pcpu,pmem", "--sort=-pcpu", timeout=4)
    items: list[dict[str, str]] = []
    for line in output.splitlines()[1:11]:
        parts = line.split(None, 3)
        if len(parts) == 4:
            items.append({"pid": parts[0], "name": parts[1], "cpu": parts[2], "memory": parts[3]})
    if items:
        return items
    output = run("ps", timeout=4)
    for line in output.splitlines()[1:11]:
        parts = line.split(None, 4)
        if len(parts) >= 4:
            items.append({"pid": parts[0], "name": parts[-1], "cpu": "?", "memory": "?"})
    return items


def status_payload() -> dict[str, Any]:
    total, available = memory_info()
    disk = run("df", "-hP", "/", timeout=3).splitlines()
    disk_value = "indisponível"
    if len(disk) >= 2:
        parts = disk[1].split()
        if len(parts) >= 5:
            disk_value = f"{parts[2]} / {parts[1]} ({parts[4]})"
    rel = release_info()
    return {"status": "online", "version": rel["version"], "commit": rel["commit"], "hostname": socket.gethostname(), "time": time.strftime("%d/%m/%Y %H:%M:%S"), "uptime_seconds": int(float(read_text(Path("/proc/uptime"), "0").split()[0])), "core_uptime_seconds": int(time.time() - STARTED_AT), "memory": {"total_mb": total, "available_mb": available}, "cpu": cpu_info(), "disk": disk_value, "wifi": wifi_info(), "ips": ip_addresses(), "tailscale": tailscale_info(), "git": git_info(), "automations": jobs_info(), "files": file_info(), "processes": process_info(), "events": read_text(EVENTS_FILE, "sem eventos").splitlines()[-20:]}


def dashboard_shell() -> str:
    rel = release_info()
    return f"""<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Orbis OS</title>
<style>
body{{font-family:system-ui,sans-serif;background:#0b0f14;color:#eaf2ff;margin:0;padding:16px}}main{{max-width:980px;margin:auto}}header{{display:flex;justify-content:space-between;align-items:end;border-bottom:1px solid #526070;padding-bottom:14px}}.online{{font-size:28px;color:#8ef0b1}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin-top:18px}}.card{{background:#141b24;border:1px solid #273444;border-radius:12px;padding:16px;margin-top:14px}}.key{{font-size:12px;color:#93a4b8;text-transform:uppercase}}.value{{font-size:20px;margin-top:6px;word-break:break-word}}button,.button{{background:#26384b;color:#eef6ff;border:1px solid #40556d;border-radius:10px;padding:11px 14px;margin:4px;display:inline-block;text-decoration:none}}button.danger{{background:#4b2528}}button.good{{background:#1f4b37}}input,textarea,select{{background:#0f151d;color:#fff;border:1px solid #40556d;border-radius:8px;padding:10px;max-width:100%;box-sizing:border-box}}textarea{{width:100%;min-height:220px;font-family:monospace}}pre{{white-space:pre-wrap;background:#080b0f;padding:12px;border-radius:8px;max-height:350px;overflow:auto}}table{{width:100%;border-collapse:collapse}}td,th{{padding:8px;border-bottom:1px solid #273444;text-align:left}}.hidden{{display:none}}.warn{{color:#ffd479}}.ok{{color:#8ef0b1}}footer{{color:#7f8da0;font-size:12px;margin-top:18px}}.terminal{{background:#080b0f;border:1px solid #273444;border-radius:10px;padding:12px;font-family:monospace}}.terminal input{{width:100%;font-family:monospace;box-sizing:border-box;margin:4px 0}}.terminal-output{{min-height:180px;max-height:420px;overflow:auto;white-space:pre-wrap;color:#d7e3ef;margin-top:10px}}
</style></head><body><main><header><div><div class='key'>ORBIS OS</div><div class='online'>ONLINE</div></div><div>v{html.escape(rel['version'])} · {html.escape(rel['commit'])}</div></header>
<div class='grid'><section class='card'><div class='key'>Memória</div><div class='value' id='memory'>carregando…</div></section><section class='card'><div class='key'>CPU / carga</div><div class='value' id='cpu'>carregando…</div></section><section class='card'><div class='key'>Temperatura</div><div class='value' id='temperature'>carregando…</div></section><section class='card'><div class='key'>Disco</div><div class='value' id='disk'>carregando…</div></section><section class='card'><div class='key'>Wi-Fi</div><div class='value' id='wifi'>carregando…</div></section><section class='card'><div class='key'>Acesso remoto</div><div class='value' id='remote'>carregando…</div></section><section class='card'><div class='key'>Git</div><div class='value' id='git'>carregando…</div></section><section class='card'><div class='key'>Uptime</div><div class='value' id='uptime'>carregando…</div></section></div>
<section class='card'><div class='key'>Administração segura</div><p>Digite o token exibido no menu “Acesso remoto”. O token fica somente neste aparelho.</p><input id='token' type='password' placeholder='Token de controle'><button onclick='saveToken()'>Salvar neste navegador</button><div id='controls' class='hidden'><p><button class='good' onclick="action('update')">Atualizar Orbis</button><button onclick="action('restart-core')">Reiniciar Core</button><button onclick="action('restart-remote')">Reparar remoto</button><button onclick="action('sync-time')">Sincronizar relógio</button></p><p><button class='danger' onclick="action('reboot')">Reiniciar computador</button><button class='danger' onclick="action('poweroff')">Desligar</button></p><p><button onclick="loadLog('orbis')">Log Orbis</button><button onclick="loadLog('core')">Log Core</button><button onclick="loadLog('tailscale')">Log remoto</button><button onclick="loadLog('events')">Eventos</button></p><pre id='log'>Selecione um log.</pre></div></section>
<section class='card'><div class='key'>Terminal remoto</div><p>Execute comandos diretamente no Orbis. A sessão usa o mesmo token de administração e permanece limitada à rede privada.</p><div id='terminalBox' class='terminal'><input id='terminalCwd' value='/opt/orbis-src' placeholder='Diretório de trabalho'><input id='terminalCommand' placeholder='Digite um comando…' onkeydown="if(event.key==='Enter')executeTerminal()"><p><button class='good' onclick='executeTerminal()'>Executar</button><button onclick='clearTerminal()'>Limpar</button><button onclick='repeatLastCommand()'>Repetir último</button></p><pre id='terminalOutput' class='terminal-output'>Terminal pronto.</pre></div></section>
<section class='card'><div class='key'>Automações</div><div id='automationList'>carregando…</div></section><section class='card'><div class='key'>Processos</div><div id='processList'>carregando…</div></section><section class='card'><div class='key'>Arquivos compartilhados</div><p>Envio limitado a 25 MB por arquivo. Arquivos de texto de até 512 KB podem ser editados.</p><input id='upload' type='file'><button onclick='uploadFile()'>Enviar</button><div id='files'></div><div id='editorBox' class='hidden'><h3 id='editorTitle'></h3><textarea id='editor'></textarea><p><button class='good' onclick='saveEdit()'>Salvar arquivo</button><button onclick='closeEdit()'>Fechar</button></p></div></section><section class='card'><div class='key'>Comandos rápidos seguros</div><p>Executa apenas comandos pré-aprovados.</p><select id='quick'><option value='status'>Status completo</option><option value='network'>Rede</option><option value='disk'>Disco</option><option value='memory'>Memória</option><option value='tailscale'>Tailscale</option><option value='git'>Git</option></select><button onclick='quickCommand()'>Executar</button><pre id='quickOut'>Selecione um comando.</pre></section><footer id='foot'>Buscando telemetria…</footer></main>
<script>
const tokenInput=document.getElementById('token');tokenInput.value=localStorage.getItem('orbisToken')||'';let editing='';function saveToken(){{localStorage.setItem('orbisToken',tokenInput.value.trim());showControls();}}function token(){{return localStorage.getItem('orbisToken')||'';}}function showControls(){{document.getElementById('controls').classList.toggle('hidden',!token());}}showControls();function fmtUptime(s){{const d=Math.floor(s/86400),h=Math.floor((s%86400)/3600),m=Math.floor((s%3600)/60);return (d?d+'d ':'')+(h?h+'h ':'')+m+'m';}}
async function refresh(){{try{{const r=await fetch('/api/status?ts='+Date.now(),{{cache:'no-store'}});const d=await r.json();memory.textContent=`${{d.memory.available_mb}} MB livres / ${{d.memory.total_mb}} MB`;cpu.textContent=(d.cpu.load||[]).join(' ')+' · '+d.cpu.model;temperature.textContent=d.cpu.temperature_c==null?'indisponível':d.cpu.temperature_c+' °C';disk.textContent=d.disk;wifi.textContent=`${{d.wifi.ssid}} · ${{d.wifi.signal}}`;remote.textContent=d.tailscale.dns||d.tailscale.ip||'desconectado';git.textContent=d.git.available?`${{d.git.branch}} · ${{d.git.local}}${{d.git.behind>0?' · '+d.git.behind+' atualização(ões)':' · atualizado'}}`:'indisponível';uptime.textContent=fmtUptime(d.uptime_seconds);automationList.innerHTML=(d.automations.items||[]).map(j=>`<p><b>${{j.name}}</b> · ${{j.schedule}} · ${{j.enabled?'ativa':'inativa'}} <button onclick="job('${{encodeURIComponent(j.name)}}','toggle')">Ativar/desativar</button><button onclick="job('${{encodeURIComponent(j.name)}}','run')">Executar</button></p>`).join('')||'<p>Nenhuma automação.</p>';processList.innerHTML='<table><tr><th>PID</th><th>Processo</th><th>CPU</th><th>RAM</th></tr>'+(d.processes||[]).map(p=>`<tr><td>${{p.pid}}</td><td>${{p.name}}</td><td>${{p.cpu}}</td><td>${{p.memory}}</td></tr>`).join('')+'</table>';files.innerHTML=(d.files||[]).map(f=>`<p><a class='button' href='/files/${{encodeURIComponent(f.name)}}'>Baixar</a> ${{f.name}} · ${{Math.ceil(f.size/1024)}} KB ${{f.editable?`<button onclick="editFile(${{JSON.stringify(f.name)}})">Editar</button>`:''}} <button class='danger' onclick='deleteFile(${{JSON.stringify(f.name)}})'>Excluir</button></p>`).join('')||'<p>Nenhum arquivo.</p>';foot.textContent='Atualizado às '+new Date().toLocaleTimeString();foot.className='';}}catch(e){{foot.textContent='Falha: '+e.message;foot.className='warn';}}}}
async function admin(path,opts={{}}){{opts.headers=Object.assign({{'X-Orbis-Token':token()}},opts.headers||{{}});const r=await fetch(path,opts);const txt=await r.text();if(!r.ok)throw new Error(txt||('HTTP '+r.status));return txt;}}async function action(name){{if(!confirm('Executar '+name+'?'))return;try{{alert(await admin('/api/action',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{action:name}})}}));}}catch(e){{alert(e.message);}}}}async function loadLog(name){{try{{log.textContent=await admin('/api/log?name='+encodeURIComponent(name));}}catch(e){{log.textContent=e.message;}}}}async function uploadFile(){{const f=upload.files[0];if(!f)return;try{{await admin('/api/files?name='+encodeURIComponent(f.name),{{method:'PUT',headers:{{'Content-Type':'application/octet-stream'}},body:f}});upload.value='';refresh();}}catch(e){{alert(e.message);}}}}async function deleteFile(name){{if(!confirm('Excluir '+name+'?'))return;try{{await admin('/api/files?name='+encodeURIComponent(name),{{method:'DELETE'}});refresh();}}catch(e){{alert(e.message);}}}}async function editFile(name){{try{{editing=name;editorTitle.textContent=name;editor.value=await admin('/api/file-text?name='+encodeURIComponent(name));editorBox.classList.remove('hidden');}}catch(e){{alert(e.message);}}}}function closeEdit(){{editing='';editorBox.classList.add('hidden');}}async function saveEdit(){{try{{await admin('/api/file-text?name='+encodeURIComponent(editing),{{method:'PUT',headers:{{'Content-Type':'text/plain; charset=utf-8'}},body:editor.value}});alert('Arquivo salvo.');refresh();}}catch(e){{alert(e.message);}}}}async function job(name,op){{try{{alert(await admin('/api/job',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{name:decodeURIComponent(name),operation:op}})}}));refresh();}}catch(e){{alert(e.message);}}}}async function quickCommand(){{try{{quickOut.textContent=await admin('/api/quick?name='+encodeURIComponent(quick.value));}}catch(e){{quickOut.textContent=e.message;}}}}
function terminalHistory(){{try{{return JSON.parse(localStorage.getItem('orbisTerminalHistory')||'[]');}}catch(e){{return [];}}}}function saveTerminalCommand(command){{const h=terminalHistory().filter(x=>x!==command);h.unshift(command);localStorage.setItem('orbisTerminalHistory',JSON.stringify(h.slice(0,50)));}}function repeatLastCommand(){{const h=terminalHistory();if(h.length){{terminalCommand.value=h[0];executeTerminal();}}}}function clearTerminal(){{terminalOutput.textContent='';}}async function executeTerminal(){{const command=terminalCommand.value.trim();const cwd=terminalCwd.value.trim()||'/opt/orbis-src';if(!command){{terminalOutput.textContent='Digite um comando.';return;}}saveTerminalCommand(command);terminalOutput.textContent='Executando…\n\n$ '+command+'\n';try{{const raw=await admin('/api/terminal/exec',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{command,cwd}})}});const data=JSON.parse(raw);terminalOutput.textContent='$ '+command+'\n\n'+(data.output||data.error||'')+'\n\n[shell '+(data.shell||'?')+' · exit '+(data.exit_code??'?')+' · '+(data.duration_ms??'?')+' ms]';}}catch(e){{terminalOutput.textContent='Falha: '+e.message;}}}}
refresh();setInterval(refresh,10000);
</script></body></html>"""


class OrbisHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 16


class Handler(BaseHTTPRequestHandler):
    server_version = "OrbisCore/2.5.1"
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
        return secrets.compare_digest(self.headers.get("X-Orbis-Token", ""), CONTROL_TOKEN)

    def require_auth(self) -> bool:
        if self.authorized():
            return True
        self.json_response({"error": "não autorizado"}, 401)
        return False

    def query(self) -> dict[str, list[str]]:
        return urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)

    def safe_name(self) -> str:
        name = Path(self.query().get("name", [""])[0]).name
        return name if name not in ("", ".", "..") else ""

    def read_json(self, limit: int = 8192) -> dict[str, Any]:
        length = min(int(self.headers.get("Content-Length", "0") or 0), limit)
        try:
            value = json.loads(self.rfile.read(length))
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            return {}

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
            elif path == "/api/terminal/status":
                if not self.require_auth():
                    return
                self.json_response({"status": "online", "shell": TERMINAL_SHELL, "timeout_seconds": TERMINAL_TIMEOUT, "max_command": MAX_TERMINAL_COMMAND, "max_output": MAX_TERMINAL_OUTPUT, "cwd": str(REPO_DIR)})
            elif path == "/api/log":
                if not self.require_auth():
                    return
                target = LOG_FILES.get(self.query().get("name", [""])[0])
                if not target:
                    self.send_bytes(b"log invalido\n", "text/plain", 400)
                    return
                lines = read_text(target, "sem log").splitlines()[-300:]
                self.send_bytes(("\n".join(lines) + "\n").encode(), "text/plain; charset=utf-8")
            elif path == "/api/file-text":
                if not self.require_auth():
                    return
                name = self.safe_name()
                target = SHARED_DIR / name
                if not name or not target.is_file() or target.suffix.lower() not in ALLOWED_TEXT_SUFFIXES or target.stat().st_size > MAX_TEXT_EDIT:
                    self.json_response({"error": "arquivo não editável"}, 400)
                    return
                self.send_bytes(target.read_bytes(), "text/plain; charset=utf-8")
            elif path == "/api/quick":
                if not self.require_auth():
                    return
                quick = {"status": ["/usr/local/bin/orbis", "--status"], "network": ["ip", "-4", "addr"], "disk": ["df", "-hP"], "memory": ["cat", "/proc/meminfo"], "tailscale": ["tailscale", "status"], "git": ["git", "-C", str(REPO_DIR), "status", "--short", "--branch"]}
                command = quick.get(self.query().get("name", [""])[0])
                if not command:
                    self.json_response({"error": "comando não permitido"}, 400)
                    return
                self.send_bytes((run(*command, timeout=12) + "\n").encode(), "text/plain; charset=utf-8")
            elif path.startswith("/files/"):
                name = Path(urllib.parse.unquote(path[len("/files/"):])).name
                target = SHARED_DIR / name
                if not target.is_file():
                    self.send_bytes(b"not found\n", "text/plain", 404)
                    return
                self.send_bytes(target.read_bytes(), "application/octet-stream", disposition=f'attachment; filename="{name}"')
            else:
                self.send_bytes(b"not found\n", "text/plain", 404)
        except Exception as exc:
            self.json_response({"error": type(exc).__name__, "message": str(exc)}, 500)

    def do_PUT(self) -> None:
        path = urllib.parse.urlsplit(self.path).path
        if not self.require_auth():
            return
        name = self.safe_name()
        if path == "/api/files":
            length = int(self.headers.get("Content-Length", "0") or 0)
            if not name or length < 0 or length > MAX_UPLOAD:
                self.json_response({"error": "arquivo inválido ou maior que 25 MB"}, 400)
                return
            data = self.rfile.read(length)
            tmp = SHARED_DIR / ("." + hashlib.sha256(name.encode()).hexdigest()[:12] + ".tmp")
            tmp.write_bytes(data)
            tmp.replace(SHARED_DIR / name)
            event(f"upload remoto: {name} ({length} bytes)")
            self.json_response({"ok": True, "name": name})
        elif path == "/api/file-text":
            target = SHARED_DIR / name
            length = int(self.headers.get("Content-Length", "0") or 0)
            if not name or target.suffix.lower() not in ALLOWED_TEXT_SUFFIXES or length > MAX_TEXT_EDIT:
                self.json_response({"error": "arquivo não editável"}, 400)
                return
            data = self.rfile.read(length)
            data.decode("utf-8")
            tmp = SHARED_DIR / ("." + hashlib.sha256(name.encode()).hexdigest()[:12] + ".edit")
            tmp.write_bytes(data)
            tmp.replace(target)
            event(f"arquivo editado remotamente: {name}")
            self.json_response({"ok": True})
        else:
            self.json_response({"error": "rota inválida"}, 404)

    def do_DELETE(self) -> None:
        if urllib.parse.urlsplit(self.path).path != "/api/files" or not self.require_auth():
            return
        name = self.safe_name()
        target = SHARED_DIR / name
        if not name or not target.is_file():
            self.json_response({"error": "arquivo não encontrado"}, 404)
            return
        target.unlink()
        event(f"arquivo excluído remotamente: {name}")
        self.json_response({"ok": True})

    def do_POST(self) -> None:
        path = urllib.parse.urlsplit(self.path).path
        if not self.require_auth():
            return
        data = self.read_json()
        if path == "/api/terminal/exec":
            command = str(data.get("command", "")).strip()
            cwd = str(data.get("cwd", str(REPO_DIR))).strip() or str(REPO_DIR)
            if not command:
                self.json_response({"error": "comando vazio"}, 400)
                return
            if len(command) > MAX_TERMINAL_COMMAND:
                self.json_response({"error": "comando excede o limite de 8192 caracteres"}, 413)
                return
            workdir = Path(cwd).expanduser()
            if not workdir.is_dir():
                self.json_response({"error": f"diretório inexistente: {cwd}"}, 400)
                return
            if not Path(TERMINAL_SHELL).is_file():
                self.json_response({"error": f"shell indisponível: {TERMINAL_SHELL}"}, 503)
                return
            started = time.monotonic()
            event(f"terminal remoto iniciado via {TERMINAL_SHELL}: {command[:200]}")
            try:
                completed = subprocess.run([TERMINAL_SHELL, "-lc", command], cwd=str(workdir), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=TERMINAL_TIMEOUT)
                output = completed.stdout or ""
                if len(output) > MAX_TERMINAL_OUTPUT:
                    output = output[:MAX_TERMINAL_OUTPUT] + "\n[saída truncada pelo Orbis]"
                duration_ms = round((time.monotonic() - started) * 1000)
                event(f"terminal remoto finalizado: código={completed.returncode}")
                self.json_response({"ok": completed.returncode == 0, "exit_code": completed.returncode, "output": output, "cwd": str(workdir), "shell": TERMINAL_SHELL, "duration_ms": duration_ms})
            except subprocess.TimeoutExpired as exc:
                output = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
                event("terminal remoto interrompido por timeout")
                self.json_response({"ok": False, "exit_code": 124, "output": output, "shell": TERMINAL_SHELL, "error": f"tempo limite de {TERMINAL_TIMEOUT} segundos excedido"}, 408)
            except OSError as exc:
                event(f"erro no terminal remoto: {exc}")
                self.json_response({"ok": False, "shell": TERMINAL_SHELL, "error": str(exc)}, 500)
        elif path == "/api/action":
            action = str(data.get("action", ""))
            commands = {"update": ["/usr/local/bin/orbis-update"], "restart-core": ["/usr/local/bin/orbis-web", "--restart"], "restart-remote": ["/usr/local/bin/orbis-remote", "--boot"], "sync-time": ["/usr/local/bin/orbis-time"], "reboot": ["reboot"], "poweroff": ["poweroff"]}
            command = commands.get(action)
            if not command:
                self.json_response({"error": "ação não permitida"}, 400)
                return
            subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            event(f"ação remota iniciada: {action}")
            self.json_response({"ok": True, "message": f"ação {action} iniciada"})
        elif path == "/api/job":
            name = Path(str(data.get("name", ""))).name
            operation = str(data.get("operation", ""))
            job_file = JOBS_DIR / f"{name}.job"
            enabled_file = JOBS_DIR / f"{name}.enabled"
            if not name or not job_file.is_file():
                self.json_response({"error": "automação não encontrada"}, 404)
                return
            if operation == "toggle":
                if enabled_file.exists():
                    enabled_file.unlink()
                else:
                    enabled_file.touch()
                event(f"automação alternada: {name}")
                self.json_response({"ok": True, "message": "estado alterado"})
            elif operation == "run":
                subprocess.Popen(["/usr/local/bin/orbis-jobs", "--run", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                event(f"automação executada remotamente: {name}")
                self.json_response({"ok": True, "message": "execução iniciada"})
            else:
                self.json_response({"error": "operação inválida"}, 400)
        else:
            self.json_response({"error": "rota inválida"}, 404)


def main() -> None:
    server = OrbisHTTPServer((HOST, PORT), Handler)

    def shutdown(_signum: int, _frame: object) -> None:
        server.shutdown()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    event(f"Orbis Core iniciado na porta {PORT}")
    print(f"Orbis Core online em http://0.0.0.0:{PORT}", flush=True)
    server.serve_forever(poll_interval=0.5)


if __name__ == "__main__":
    main()
