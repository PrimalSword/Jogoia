#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import secrets
import sqlite3
import subprocess
import time
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
    item["params"] = json.loads(item.pop("params_json"))
    item["result"] = json.loads(item.pop("result_json"))
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
            "FROM runs ORDER BY id DESC LIMIT 10"
        ).fetchall()
        recent = [decode_run(row) for row in rows]
        return {"datasets": datasets, "runs": runs, "latest": recent[0] if recent else None, "recent": recent}
    finally:
        conn.close()


def run_backtest(data: dict[str, Any]) -> dict[str, Any]:
    symbol = str(data.get("symbol", "DEMO")).upper().strip()[:24]
    timeframe = str(data.get("timeframe", "1h")).strip()[:12]
    fast = max(1, int(data.get("fast", 9)))
    slow = max(fast + 1, int(data.get("slow", 21)))
    capital = max(1.0, float(data.get("capital", 10000)))
    fee_bps = max(0.0, float(data.get("fee_bps", 10)))
    cmd = [TRADE_BIN, "backtest", "--symbol", symbol, "--timeframe", timeframe,
           "--fast", str(fast), "--slow", str(slow), "--capital", str(capital),
           "--fee-bps", str(fee_bps)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
    raw = (proc.stdout or proc.stderr).strip()
    if proc.returncode != 0:
        raise ValueError(raw or f"Falha no backtest (exit {proc.returncode})")
    return json.loads(raw)


def page() -> str:
    return """<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'><title>Orbis Trade</title>
<style>
body{font-family:system-ui,sans-serif;background:#0b0f14;color:#eaf2ff;margin:0;padding:16px}main{max-width:980px;margin:auto}.head{display:flex;justify-content:space-between;align-items:end;border-bottom:1px solid #526070;padding-bottom:14px}.online{font-size:28px;color:#8ef0b1}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}.card{background:#141b24;border:1px solid #273444;border-radius:12px;padding:16px;margin-top:14px}.key{font-size:12px;color:#93a4b8;text-transform:uppercase}.value{font-size:22px;margin-top:6px;word-break:break-word}input,select,button{background:#0f151d;color:#fff;border:1px solid #40556d;border-radius:8px;padding:11px;box-sizing:border-box;width:100%}button{background:#1f4b37;width:auto;min-width:150px}button:disabled{opacity:.55}.form{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}label{display:block;margin:8px 0}table{width:100%;border-collapse:collapse}td,th{padding:8px;border-bottom:1px solid #273444;text-align:left}pre{white-space:pre-wrap;background:#080b0f;padding:12px;border-radius:8px;max-height:420px;overflow:auto}.warn{color:#ffd479}.pos{color:#8ef0b1}.neg{color:#ff9b9b}.muted{color:#93a4b8}a{color:#9dc8ff}.auth{display:flex;gap:8px;align-items:end;flex-wrap:wrap}.auth label{flex:1;min-width:230px}.chart{width:100%;height:240px;background:#0b1017;border:1px solid #273444;border-radius:10px}.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px}.gooddot{background:#8ef0b1}.baddot{background:#ff9b9b}
</style></head>
<body><main><div class='head'><div><div class='key'>ORBIS TRADE</div><div class='online'>PAPER / BACKTEST</div></div><a href='http://100.87.144.114:8080/'>Voltar ao Orbis OS</a></div>
<div class='grid'><section class='card'><div class='key'>Capital inicial</div><div class='value' id='initial'>—</div></section><section class='card'><div class='key'>Capital final</div><div class='value' id='final'>—</div></section><section class='card'><div class='key'>Retorno</div><div class='value' id='ret'>—</div></section><section class='card'><div class='key'>Drawdown</div><div class='value' id='dd'>—</div></section><section class='card'><div class='key'>Win rate</div><div class='value' id='win'>—</div></section><section class='card'><div class='key'>Execuções</div><div class='value' id='runs'>—</div></section></div>
<section class='card'><div class='key'>Autenticação</div><div class='auth'><label>Token administrativo<input id='token' type='password' placeholder='Mesmo token do Orbis OS'></label><button id='authBtn' onclick='verifyToken()'>Validar token</button></div><p id='authState' class='muted'>Token ainda não validado.</p></section>
<section class='card'><div class='key'>Executar backtest SMA Cross</div><div class='form'><label>Ativo<input id='symbol' value='DEMO'></label><label>Timeframe<input id='timeframe' value='1h'></label><label>SMA rápida<input id='fast' type='number' value='9'></label><label>SMA lenta<input id='slow' type='number' value='21'></label><label>Capital (R$)<input id='capital' type='number' value='10000'></label><label>Taxa (bps)<input id='fee' type='number' value='10'></label></div><button id='runBtn' onclick='runTest()'>Executar backtest</button><pre id='result'>Pronto.</pre></section>
<section class='card'><div class='key'>Desempenho das últimas execuções</div><svg id='chart' class='chart' viewBox='0 0 900 240' preserveAspectRatio='none'></svg><div id='history'></div></section>
<section class='card'><div class='key'>Datasets</div><div id='datasets'>carregando…</div></section>
<section class='card'><div class='key'>Últimas operações</div><div id='trades'>Nenhuma execução.</div></section>
</main><script>
const brl=new Intl.NumberFormat('pt-BR',{style:'currency',currency:'BRL'});const saved=localStorage.getItem('orbisToken')||'';token.value=saved;token.addEventListener('input',()=>localStorage.setItem('orbisToken',token.value.trim()));
function pct(v){return Number(v||0).toFixed(2)+'%'}
function errorMessage(text){try{const d=JSON.parse(text);return d.error||text}catch(e){return text}}
function drawChart(recent){const svg=document.getElementById('chart');svg.innerHTML='';const items=[...(recent||[])].reverse();if(!items.length){svg.innerHTML="<text x='30' y='120' fill='#93a4b8'>Nenhuma execução registrada.</text>";return}const vals=items.map(x=>Number(x.result.final_capital||0));const min=Math.min(...vals),max=Math.max(...vals);const span=Math.max(1,max-min);const pts=vals.map((v,i)=>{const x=35+(i*(830/Math.max(1,vals.length-1)));const y=205-((v-min)/span)*165;return [x,y,v,items[i].id]});const line=document.createElementNS('http://www.w3.org/2000/svg','polyline');line.setAttribute('points',pts.map(p=>p[0]+','+p[1]).join(' '));line.setAttribute('fill','none');line.setAttribute('stroke','#8ef0b1');line.setAttribute('stroke-width','4');svg.appendChild(line);pts.forEach(p=>{const c=document.createElementNS('http://www.w3.org/2000/svg','circle');c.setAttribute('cx',p[0]);c.setAttribute('cy',p[1]);c.setAttribute('r','6');c.setAttribute('fill','#9dc8ff');svg.appendChild(c)});const t1=document.createElementNS('http://www.w3.org/2000/svg','text');t1.setAttribute('x','15');t1.setAttribute('y','24');t1.setAttribute('fill','#93a4b8');t1.textContent=brl.format(max);svg.appendChild(t1);const t2=document.createElementNS('http://www.w3.org/2000/svg','text');t2.setAttribute('x','15');t2.setAttribute('y','230');t2.setAttribute('fill','#93a4b8');t2.textContent=brl.format(min);svg.appendChild(t2)}
async function refresh(){try{const r=await fetch('/api/summary?x='+Date.now(),{cache:'no-store'});const d=await r.json();runs.textContent=d.runs;datasets.innerHTML=(d.datasets||[]).map(x=>`<p><b>${x.symbol}</b> · ${x.timeframe} · ${x.candles} candles</p>`).join('')||'<p>Nenhum dataset.</p>';drawChart(d.recent);history.innerHTML=(d.recent||[]).map(x=>`<p><span class='dot ${Number(x.result.return_pct)>=0?'gooddot':'baddot'}'></span>#${x.id} · ${x.symbol}/${x.timeframe} · ${pct(x.result.return_pct)} · ${brl.format(x.result.final_capital)}</p>`).join('')||'<p>Nenhuma execução.</p>';const q=d.latest?.result;if(!q)return;initial.textContent=brl.format(q.initial_capital);final.textContent=brl.format(q.final_capital);ret.textContent=pct(q.return_pct);ret.className='value '+(q.return_pct>=0?'pos':'neg');dd.textContent=pct(q.max_drawdown_pct);win.textContent=pct(q.win_rate_pct);trades.innerHTML='<table><tr><th>Lado</th><th>Preço</th><th>Taxa</th><th>PnL</th></tr>'+(q.trades||[]).map(t=>`<tr><td>${t.side}</td><td>${Number(t.price).toFixed(4)}</td><td>${Number(t.fee||0).toFixed(2)}</td><td>${t.pnl==null?'—':brl.format(t.pnl)}</td></tr>`).join('')+'</table>'}catch(e){result.textContent='Falha ao atualizar painel: '+e.message}}
async function verifyToken(){authBtn.disabled=true;authState.textContent='Validando…';try{const r=await fetch('/api/auth',{headers:{'X-Orbis-Token':token.value.trim()},cache:'no-store'});const txt=await r.text();if(!r.ok)throw new Error(errorMessage(txt));localStorage.setItem('orbisToken',token.value.trim());authState.textContent='Token válido. Backtests liberados.';authState.className='pos'}catch(e){authState.textContent='Token inválido: '+e.message;authState.className='neg'}finally{authBtn.disabled=false}}
async function runTest(){runBtn.disabled=true;result.textContent='Executando…';try{const body={symbol:symbol.value,timeframe:timeframe.value,fast:+fast.value,slow:+slow.value,capital:+capital.value,fee_bps:+fee.value};const r=await fetch('/api/backtest',{method:'POST',headers:{'Content-Type':'application/json','X-Orbis-Token':token.value.trim()},body:JSON.stringify(body)});const txt=await r.text();if(!r.ok)throw new Error(errorMessage(txt));const data=JSON.parse(txt);result.textContent=`SUCESSO · execução #${data.run_id}\nCapital final: ${brl.format(data.final_capital)}\nRetorno: ${pct(data.return_pct)}\nDrawdown: ${pct(data.max_drawdown_pct)}\nWin rate: ${pct(data.win_rate_pct)}`;authState.textContent='Token válido. Backtest concluído.';authState.className='pos';await refresh()}catch(e){result.textContent='Falha: '+e.message}finally{runBtn.disabled=false}}
refresh();if(saved)verifyToken();setInterval(refresh,10000);
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
                self.send(json.dumps({"ok": True}, ensure_ascii=False).encode(), "application/json; charset=utf-8")
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
            length = min(int(self.headers.get("Content-Length", "0") or 0), 8192)
            data = json.loads(self.rfile.read(length) or b"{}")
            result = run_backtest(data)
            self.send(json.dumps(result, ensure_ascii=False).encode(), "application/json; charset=utf-8")
        except (ValueError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
            self.send(json.dumps({"error": str(exc)}, ensure_ascii=False).encode(), "application/json; charset=utf-8", 400)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Orbis Trade Web: http://{HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
