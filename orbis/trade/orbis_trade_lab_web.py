#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import secrets
import subprocess
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

HOST = "0.0.0.0"
PORT = int(os.environ.get("ORBIS_TRADE_LAB_PORT", "8091"))
TOKEN_FILE = Path("/etc/orbis-web-token")
LAB_BIN = "/usr/local/bin/orbis-trade-lab"


def token() -> str:
    try:
        return TOKEN_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def run_lab(command: str, data: dict[str, Any]) -> dict[str, Any]:
    cmd = [LAB_BIN, command]
    mapping = {
        "symbol": "--symbol", "timeframe": "--timeframe", "fast": "--fast", "slow": "--slow",
        "capital": "--capital", "risk_pct": "--risk-pct", "stop_pips": "--stop-pips",
        "take_pips": "--take-pips", "spread_pips": "--spread-pips", "pip_size": "--pip-size",
        "pip_value": "--pip-value", "max_lots": "--max-lots", "simulations": "--simulations",
        "fast_min": "--fast-min", "fast_max": "--fast-max", "fast_step": "--fast-step",
        "slow_min": "--slow-min", "slow_max": "--slow-max", "slow_step": "--slow-step", "top": "--top",
        "side": "--side", "price": "--price", "lots": "--lots", "stop": "--stop", "take": "--take",
        "index": "--index",
    }
    for key, flag in mapping.items():
        if key in data and data[key] not in (None, ""):
            cmd.extend([flag, str(data[key])])
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    raw = (proc.stdout or proc.stderr).strip()
    if proc.returncode != 0:
        raise ValueError(raw or f"Falha em {command} (exit {proc.returncode})")
    return json.loads(raw)


