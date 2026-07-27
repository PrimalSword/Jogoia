#!/usr/bin/env python3
"""Authenticated browser terminal for Orbis OS.

The service is intended to run behind the private Tailscale network. It uses
/etc/orbis-web-token, the same token used by Orbis Core, and is deliberately
bounded by command size and execution timeout.
"""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

HOST = "0.0.0.0"
PORT = int(os.environ.get("ORBIS_TERMINAL_PORT", "8081"))
TOKEN_FILE = Path(os.environ.get("ORBIS_TOKEN_FILE", "/etc/orbis-web-token"))
EVENTS_FILE = Path("/var/log/orbis-events.log")
MAX_COMMAND = 8192
MAX_OUTPUT = 128 * 1024
COMMAND_TIMEOUT = 30


def read_token() -> str:
    try:
        return TOKEN_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def event(message: str) -> None:
    try:
        EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with EVENTS_FILE.open("a", encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} terminal: {message}\n")
    except OSError:
        pass


def shell_html() -> str:
    return """<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Orbis Terminal</title>
<style>
body{font-family:system-ui,sans-serif;background:#080b0f;color:#eaf2ff;margin:0;padding:12px}
main{max-width:1100px;margin:auto}.card{background:#141b24;border:1px solid #273444;border-radius:12px;padding:14px}
h1{font-size:22px;margin:0 0 6px}.muted{color:#93a4b8;font-size:13px}
input,textarea,button{font:inherit;border-radius:8px;border:1px solid #40556d;padding:10px;box-sizing:border-box}
input,textarea{background:#0f151d;color:#fff;width:100%}textarea{min-height:360px;font-family:monospace;resize:vertical}
button{background:#26384b;color:#eef6ff;cursor:pointer}button.good{background:#1f4b37}
.row{display:grid;grid-template-columns:1fr auto;gap:8px;margin-top:10px}
pre{background:#05070a;border-radius:8px;padding:12px;min-height:300px;max-height:60vh;overflow:auto;white-space:pre-wrap;word-break:break-word;font-family:monospace}
.status{margin-top:8px;color:#8ef0b1}.warn{color:#ffd479}
</style></head><body><main><section class='card'>
<h1>ORBIS TERMINAL</h1><div class='muted'>Terminal web autenticado · acesso privado via Tailscale</div>
<div class='row'><input id='token' type='password' placeholder='Token de controle'><button onclick='saveToken()'>Salvar token</button></div>
<div class='row'><input id='command' placeholder='Digite um comando, ex.: uname -a' autocomplete='off'><button class='good' onclick='executeCommand()'>Executar</button></div>
<div class='row'><input id='cwd' placeholder='Diretório de trabalho (opcional)' value='/'><button onclick='clearOutput()'>Limpar</button></div>
<div id='status' class='status'>Pronto.</div><pre id='output'>Orbis Terminal pronto.</pre>
</section></main>
<script>
const tokenInput=document.getElementById('token');
const commandInput=document.getElementById('command');
const cwdInput=document.getElementById('cwd');
const output=document.getElementById('output');
const status=document.getElementById('status');
tokenInput.value=localStorage.getItem('orbisToken')||'';
function token(){return localStorage.getItem('orbisToken')||tokenInput.value.trim();}
function saveToken(){localStorage.setItem('orbisToken',tokenInput.value.trim());status.textContent='Token salvo neste navegador.';}
function clearOutput(){output.textContent='';}
commandInput.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();executeCommand();}});
async function executeCommand(){
 const command=commandInput.value.trim(); if(!command)return;
 status.textContent='Executando…';
 try{
  const r=await fetch('/api/terminal/exec',{method:'POST',headers:{'Content-Type':'application/json','X-Orbis-Token':token()},body:JSON.stringify({command,cwd:cwdInput.value.trim()})});
  const d=await r.json();
  output.textContent=(d.output||'')+(d.error?'\n'+d.error:'');
  if(d.cwd)cwdInput.value=d.cwd;
  status.textContent=d.ok?'Concluído · código '+d.exit_code:'Falha';
 }catch(e){status.textContent='Erro: '+e.message;}
}
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    server_version = "OrbisTerminal/1.1"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.client_address[0]} - {fmt % args}", flush=True)

    def send_bytes(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def json_response(self, data: dict[str, Any], status: int = 200) -> None:
        self.send_bytes(json.dumps(data, ensure_ascii=False).encode(), "application/json; charset=utf-8", status)

    def authorized(self) -> bool:
        token = read_token()
        supplied = self.headers.get("X-Orbis-Token", "")
        return bool(token) and secrets.compare_digest(supplied, token)

    def read_json(self) -> dict[str, Any]:
        try:
            length = min(int(self.headers.get("Content-Length", "0") or 0), MAX_COMMAND + 4096)
            value = json.loads(self.rfile.read(length))
            return value if isinstance(value, dict) else {}
        except (ValueError, json.JSONDecodeError):
            return {}

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self.send_bytes(shell_html().encode(), "text/html; charset=utf-8")
        elif path == "/health":
            self.send_bytes(b"ok\n", "text/plain; charset=utf-8")
        elif path == "/api/terminal/status":
            if not self.authorized():
                self.json_response({"error": "não autorizado"}, 401)
                return
            self.json_response({"status": "online", "port": PORT, "timeout_seconds": COMMAND_TIMEOUT, "max_output_bytes": MAX_OUTPUT})
        else:
            self.send_bytes(b"not found\n", "text/plain", 404)

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        if path != "/api/terminal/exec":
            self.json_response({"error": "rota inválida"}, 404)
            return
        if not self.authorized():
            self.json_response({"error": "não autorizado"}, 401)
            return
        data = self.read_json()
        command = str(data.get("command", "")).strip()
        cwd = str(data.get("cwd", "/")).strip() or "/"
        if not command or len(command) > MAX_COMMAND:
            self.json_response({"error": "comando vazio ou grande demais"}, 400)
            return
        workdir = Path(cwd).expanduser()
        if not workdir.is_dir():
            self.json_response({"error": f"diretório inexistente: {cwd}"}, 400)
            return
        started = time.monotonic()
        event(f"execução iniciada: {command[:200]}")
        try:
            completed = subprocess.run(
                ["/bin/bash", "-lc", command],
                cwd=str(workdir),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=COMMAND_TIMEOUT,
                check=False,
            )
            output = completed.stdout or ""
            if len(output) > MAX_OUTPUT:
                output = output[:MAX_OUTPUT] + "\n[saída truncada pelo Orbis Terminal]"
            event(f"execução finalizada: código={completed.returncode}")
            self.json_response({"ok": completed.returncode == 0, "exit_code": completed.returncode, "output": output, "cwd": str(workdir), "duration_ms": round((time.monotonic() - started) * 1000)})
        except subprocess.TimeoutExpired as exc:
            output = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
            event("execução interrompida por timeout")
            self.json_response({"ok": False, "exit_code": 124, "output": output, "error": "tempo limite de 30 segundos excedido"}, 408)
        except OSError as exc:
            event(f"erro de execução: {exc}")
            self.json_response({"ok": False, "error": str(exc)}, 500)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Orbis Terminal online em http://0.0.0.0:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
