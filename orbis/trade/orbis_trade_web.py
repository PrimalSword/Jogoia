#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import secrets
import sqlite3
import subprocess
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

HOST = "0.0.0.0"
PORT = int(os.environ.get("ORBIS_TRADE_PORT", "8090"))
DB = Path("/var/lib/orbis/trade/orbis_trade.db")
TOKEN_FILE = Path("/etc/orbis-web-token")
TRADE_BIN = "/usr/local/bin/orbis-trade"


def read_token() -> str:
    try:
        return TOKEN_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def decode_run(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    try:
        item["params"] = json.loads(item.pop("params_json"))
    except (KeyError, TypeError, json.JSONDecodeError):
        item["params"] = {}
    try:
        item["result"] = json.loads(item.pop("result_json"))
    except (KeyError, TypeError, json.JSONDecodeError):
        item["result"] = {}
    return item


def db_summary() -> dict[str, Any]:
    if not DB.exists():
        return {"datasets": [], "runs": 0, "latest": None, "recent": []}
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        datasets = [dict(row) for row in conn.execute(
            "SELECT symbol,timeframe,COUNT(*) candles,MIN(ts) first_ts,MAX(ts) last_ts "
            "FROM candles GROUP BY symbol,timeframe ORDER BY symbol,timeframe"
        )]
        runs = int(conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0])
        rows = conn.execute(
            "SELECT id,created_at,symbol,timeframe,strategy,params_json,result_json "
            "FROM runs ORDER BY id DESC LIMIT 20"
        ).fetchall()
        recent = [decode_run(row) for row in rows]
        return {"datasets": datasets, "runs": runs, "latest": recent[0] if recent else None, "recent": recent}
    finally:
        conn.close()