def page() -> str:
    return r"""<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Orbis Quant Lab</title><style>
:root{color-scheme:dark;--bg:#080c11;--panel:#111923;--line:#26364a;--txt:#eef5ff;--muted:#91a4bb;--green:#78e7a5;--red:#ff9696;--blue:#8dbdff}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font-family:system-ui,sans-serif}.shell{display:grid;grid-template-columns:220px 1fr;min-height:100vh}.side{background:#0c1219;border-right:1px solid var(--line);padding:22px 15px}.brand{font-weight:800;letter-spacing:.12em}.sub,.muted{color:var(--muted)}.nav button{display:block;width:100%;text-align:left;margin-top:8px;background:transparent;border:0;color:#cad7e7;padding:11px;border-radius:8px}.nav button.active{background:#192536}.main{padding:18px;max-width:1300px;width:100%;margin:auto}.top{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--line);padding-bottom:15px}.card{background:var(--panel);border:1px solid var(--line);border-radius:13px;padding:15px;margin-top:14px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}.key{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}.value{font-size:21px;margin-top:6px}.form{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}label{font-size:13px;color:#cbd7e7}input,select,button{width:100%;padding:10px;margin-top:5px;background:#0c141e;color:#fff;border:1px solid #39506b;border-radius:8px}button{cursor:pointer;background:#214d39;width:auto}.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.tab{display:none}.tab.active{display:block}pre{white-space:pre-wrap;background:#070a0e;padding:12px;border-radius:8px;overflow:auto;max-height:420px}.pos{color:var(--green)}.neg{color:var(--red)}table{width:100%;border-collapse:collapse;font-size:13px}th,td{padding:8px;border-bottom:1px solid var(--line);text-align:left}.scroll{overflow:auto}@media(max-width:800px){.shell{display:block}.side{border-right:0;border-bottom:1px solid var(--line)}.nav{display:flex;overflow:auto}.nav button{white-space:nowrap;width:auto}.main{padding:12px}}
</style></head><body><div class='shell'><aside class='side'><div class='brand'>ORBIS QUANT LAB</div><div class='sub'>Pesquisa e paper trading</div><div class='nav'><button class='active' data-tab='analyze'>Análise</button><button data-tab='optimize'>Otimização</button><button data-tab='monte'>Monte Carlo</button><button data-tab='paper'>Paper Trading</button><button onclick="location.href='http://100.87.144.114:8090/'">Painel clássico</button></div></aside><main class='main'>
<div class='top'><div><div class='key'>ORBIS TRADE 2.0</div><h2 style='margin:4px 0'>Laboratório quantitativo</h2></div><div><span class='pos'>● Motor online</span><div id='clock' class='muted'></div></div></div>
<section class='card'><div class='key'>Autenticação</div><div class='form'><label>Token<input id='token' type='password'></label></div><div class='actions'><button id='auth'>Validar</button></div><div id='authState' class='muted'>Token não validado.</div></section>
<div id='analyze' class='tab active'><section class='card'><div class='key'>Analisar estratégia</div><div class='form'>
<label>Ativo<select id='a_symbol'><option>DEMO</option><option>EURUSD</option><option>GBPUSD</option><option>USDJPY</option></select></label><label>Timeframe<select id='a_timeframe'><option selected>1h</option><option>15m</option><option>4h</option></select></label><label>SMA rápida<input id='a_fast' value='9' type='number'></label><label>SMA lenta<input id='a_slow' value='21' type='number'></label><label>Capital (R$)<input id='a_capital' value='10000' type='number'></label><label>Risco (%)<input id='a_risk_pct' value='1' type='number' step='.1'></label><label>Stop (pips)<input id='a_stop_pips' value='30' type='number'></label><label>Alvo (pips)<input id='a_take_pips' value='60' type='number'></label><label>Spread<input id='a_spread_pips' value='1' type='number'></label><label>Pip size<input id='a_pip_size' value='.01' type='number' step='.0001'></label><label>Valor pip/lote<input id='a_pip_value' value='10' type='number'></label><label>Lote máximo<input id='a_max_lots' value='10' type='number'></label></div><button id='analyzeBtn'>Executar análise</button><pre id='analyzeOut'>Pronto.</pre></section><section id='metrics' class='grid'></section><section class='card'><div class='key'>Análise Orbis</div><div id='ai'>Nenhuma análise.</div></section></div>
<div id='optimize' class='tab'><section class='card'><div class='key'>Otimização de parâmetros</div><div class='form'><label>Ativo<input id='o_symbol' value='DEMO'></label><label>TF<input id='o_timeframe' value='1h'></label><label>Capital<input id='o_capital' value='10000' type='number'></label><label>Pip size<input id='o_pip_size' value='.01' type='number' step='.0001'></label><label>Rápida mín.<input id='o_fast_min' value='5' type='number'></label><label>Rápida máx.<input id='o_fast_max' value='20' type='number'></label><label>Lenta mín.<input id='o_slow_min' value='20' type='number'></label><label>Lenta máx.<input id='o_slow_max' value='80' type='number'></label><label>Passo lenta<input id='o_slow_step' value='5' type='number'></label><label>Top<input id='o_top' value='10' type='number'></label></div><button id='optBtn'>Otimizar</button><pre id='optOut'>Pronto.</pre><div id='optTable' class='scroll'></div></section></div>
<div id='monte' class='tab'><section class='card'><div class='key'>Monte Carlo</div><p class='muted'>Reamostra as operações do backtest e estima cenários de capital, drawdown e ruína.</p><div class='form'><label>Ativo<input id='m_symbol' value='DEMO'></label><label>TF<input id='m_timeframe' value='1h'></label><label>SMA rápida<input id='m_fast' value='9' type='number'></label><label>SMA lenta<input id='m_slow' value='21' type='number'></label><label>Capital<input id='m_capital' value='10000' type='number'></label><label>Pip size<input id='m_pip_size' value='.01' type='number' step='.0001'></label><label>Simulações<input id='m_simulations' value='1000' type='number'></label></div><button id='monteBtn'>Simular</button><pre id='monteOut'>Pronto.</pre></section></div>
<div id='paper' class='tab'><section class='card'><div class='key'>Conta simulada</div><div class='actions'><button id='paperInit'>Criar/Reiniciar R$ 10.000</button><button id='paperStatus'>Atualizar conta</button></div><pre id='paperOut'>Pronto.</pre></section><section class='card'><div class='key'>Nova posição</div><div class='form'><label>Ativo<input id='p_symbol' value='EURUSD'></label><label>Lado<select id='p_side'><option>BUY</option><option>SELL</option></select></label><label>Preço<input id='p_price' value='1.085' type='number' step='.00001'></label><label>Lotes<input id='p_lots' value='.1' type='number' step='.01'></label><label>Stop<input id='p_stop' value='1.082' type='number' step='.00001'></label><label>Alvo<input id='p_take' value='1.091' type='number' step='.00001'></label></div><button id='paperOrder'>Abrir posição</button></section></div>
<section class='card'><div class='key'>Diagnóstico</div><div id='diag' class='muted'>Inicializando…</div></section>
</main></div><script>
'use strict';const $=id=>document.getElementById(id);const token=()=>$('token').value.trim();function values(prefix,keys){const o={};keys.forEach(k=>{const e=$(prefix+k);if(e)o[k]=e.type==='number'?Number(e.value):e.value});return o}function show(id,obj){$(id).textContent=typeof obj==='string'?obj:JSON.stringify(obj,null,2)}function diag(s,ok=true){$('diag').textContent=(ok?'OK · ':'ERRO · ')+s+' · '+new Date().toLocaleTimeString('pt-BR')}async function api(path,body){const r=await fetch(path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json','X-Orbis-Token':token()},body:body?JSON.stringify(body):undefined});const t=await r.text();if(!r.ok)throw new Error((()=>{try{return JSON.parse(t).error}catch{return t}})());return JSON.parse(t)}
document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{document.querySelectorAll('[data-tab]').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));b.classList.add('active');$(b.dataset.tab).classList.add('active')});const saved=localStorage.getItem('orbisToken')||'';$('token').value=saved;$('token').oninput=()=>localStorage.setItem('orbisToken',token());$('auth').onclick=async()=>{try{await api('/api/auth');$('authState').textContent='Token válido.';$('authState').className='pos'}catch(e){$('authState').textContent=e.message;$('authState').className='neg'}};
$('analyzeBtn').onclick=async()=>{show('analyzeOut','Executando…');try{const d=await api('/api/lab/analyze',values('a_',['symbol','timeframe','fast','slow','capital','risk_pct','stop_pips','take_pips','spread_pips','pip_size','pip_value','max_lots']));show('analyzeOut',d);const fields=[['Retorno',d.return_pct+'%'],['Drawdown',d.max_drawdown_pct+'%'],['Profit factor',d.profit_factor],['Sharpe',d.sharpe],['Sortino',d.sortino],['Expectância',d.expectancy],['Operações',d.closed_trades],['Win rate',d.win_rate_pct+'%']];$('metrics').innerHTML=fields.map(x=>`<div class='card'><div class='key'>${x[0]}</div><div class='value'>${x[1]}</div></div>`).join('');$('ai').innerHTML=`<h3>${d.ai_analysis?.verdict||'N/D'}</h3><ul>${(d.ai_analysis?.notes||[]).map(n=>`<li>${n}</li>`).join('')}</ul>`;diag('Análise concluída')}catch(e){show('analyzeOut','Falha: '+e.message);diag(e.message,false)}};
$('optBtn').onclick=async()=>{show('optOut','Otimizando…');try{const d=await api('/api/lab/optimize',values('o_',['symbol','timeframe','capital','pip_size','fast_min','fast_max','slow_min','slow_max','slow_step','top']));show('optOut',{tested:d.tested});$('optTable').innerHTML='<table><tr><th>Rápida</th><th>Lenta</th><th>Score</th><th>Retorno</th><th>DD</th><th>PF</th></tr>'+d.top.map(x=>`<tr><td>${x.fast}</td><td>${x.slow}</td><td>${x.score}</td><td>${x.return_pct}%</td><td>${x.drawdown_pct}%</td><td>${x.profit_factor}</td></tr>`).join('')+'</table>';diag('Otimização concluída')}catch(e){show('optOut','Falha: '+e.message);diag(e.message,false)}};
$('monteBtn').onclick=async()=>{show('monteOut','Simulando…');try{const d=await api('/api/lab/monte-carlo',values('m_',['symbol','timeframe','fast','slow','capital','pip_size','simulations']));show('monteOut',d);diag('Monte Carlo concluído')}catch(e){show('monteOut','Falha: '+e.message);diag(e.message,false)}};
$('paperInit').onclick=async()=>{try{show('paperOut',await api('/api/lab/paper-init',{capital:10000}));diag('Conta simulada criada')}catch(e){diag(e.message,false)}};$('paperStatus').onclick=async()=>{try{show('paperOut',await api('/api/lab/paper-status',{}));diag('Conta atualizada')}catch(e){diag(e.message,false)}};$('paperOrder').onclick=async()=>{try{show('paperOut',await api('/api/lab/paper-order',values('p_',['symbol','side','price','lots','stop','take'])));diag('Posição simulada aberta')}catch(e){diag(e.message,false)}};setInterval(()=>$('clock').textContent=new Date().toLocaleString('pt-BR'),1000);diag('Painel carregado');
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: object) -> None:
        print(fmt % args, flush=True)

    def send_body(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def authorized(self) -> bool:
        expected = token()
        supplied = self.headers.get("X-Orbis-Token", "")
        return bool(expected) and secrets.compare_digest(expected, supplied)

    def do_GET(self) -> None:
        path = urllib.parse.urlsplit(self.path).path
        if path == "/health":
            self.send_body(b"ok\n", "text/plain; charset=utf-8")
        elif path == "/api/auth":
            self.send_body(json.dumps({"ok": True} if self.authorized() else {"error": "não autorizado"}).encode(), "application/json", 200 if self.authorized() else 401)
        elif path == "/":
            self.send_body(page().encode(), "text/html; charset=utf-8")
        else:
            self.send_body(b"not found\n", "text/plain", 404)

    def do_POST(self) -> None:
        path = urllib.parse.urlsplit(self.path).path
        routes = {
            "/api/lab/analyze": "analyze", "/api/lab/optimize": "optimize",
            "/api/lab/monte-carlo": "monte-carlo", "/api/lab/paper-init": "paper-init",
            "/api/lab/paper-status": "paper-status", "/api/lab/paper-order": "paper-order",
            "/api/lab/paper-close": "paper-close",
        }
        if path not in routes:
            self.send_body(b"not found\n", "text/plain", 404); return
        if not self.authorized():
            self.send_body(json.dumps({"error": "não autorizado"}).encode(), "application/json", 401); return
        try:
            length = min(int(self.headers.get("Content-Length", "0") or 0), 65536)
            data = json.loads(self.rfile.read(length) or b"{}")
            result = run_lab(routes[path], data)
            self.send_body(json.dumps(result, ensure_ascii=False).encode(), "application/json; charset=utf-8")
        except (ValueError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
            self.send_body(json.dumps({"error": str(exc)}, ensure_ascii=False).encode(), "application/json; charset=utf-8", 400)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Orbis Quant Lab Web: http://{HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
