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
:root{--bg:#081018;--panel:#101a25;--panel2:#0b141d;--line:#223447;--text:#edf5ff;--muted:#91a5bb;--green:#69e39f;--blue:#73b8ff;--red:#ff8c98;--amber:#ffd27a}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at top right,#11283a 0,#081018 34%);color:var(--text);font-family:Inter,system-ui,sans-serif}.shell{display:grid;grid-template-columns:220px 1fr;min-height:100vh}.side{border-right:1px solid var(--line);background:rgba(7,14,21,.94);padding:22px 14px;position:sticky;top:0;height:100vh}.brand{padding:8px 10px 24px}.brand b{font-size:20px;letter-spacing:.08em}.brand small{display:block;color:var(--green);margin-top:5px}.nav a{display:block;color:var(--muted);text-decoration:none;padding:11px 12px;border-radius:9px;margin:4px 0}.nav a.active,.nav a:hover{background:#132130;color:#fff}.sidefoot{position:absolute;bottom:18px;left:16px;right:16px;color:var(--muted);font-size:12px}.main{padding:22px;max-width:1400px;width:100%;margin:auto}.top{display:flex;justify-content:space-between;align-items:center;gap:15px}.title h1{margin:0;font-size:27px}.title p{margin:6px 0 0;color:var(--muted)}.status{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.pill{border:1px solid var(--line);background:var(--panel);border-radius:999px;padding:8px 12px;font-size:13px}.dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--green);margin-right:7px;box-shadow:0 0 10px var(--green)}.grid{display:grid;grid-template-columns:repeat(4,minmax(150px,1fr));gap:12px;margin-top:18px}.card{background:linear-gradient(180deg,var(--panel),var(--panel2));border:1px solid var(--line);border-radius:14px;padding:16px}.key{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}.value{font-size:22px;font-weight:700;margin-top:7px}.sub{font-size:12px;color:var(--muted);margin-top:5px}.section{margin-top:14px}.cols{display:grid;grid-template-columns:1.25fr .75fr;gap:14px}.form{display:grid;grid-template-columns:repeat(3,minmax(130px,1fr));gap:10px;margin-top:12px}label{font-size:12px;color:var(--muted)}input,select,button{width:100%;margin-top:6px;padding:11px;border-radius:9px;border:1px solid #36506a;background:#0a131c;color:#fff}button{background:linear-gradient(90deg,#1d7049,#245d48);cursor:pointer;font-weight:700}button:disabled{opacity:.55}.btn2{background:#142638}.row{display:flex;gap:10px;align-items:end}.row>*{flex:1}.note{font-size:12px;line-height:1.5;color:var(--muted)}pre{background:#070d13;border:1px solid #1c2a39;border-radius:10px;padding:13px;white-space:pre-wrap;max-height:270px;overflow:auto}.chart{width:100%;height:260px;background:#08111a;border:1px solid var(--line);border-radius:10px;margin-top:12px}.pos{color:var(--green)}.neg{color:var(--red)}.amber{color:var(--amber)}table{width:100%;border-collapse:collapse;font-size:13px}th,td{padding:9px 7px;border-bottom:1px solid #1f3041;text-align:left}th{color:var(--muted);font-size:11px;text-transform:uppercase}.scroll{overflow:auto}.dataset{padding:10px 0;border-bottom:1px solid #1f3041}.metricbar{height:8px;background:#0a1119;border-radius:999px;overflow:hidden;margin-top:8px}.metricbar span{display:block;height:100%;background:linear-gradient(90deg,var(--blue),var(--green))}.empty{color:var(--muted);padding:18px 0}.authok{border-color:#286044}.authbad{border-color:#6e3238}@media(max-width:980px){.shell{grid-template-columns:1fr}.side{display:none}.grid{grid-template-columns:repeat(2,1fr)}.cols{grid-template-columns:1fr}.form{grid-template-columns:repeat(2,1fr)}}@media(max-width:560px){.main{padding:13px}.grid,.form{grid-template-columns:1fr 1fr}.top{align-items:flex-start;flex-direction:column}.value{font-size:19px}}
</style></head><body><div class='shell'>
<aside class='side'><div class='brand'><b>ORBIS</b><small>FOREX LAB</small></div><nav class='nav'><a class='active' href='#dashboard'>Dashboard</a><a href='#backtest'>Backtests</a><a href='#analytics'>Analytics</a><a href='#datasets'>Datasets</a><a href='#trades'>Operações</a><a href='http://100.87.144.114:8080/'>Orbis OS</a></nav><div class='sidefoot'>Paper e backtest local<br>Nenhuma ordem real</div></aside>
<main class='main'><header class='top'><div class='title'><h1>Orbis Forex Lab</h1><p>Workbench quantitativo para pares de moedas</p></div><div class='status'><span class='pill'><span class='dot'></span>Motor online</span><span class='pill' id='clock'>--:--:--</span><span class='pill'>BACKTEST</span></div></header>
<section id='dashboard' class='grid'>
<div class='card'><div class='key'>Equity inicial</div><div class='value' id='initial'>—</div><div class='sub'>Capital de partida</div></div>
<div class='card'><div class='key'>Equity final</div><div class='value' id='final'>—</div><div class='sub' id='delta'>Aguardando execução</div></div>
<div class='card'><div class='key'>Retorno</div><div class='value' id='ret'>—</div><div class='metricbar'><span id='retbar' style='width:0%'></span></div></div>
<div class='card'><div class='key'>Drawdown máximo</div><div class='value' id='dd'>—</div><div class='sub'>Queda desde o pico</div></div>
<div class='card'><div class='key'>Win rate</div><div class='value' id='win'>—</div><div class='metricbar'><span id='winbar' style='width:0%'></span></div></div>
<div class='card'><div class='key'>Pips líquidos</div><div class='value' id='pips'>—</div><div class='sub'>Após spread</div></div>
<div class='card'><div class='key'>Profit factor</div><div class='value' id='pf'>—</div><div class='sub' id='pfLabel'>Qualidade da estratégia</div></div>
<div class='card'><div class='key'>Execuções</div><div class='value' id='runs'>—</div><div class='sub'>Histórico acumulado</div></div>
</section>
<section class='cols section'>
<div id='backtest' class='card'><div class='key'>Novo backtest Forex</div><div class='form'>
<label>Par<select id='symbol'><option>EURUSD</option><option>GBPUSD</option><option>USDJPY</option><option>USDCHF</option><option>AUDUSD</option><option>USDCAD</option><option>NZDUSD</option><option>EURGBP</option><option>EURJPY</option><option>GBPJPY</option><option>DEMO</option></select></label>
<label>Timeframe<select id='timeframe'><option>1m</option><option>5m</option><option>15m</option><option>30m</option><option selected>1h</option><option>4h</option><option>1d</option></select></label>
<label>Preset<select id='preset' onchange='applyPreset()'><option value='balanced'>Equilibrado</option><option value='conservative'>Conservador</option><option value='aggressive'>Agressivo</option></select></label>
<label>SMA rápida<input id='fast' type='number' value='9' min='1'></label><label>SMA lenta<input id='slow' type='number' value='21' min='2'></label><label>Capital (R$)<input id='capital' type='number' value='10000' min='1' step='100'></label>
<label>Risco por operação (%)<input id='risk' type='number' value='1' min='.01' max='10' step='.1'></label><label>Stop (pips)<input id='stop' type='number' value='30' min='.1' step='.1'></label><label>Alvo (pips)<input id='take' type='number' value='60' min='.1' step='.1'></label>
<label>Spread (pips)<input id='spread' type='number' value='1' min='0' step='.1'></label><label>Valor do pip/lote (R$)<input id='pipValue' type='number' value='10' min='.01' step='.01'></label><label>Lote máximo<input id='maxLots' type='number' value='10' min='.01' step='.01'></label>
</div><p class='note'>Relação risco-retorno atual: <b id='rr'>1:2.00</b>. O valor do pip ainda é informado manualmente. Nenhuma ordem é enviada a corretoras.</p><button id='runBtn' onclick='runTest()'>Executar backtest Forex</button><pre id='result'>Pronto para executar.</pre></div>
<div class='card'><div class='key'>Autenticação e sessão</div><label>Token administrativo<input id='token' type='password' placeholder='Mesmo token do Orbis OS'></label><div class='row'><button id='authBtn' onclick='verifyToken()'>Validar</button><button class='btn2' onclick='clearToken()'>Limpar</button></div><p id='authState' class='note'>Token ainda não validado.</p><hr style='border:0;border-top:1px solid var(--line);margin:18px 0'><div class='key'>Execução selecionada</div><div class='value' id='currentRun'>—</div><div class='sub' id='currentMeta'>Nenhum backtest carregado</div></div>
</section>
<section id='analytics' class='card section'><div class='key'>Curva das últimas execuções</div><svg id='chart' class='chart' viewBox='0 0 900 260' preserveAspectRatio='none'></svg><div id='history' class='scroll'></div></section>
<section class='cols section'><div id='datasets' class='card'><div class='key'>Datasets disponíveis</div><div id='datasetList' class='empty'>Carregando…</div></div><div class='card'><div class='key'>Leitura rápida</div><div id='insight' class='note'>Execute um backtest para gerar a análise.</div></div></section>
<section id='trades' class='card section'><div class='key'>Últimas operações</div><div id='tradeList' class='scroll empty'>Nenhuma execução.</div></section>
</main></div><script>
const brl=new Intl.NumberFormat('pt-BR',{style:'currency',currency:'BRL'}),saved=localStorage.getItem('orbisToken')||'';token.value=saved;token.addEventListener('input',()=>localStorage.setItem('orbisToken',token.value.trim()));
function pct(v){return Number(v||0).toFixed(2)+'%'}function err(t){try{return JSON.parse(t).error||t}catch(e){return t}}function date(ts){return ts?new Date(ts*1000).toLocaleString('pt-BR'):'—'}
function applyPreset(){const p=preset.value;if(p==='conservative'){risk.value=.5;stop.value=35;take.value=70;spread.value=1;fast.value=12;slow.value=30}else if(p==='aggressive'){risk.value=2;stop.value=20;take.value=40;spread.value=1;fast.value=5;slow.value=13}else{risk.value=1;stop.value=30;take.value=60;spread.value=1;fast.value=9;slow.value=21}updateRR()}
function updateRR(){rr.textContent='1:'+((+take.value||0)/Math.max(.1,+stop.value||.1)).toFixed(2)}stop.addEventListener('input',updateRR);take.addEventListener('input',updateRR);
function clearToken(){localStorage.removeItem('orbisToken');token.value='';authState.textContent='Token removido.';authState.className='note'}
function drawChart(recent){chart.innerHTML='';const items=[...(recent||[])].reverse();if(!items.length){chart.innerHTML="<text x='30' y='130' fill='#91a5bb'>Nenhuma execução registrada.</text>";return}const vals=items.map(x=>Number(x.result.final_capital||0)),min=Math.min(...vals),max=Math.max(...vals),span=Math.max(1,max-min),pts=vals.map((v,i)=>[40+i*(820/Math.max(1,vals.length-1)),220-((v-min)/span)*170,v]);const line=document.createElementNS('http://www.w3.org/2000/svg','polyline');line.setAttribute('points',pts.map(p=>p[0]+','+p[1]).join(' '));line.setAttribute('fill','none');line.setAttribute('stroke','#69e39f');line.setAttribute('stroke-width','4');chart.appendChild(line);pts.forEach(p=>{const c=document.createElementNS('http://www.w3.org/2000/svg','circle');c.setAttribute('cx',p[0]);c.setAttribute('cy',p[1]);c.setAttribute('r','5');c.setAttribute('fill','#73b8ff');chart.appendChild(c)})}
function analysis(q){if(!q)return 'Execute um backtest para gerar a análise.';const parts=[];parts.push(q.return_pct>0?'A estratégia encerrou positiva.':'A estratégia encerrou negativa.');parts.push(Number(q.profit_factor||0)>=1.5?'O profit factor é forte para esta amostra.':Number(q.profit_factor||0)>=1?'O profit factor é aceitável, mas ainda exige validação.':'As perdas superaram os ganhos brutos.');parts.push(Number(q.max_drawdown_pct||0)>20?'O drawdown está elevado.':Number(q.max_drawdown_pct||0)>10?'O drawdown merece atenção.':'O drawdown permaneceu controlado nesta amostra.');parts.push('Resultado histórico não garante desempenho futuro.');return parts.join(' ')}
async function refresh(){try{const r=await fetch('/api/summary?x='+Date.now(),{cache:'no-store'}),d=await r.json();runs.textContent=d.runs;datasetList.innerHTML=(d.datasets||[]).map(x=>`<div class='dataset'><b>${x.symbol}</b> · ${x.timeframe}<div class='sub'>${x.candles} candles · ${date(x.first_ts)} → ${date(x.last_ts)}</div></div>`).join('')||'<div class="empty">Nenhum dataset.</div>';drawChart(d.recent);history.innerHTML='<table><tr><th>ID</th><th>Par</th><th>Timeframe</th><th>Retorno</th><th>Equity final</th></tr>'+(d.recent||[]).map(x=>`<tr><td>#${x.id}</td><td>${x.symbol}</td><td>${x.timeframe}</td><td class='${Number(x.result.return_pct)>=0?'pos':'neg'}'>${pct(x.result.return_pct)}</td><td>${brl.format(x.result.final_capital)}</td></tr>`).join('')+'</table>';const q=d.latest?.result;if(!q)return;initial.textContent=brl.format(q.initial_capital);final.textContent=brl.format(q.final_capital);delta.textContent=(q.final_capital>=q.initial_capital?'+':'')+brl.format(q.final_capital-q.initial_capital);ret.textContent=pct(q.return_pct);ret.className='value '+(q.return_pct>=0?'pos':'neg');retbar.style.width=Math.min(100,Math.abs(Number(q.return_pct||0))*2)+'%';dd.textContent=pct(q.max_drawdown_pct);win.textContent=pct(q.win_rate_pct);winbar.style.width=Math.min(100,Number(q.win_rate_pct||0))+'%';pips.textContent=q.net_pips==null?'—':Number(q.net_pips).toFixed(2);pf.textContent=q.profit_factor==null?'—':Number(q.profit_factor).toFixed(2);pfLabel.textContent=Number(q.profit_factor||0)>=1.5?'Forte nesta amostra':Number(q.profit_factor||0)>=1?'Aceitável nesta amostra':'Abaixo do desejável';currentRun.textContent='#'+d.latest.id+' · '+d.latest.symbol;currentMeta.textContent=d.latest.timeframe+' · '+d.latest.strategy+' · '+date(d.latest.created_at);insight.textContent=analysis(q);tradeList.innerHTML='<table><tr><th>Lado</th><th>Entrada</th><th>Saída</th><th>Lotes</th><th>Pips</th><th>PnL</th><th>Motivo</th></tr>'+(q.trades||[]).map(t=>`<tr><td>${t.side}</td><td>${Number(t.entry??t.price).toFixed(5)}</td><td>${Number(t.price).toFixed(5)}</td><td>${t.lots??'—'}</td><td class='${Number(t.pips||0)>=0?'pos':'neg'}'>${t.pips??'—'}</td><td>${t.pnl==null?'—':brl.format(t.pnl)}</td><td>${t.reason??'—'}</td></tr>`).join('')+'</table>'}catch(e){result.textContent='Falha ao atualizar painel: '+e.message}}
async function verifyToken(){authBtn.disabled=true;authState.textContent='Validando…';try{const r=await fetch('/api/auth',{headers:{'X-Orbis-Token':token.value.trim()},cache:'no-store'}),txt=await r.text();if(!r.ok)throw new Error(err(txt));localStorage.setItem('orbisToken',token.value.trim());authState.textContent='Token válido. Backtests liberados.';authState.className='note pos'}catch(e){authState.textContent='Token inválido: '+e.message;authState.className='note neg'}finally{authBtn.disabled=false}}
async function runTest(){runBtn.disabled=true;result.textContent='Executando backtest Forex…';try{const body={symbol:symbol.value,timeframe:timeframe.value,fast:+fast.value,slow:+slow.value,capital:+capital.value,risk_pct:+risk.value,stop_pips:+stop.value,take_pips:+take.value,spread_pips:+spread.value,pip_value:+pipValue.value,max_lots:+maxLots.value};const r=await fetch('/api/backtest',{method:'POST',headers:{'Content-Type':'application/json','X-Orbis-Token':token.value.trim()},body:JSON.stringify(body)}),txt=await r.text();if(!r.ok)throw new Error(err(txt));const d=JSON.parse(txt);result.textContent=`SUCESSO · execução #${d.run_id}\n${d.symbol} · ${d.closed_trades} operações\nEquity final: ${brl.format(d.final_capital)}\nRetorno: ${pct(d.return_pct)}\nPips líquidos: ${d.net_pips}\nDrawdown: ${pct(d.max_drawdown_pct)}\nWin rate: ${pct(d.win_rate_pct)}\nProfit factor: ${d.profit_factor}`;await refresh()}catch(e){result.textContent='Falha: '+e.message}finally{runBtn.disabled=false}}
setInterval(()=>clock.textContent=new Date().toLocaleTimeString('pt-BR'),1000);updateRR();refresh();if(saved)verifyToken();setInterval(refresh,10000);
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