def run_forex_backtest(data: dict[str, Any]) -> dict[str, Any]:
    symbol = str(data.get("symbol", "EURUSD")).upper().replace("/", "").strip()[:12]
    timeframe = str(data.get("timeframe", "1h")).strip()[:12]
    fast = max(1, int(data.get("fast", 9)))
    slow = max(fast + 1, int(data.get("slow", 21)))
    capital = max(1.0, float(data.get("capital", 10000)))
    risk_pct = min(10.0, max(0.01, float(data.get("risk_pct", 1))))
    stop_pips = max(0.1, float(data.get("stop_pips", 30)))
    take_pips = max(0.1, float(data.get("take_pips", 60)))
    spread_pips = max(0.0, float(data.get("spread_pips", 1)))
    pip_value = max(0.01, float(data.get("pip_value", 10)))
    max_lots = max(0.01, float(data.get("max_lots", 10)))
    cmd = [
        TRADE_BIN, "forex-backtest", "--symbol", symbol, "--timeframe", timeframe,
        "--fast", str(fast), "--slow", str(slow), "--capital", str(capital),
        "--risk-pct", str(risk_pct), "--stop-pips", str(stop_pips),
        "--take-pips", str(take_pips), "--spread-pips", str(spread_pips),
        "--pip-value", str(pip_value), "--max-lots", str(max_lots),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    raw = (proc.stdout or proc.stderr).strip()
    if proc.returncode != 0:
        raise ValueError(raw or f"Falha no backtest Forex (exit {proc.returncode})")
    return json.loads(raw)


def page() -> str:
    return r"""<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'><title>Orbis Forex Lab</title>
<style>
:root{color-scheme:dark;--bg:#090d12;--panel:#121922;--line:#263445;--muted:#91a2b8;--text:#edf5ff;--green:#78e7a5;--red:#ff9696;--blue:#8dbdff;--gold:#f1ca72}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,sans-serif}.shell{display:grid;grid-template-columns:220px 1fr;min-height:100vh}.side{padding:22px 16px;border-right:1px solid var(--line);background:#0c1118;position:sticky;top:0;height:100vh}.brand{font-weight:800;letter-spacing:.13em}.sub{font-size:12px;color:var(--muted);margin-top:4px}.nav{margin-top:28px}.nav a{display:block;padding:11px 12px;margin:5px 0;border-radius:9px;color:#c9d6e5;text-decoration:none}.nav a.active{background:#182231;color:#fff}.main{padding:20px;max-width:1400px;width:100%;margin:auto}.top{display:flex;justify-content:space-between;gap:14px;align-items:center;border-bottom:1px solid var(--line);padding-bottom:16px}.status{display:flex;gap:8px;align-items:center;color:var(--green)}.dot{width:9px;height:9px;border-radius:50%;background:var(--green)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(165px,1fr));gap:12px}.card{background:var(--panel);border:1px solid var(--line);border-radius:13px;padding:15px;margin-top:14px}.key{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}.value{font-size:22px;margin-top:7px}.pos{color:var(--green)}.neg{color:var(--red)}.muted{color:var(--muted)}.form{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:10px}label{font-size:13px;color:#c9d6e5}input,select,button{width:100%;margin-top:6px;padding:11px;border:1px solid #3a4d64;border-radius:8px;background:#0d141d;color:#fff}button{width:auto;min-width:145px;background:#214d39;cursor:pointer}button.secondary{background:#192432}button:disabled{opacity:.55}.actions{display:flex;gap:9px;flex-wrap:wrap;margin-top:12px}pre{white-space:pre-wrap;background:#080b10;padding:12px;border-radius:8px;max-height:300px;overflow:auto}table{width:100%;border-collapse:collapse;font-size:13px}th,td{padding:8px;border-bottom:1px solid var(--line);text-align:left}.scroll{overflow:auto}.chart{width:100%;height:250px;border:1px solid var(--line);border-radius:10px;background:#0b1017}.bar{height:8px;background:#0a0f15;border-radius:8px;overflow:hidden;margin-top:9px}.fill{height:100%;width:0;background:var(--green)}.diag{font-family:ui-monospace,monospace;font-size:12px;color:#b8c5d5}.pill{display:inline-block;padding:4px 8px;border-radius:20px;background:#192433;color:#c8d8ea;font-size:12px}@media(max-width:820px){.shell{display:block}.side{height:auto;position:static;border-right:0;border-bottom:1px solid var(--line)}.nav{display:flex;overflow:auto;margin-top:14px}.nav a{white-space:nowrap}.main{padding:13px}.top{align-items:flex-start}.hide-mobile{display:none}}
</style></head><body><div class='shell'><aside class='side'><div class='brand'>ORBIS TRADE</div><div class='sub'>FOREX QUANT WORKBENCH</div><nav class='nav'><a class='active' href='#dashboard'>Dashboard</a><a href='#backtest'>Backtest</a><a href='#datasets'>Datasets</a><a href='#trades'>Operações</a><a href='http://100.87.144.114:8080/'>Orbis OS</a></nav></aside><main class='main'>
<div class='top'><div><div class='key'>ORBIS FOREX LAB</div><h2 style='margin:5px 0 0'>Painel quantitativo</h2></div><div><div class='status'><span class='dot'></span><span id='engineStatus'>Motor online</span></div><div id='clock' class='muted' style='margin-top:5px;text-align:right'>—</div></div></div>
<section id='dashboard' class='grid'><div class='card'><div class='key'>Equity inicial</div><div class='value' id='initial'>N/D</div></div><div class='card'><div class='key'>Equity final</div><div class='value' id='final'>N/D</div></div><div class='card'><div class='key'>Retorno</div><div class='value' id='ret'>N/D</div></div><div class='card'><div class='key'>Drawdown</div><div class='value' id='dd'>N/D</div></div><div class='card'><div class='key'>Win rate</div><div class='value' id='win'>N/D</div></div><div class='card'><div class='key'>Profit factor</div><div class='value' id='pf'>N/D</div></div><div class='card'><div class='key'>Pips líquidos</div><div class='value' id='pips'>N/D</div></div><div class='card'><div class='key'>Execuções</div><div class='value' id='runs'>0</div></div></section>
<section class='card'><div class='key'>Curva das últimas execuções</div><canvas id='chart' class='chart'></canvas><p id='lastUpdate' class='muted'>Aguardando atualização.</p></section>
<section class='card'><div class='key'>Autenticação</div><div class='form'><label>Token administrativo<input id='token' type='password' placeholder='Mesmo token do Orbis OS'></label></div><div class='actions'><button id='authBtn'>Validar token</button><button class='secondary' id='clearBtn'>Limpar token</button><button class='secondary' id='refreshBtn'>Atualizar agora</button><button class='secondary' id='exportBtn'>Exportar JSON</button></div><p id='authState' class='muted'>Token ainda não validado.</p></section>
<section id='backtest' class='card'><div class='key'>Backtest Forex — SMA + gestão de risco</div><div class='actions'><button class='secondary preset' data-preset='safe'>Conservador</button><button class='secondary preset' data-preset='balanced'>Equilibrado</button><button class='secondary preset' data-preset='aggressive'>Agressivo</button></div><div class='form'>
<label>Par<select id='symbol'><option>EURUSD</option><option>GBPUSD</option><option>USDJPY</option><option>USDCHF</option><option>AUDUSD</option><option>USDCAD</option><option>NZDUSD</option><option>EURGBP</option><option>EURJPY</option><option>GBPJPY</option><option>DEMO</option></select></label>
<label>Timeframe<select id='timeframe'><option>1m</option><option>5m</option><option>15m</option><option>30m</option><option selected>1h</option><option>4h</option><option>1d</option></select></label>
<label>SMA rápida<input id='fast' type='number' value='9'></label><label>SMA lenta<input id='slow' type='number' value='21'></label><label>Capital (R$)<input id='capital' type='number' value='10000'></label><label>Risco (%)<input id='risk' type='number' value='1' step='.1'></label><label>Stop (pips)<input id='stop' type='number' value='30'></label><label>Alvo (pips)<input id='take' type='number' value='60'></label><label>Spread (pips)<input id='spread' type='number' value='1' step='.1'></label><label>Valor pip/lote (R$)<input id='pipValue' type='number' value='10'></label><label>Lote máximo<input id='maxLots' type='number' value='10'></label></div><p class='muted'>Risco-retorno estimado: <span class='pill' id='rr'>1:2,00</span></p><button id='runBtn'>Executar backtest Forex</button><pre id='result'>Pronto.</pre></section>
<section id='datasets' class='card'><div class='key'>Datasets disponíveis</div><div id='datasetsBox'>Carregando…</div></section>
<section class='card'><div class='key'>Histórico</div><div class='scroll'><table><thead><tr><th>ID</th><th>Ativo</th><th>TF</th><th>Estratégia</th><th>Retorno</th><th>Equity final</th></tr></thead><tbody id='history'></tbody></table></div></section>
<section id='trades' class='card'><div class='key'>Últimas operações</div><div id='tradesBox' class='scroll'>Nenhuma operação.</div></section>
<section class='card'><div class='key'>Diagnóstico</div><div id='diagnostic' class='diag'>Inicializando…</div></section>
</main></div><script>
'use strict';
const $=id=>document.getElementById(id);const brl=new Intl.NumberFormat('pt-BR',{style:'currency',currency:'BRL'});let latestSummary=null;
function num(v){const n=Number(v);return Number.isFinite(n)?n:null}function money(v){const n=num(v);return n===null?'N/D':brl.format(n)}function pct(v){const n=num(v);return n===null?'N/D':n.toFixed(2)+'%'}function text(id,v){const e=$(id);if(e)e.textContent=v}function cls(id,v){const e=$(id);if(e)e.className='value '+(num(v)!==null&&num(v)>=0?'pos':'neg')}function diag(msg,ok=true){text('diagnostic',(ok?'OK · ':'ERRO · ')+msg+' · '+new Date().toLocaleTimeString('pt-BR'));text('engineStatus',ok?'Motor online':'Falha de atualização')}
function err(t){try{const d=JSON.parse(t);return d.error||t}catch{return t}}
function updateRR(){const s=Math.max(.01,num($('stop').value)||0),t=Math.max(.01,num($('take').value)||0);text('rr','1:'+(t/s).toFixed(2).replace('.',','))}
function drawChart(recent){const c=$('chart'),ctx=c.getContext('2d'),ratio=devicePixelRatio||1,w=c.clientWidth||800,h=c.clientHeight||250;c.width=w*ratio;c.height=h*ratio;ctx.scale(ratio,ratio);ctx.clearRect(0,0,w,h);const items=[...(recent||[])].reverse();const vals=items.map(x=>num(x?.result?.final_capital)).filter(v=>v!==null);ctx.font='13px system-ui';ctx.fillStyle='#91a2b8';if(!vals.length){ctx.fillText('Nenhuma execução registrada.',24,h/2);return}const min=Math.min(...vals),max=Math.max(...vals),span=Math.max(1,max-min),pad=30;ctx.strokeStyle='#78e7a5';ctx.lineWidth=3;ctx.beginPath();vals.forEach((v,i)=>{const x=pad+i*((w-pad*2)/Math.max(1,vals.length-1)),y=h-pad-((v-min)/span)*(h-pad*2);i?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.stroke();ctx.fillStyle='#91a2b8';ctx.fillText(money(max),10,18);ctx.fillText(money(min),10,h-8)}
function renderLatest(run){const q=run?.result||{};text('initial',money(q.initial_capital));text('final',money(q.final_capital));text('ret',pct(q.return_pct));cls('ret',q.return_pct);text('dd',pct(q.max_drawdown_pct));text('win',pct(q.win_rate_pct));text('pf',num(q.profit_factor)===null?'N/D':num(q.profit_factor).toFixed(2));text('pips',num(q.net_pips)===null?'N/D':num(q.net_pips).toFixed(2));const trades=Array.isArray(q.trades)?q.trades:[];if(!trades.length){$('tradesBox').textContent='Nenhuma operação neste resultado.';return}$('tradesBox').innerHTML='<table><thead><tr><th>Lado</th><th>Entrada</th><th>Saída</th><th>Lotes</th><th>Pips</th><th>PnL</th><th>Motivo</th></tr></thead><tbody>'+trades.map(t=>`<tr><td>${t.side??'—'}</td><td>${num(t.entry??t.price)?.toFixed(5)??'—'}</td><td>${num(t.price)?.toFixed(5)??'—'}</td><td>${t.lots??'—'}</td><td>${t.pips??'—'}</td><td>${t.pnl==null?'—':money(t.pnl)}</td><td>${t.reason??(t.forced?'FIM_DADOS':'—')}</td></tr>`).join('')+'</tbody></table>'}
function renderSummary(d){latestSummary=d;text('runs',d?.runs??0);const sets=Array.isArray(d?.datasets)?d.datasets:[];$('datasetsBox').innerHTML=sets.length?sets.map(x=>`<p><b>${x.symbol??'—'}</b> · ${x.timeframe??'—'} · ${x.candles??0} candles · ${x.first_ts?new Date(x.first_ts*1000).toLocaleDateString('pt-BR'):'—'} → ${x.last_ts?new Date(x.last_ts*1000).toLocaleDateString('pt-BR'):'—'}</p>`).join(''):'<p>Nenhum dataset.</p>';const recent=Array.isArray(d?.recent)?d.recent:[];$('history').innerHTML=recent.length?recent.map(x=>`<tr><td>#${x.id??'—'}</td><td>${x.symbol??'—'}</td><td>${x.timeframe??'—'}</td><td>${x.strategy??'—'}</td><td>${pct(x?.result?.return_pct)}</td><td>${money(x?.result?.final_capital)}</td></tr>`).join(''):'<tr><td colspan="6">Nenhuma execução.</td></tr>';drawChart(recent);renderLatest(d?.latest);text('lastUpdate','Última atualização: '+new Date().toLocaleString('pt-BR'));diag('API e banco respondendo normalmente')}
async function refresh(){try{const r=await fetch('/api/summary?x='+Date.now(),{cache:'no-store'}),txt=await r.text();if(!r.ok)throw new Error(err(txt));renderSummary(JSON.parse(txt))}catch(e){diag(e.message,false);text('lastUpdate','Falha ao atualizar: '+e.message)}}
async function verifyToken(){const b=$('authBtn');b.disabled=true;text('authState','Validando…');try{const r=await fetch('/api/auth',{headers:{'X-Orbis-Token':$('token').value.trim()},cache:'no-store'}),txt=await r.text();if(!r.ok)throw new Error(err(txt));localStorage.setItem('orbisToken',$('token').value.trim());text('authState','Token válido. Backtests liberados.');$('authState').className='pos'}catch(e){text('authState','Token inválido: '+e.message);$('authState').className='neg'}finally{b.disabled=false}}
async function runTest(){const b=$('runBtn');b.disabled=true;text('result','Executando backtest Forex…');try{const body={symbol:$('symbol').value,timeframe:$('timeframe').value,fast:+$('fast').value,slow:+$('slow').value,capital:+$('capital').value,risk_pct:+$('risk').value,stop_pips:+$('stop').value,take_pips:+$('take').value,spread_pips:+$('spread').value,pip_value:+$('pipValue').value,max_lots:+$('maxLots').value};const r=await fetch('/api/backtest',{method:'POST',headers:{'Content-Type':'application/json','X-Orbis-Token':$('token').value.trim()},body:JSON.stringify(body)}),txt=await r.text();if(!r.ok)throw new Error(err(txt));const d=JSON.parse(txt);text('result',`SUCESSO · execução #${d.run_id??'—'}\n${d.symbol??body.symbol} · ${d.closed_trades??0} operações\nEquity final: ${money(d.final_capital)}\nRetorno: ${pct(d.return_pct)}\nDrawdown: ${pct(d.max_drawdown_pct)}\nWin rate: ${pct(d.win_rate_pct)}\nProfit factor: ${d.profit_factor??'N/D'}`);await refresh()}catch(e){text('result','Falha: '+e.message);diag(e.message,false)}finally{b.disabled=false}}
function preset(kind){const p={safe:[.5,40,80,1],balanced:[1,30,60,1],aggressive:[2,20,50,1.5]}[kind];$('risk').value=p[0];$('stop').value=p[1];$('take').value=p[2];$('spread').value=p[3];updateRR()}
function exportJson(){if(!latestSummary){diag('Nada para exportar',false);return}const blob=new Blob([JSON.stringify(latestSummary,null,2)],{type:'application/json'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='orbis-trade-summary.json';a.click();URL.revokeObjectURL(a.href)}
const saved=localStorage.getItem('orbisToken')||'';$('token').value=saved;$('token').addEventListener('input',()=>localStorage.setItem('orbisToken',$('token').value.trim()));$('authBtn').onclick=verifyToken;$('clearBtn').onclick=()=>{localStorage.removeItem('orbisToken');$('token').value='';text('authState','Token removido deste navegador.');$('authState').className='muted'};$('refreshBtn').onclick=refresh;$('exportBtn').onclick=exportJson;$('runBtn').onclick=runTest;document.querySelectorAll('.preset').forEach(b=>b.onclick=()=>preset(b.dataset.preset));['stop','take'].forEach(id=>$(id).addEventListener('input',updateRR));setInterval(()=>text('clock',new Date().toLocaleString('pt-BR')),1000);addEventListener('resize',()=>latestSummary&&drawChart(latestSummary.recent));updateRR();refresh();if(saved)verifyToken();setInterval(refresh,15000);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: object) -> None:
        print(fmt % args, flush=True)

    def send(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def authorized(self) -> bool:
        expected = read_token()
        supplied = self.headers.get("X-Orbis-Token", "")
        return bool(expected) and secrets.compare_digest(supplied, expected)

    def do_GET(self) -> None:
        path = urllib.parse.urlsplit(self.path).path
        if path == "/health":
            self.send(b"ok\n", "text/plain; charset=utf-8")
        elif path == "/api/summary":
            self.send(json.dumps(db_summary(), ensure_ascii=False).encode(), "application/json; charset=utf-8")
        elif path == "/api/auth":
            if self.authorized():
                self.send(json.dumps({"ok": True}).encode(), "application/json; charset=utf-8")
            else:
                self.send(json.dumps({"error": "não autorizado"}, ensure_ascii=False).encode(), "application/json; charset=utf-8", 401)
        elif path == "/":
            self.send(page().encode(), "text/html; charset=utf-8")
        else:
            self.send(b"not found\n", "text/plain; charset=utf-8", 404)

    def do_POST(self) -> None:
        if urllib.parse.urlsplit(self.path).path != "/api/backtest":
            self.send(b"not found\n", "text/plain; charset=utf-8", 404)
            return
        if not self.authorized():
            self.send(json.dumps({"error": "não autorizado"}, ensure_ascii=False).encode(), "application/json; charset=utf-8", 401)
            return
        try:
            length = min(int(self.headers.get("Content-Length", "0") or 0), 16384)
            data = json.loads(self.rfile.read(length) or b"{}")
            result = run_forex_backtest(data)
            self.send(json.dumps(result, ensure_ascii=False).encode(), "application/json; charset=utf-8")
        except (ValueError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
            self.send(json.dumps({"error": str(exc)}, ensure_ascii=False).encode(), "application/json; charset=utf-8", 400)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Orbis Forex Lab: http://{HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
