#!/usr/bin/env python3
from __future__ import annotations

import csv
import io
import json
import os
import secrets
import sqlite3
import subprocess
import urllib.parse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

HOST = "0.0.0.0"
PORT = int(os.environ.get("ORBIS_TRADE_LAB_PORT", "8091"))
TOKEN_FILE = Path("/etc/orbis-web-token")
LAB_BIN = "/usr/local/bin/orbis-trade-lab"
DB = Path("/var/lib/orbis/trade/orbis_trade.db")


def token() -> str:
    try:
        return TOKEN_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def datasets() -> list[dict[str, Any]]:
    if not DB.exists():
        return []
    conn = db_connect()
    try:
        rows = conn.execute(
            "SELECT symbol,timeframe,COUNT(*) candles,MIN(ts) first_ts,MAX(ts) last_ts "
            "FROM candles GROUP BY symbol,timeframe ORDER BY symbol,timeframe"
        ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["source"] = "synthetic" if item["symbol"] == "DEMO" else "imported"
            item["is_real"] = item["symbol"] != "DEMO"
            out.append(item)
        return out
    finally:
        conn.close()


def parse_time(value: str) -> int:
    value = value.strip().replace(".", "-")
    if value.isdigit():
        n = int(value)
        return n // 1000 if n > 10_000_000_000 else n
    value = value.replace("Z", "+00:00")
    formats = (
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M", "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M",
    )
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        dt = None
        for fmt in formats:
            try:
                dt = datetime.strptime(value, fmt)
                break
            except ValueError:
                pass
        if dt is None:
            raise ValueError(f"Data inválida no CSV: {value}")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def normalized_rows(text: str, symbol: str, timeframe: str) -> list[tuple[Any, ...]]:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    raw = list(reader)
    if not raw:
        raise ValueError("CSV vazio")
    header = [c.strip().lower().replace("<", "").replace(">", "") for c in raw[0]]
    aliases = {
        "date": ("date", "data"), "time": ("time", "hora"), "timestamp": ("timestamp", "datetime", "date_time"),
        "open": ("open", "abertura"), "high": ("high", "maxima", "máxima"),
        "low": ("low", "minima", "mínima"), "close": ("close", "fechamento"),
        "volume": ("volume", "tickvol", "tick_volume", "vol"),
    }
    def idx(name: str) -> int | None:
        for alias in aliases[name]:
            if alias in header:
                return header.index(alias)
        return None
    oi, hi, li, ci = idx("open"), idx("high"), idx("low"), idx("close")
    if None in (oi, hi, li, ci):
        raise ValueError("CSV precisa conter Open, High, Low e Close")
    tsi, di, ti, vi = idx("timestamp"), idx("date"), idx("time"), idx("volume")
    if tsi is None and di is None:
        raise ValueError("CSV precisa conter Timestamp/Datetime ou Date")
    rows: list[tuple[Any, ...]] = []
    for number, row in enumerate(raw[1:], start=2):
        if not row or not any(x.strip() for x in row):
            continue
        try:
            when = row[tsi] if tsi is not None else row[di] + (" " + row[ti] if ti is not None and ti < len(row) else "")
            conv = lambda x: float(x.strip().replace(" ", "").replace(",", "."))
            rows.append((parse_time(when), symbol, timeframe, conv(row[oi]), conv(row[hi]), conv(row[li]), conv(row[ci]), conv(row[vi]) if vi is not None and vi < len(row) and row[vi].strip() else 0.0))
        except (IndexError, ValueError) as exc:
            raise ValueError(f"Linha {number} inválida: {exc}") from exc
    if len(rows) < 23:
        raise ValueError("O dataset precisa ter pelo menos 23 candles")
    return rows


def import_csv(data: dict[str, Any]) -> dict[str, Any]:
    symbol = str(data.get("symbol", "")).upper().replace("/", "").strip()[:16]
    timeframe = str(data.get("timeframe", "")).strip()[:12]
    text = str(data.get("csv_text", ""))
    if not symbol or symbol == "DEMO":
        raise ValueError("Informe um símbolo real, como EURUSD")
    if not timeframe or not text:
        raise ValueError("Informe timeframe e arquivo CSV")
    rows = normalized_rows(text, symbol, timeframe)
    conn = db_connect()
    try:
        with conn:
            conn.executemany(
                "INSERT INTO candles(ts,symbol,timeframe,open,high,low,close,volume) VALUES(?,?,?,?,?,?,?,?) "
                "ON CONFLICT(symbol,timeframe,ts) DO UPDATE SET open=excluded.open,high=excluded.high,low=excluded.low,close=excluded.close,volume=excluded.volume",
                rows,
            )
    finally:
        conn.close()
    return {"ok": True, "symbol": symbol, "timeframe": timeframe, "imported": len(rows), "source": "imported"}


def run_lab(command: str, data: dict[str, Any]) -> dict[str, Any]:
    cmd = [LAB_BIN, command]
    mapping = {
        "symbol": "--symbol", "timeframe": "--timeframe", "fast": "--fast", "slow": "--slow",
        "capital": "--capital", "risk_pct": "--risk-pct", "stop_pips": "--stop-pips",
        "take_pips": "--take-pips", "spread_pips": "--spread-pips", "pip_size": "--pip-size",
        "pip_value": "--pip-value", "max_lots": "--max-lots", "simulations": "--simulations",
        "fast_min": "--fast-min", "fast_max": "--fast-max", "fast_step": "--fast-step",
        "slow_min": "--slow-min", "slow_max": "--slow-max", "slow_step": "--slow-step", "top": "--top",
        "side": "--side", "price": "--price", "lots": "--lots", "stop": "--stop", "take": "--take", "index": "--index",
    }
    for key, flag in mapping.items():
        if key in data and data[key] not in (None, ""):
            cmd.extend([flag, str(data[key])])
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    raw = (proc.stdout or proc.stderr).strip()
    if proc.returncode != 0:
        try:
            parsed = json.loads(raw)
            raise ValueError(parsed.get("error", raw))
        except json.JSONDecodeError:
            raise ValueError(raw or f"Falha em {command} (exit {proc.returncode})")
    return json.loads(raw)


def page() -> str:
    return r"""<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Orbis Quant Lab</title><style>
:root{color-scheme:dark;--bg:#070b10;--panel:#111923;--line:#26364a;--txt:#eef5ff;--muted:#91a4bb;--green:#78e7a5;--red:#ff9696;--blue:#8dbdff;--gold:#f1ca72}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font-family:system-ui,sans-serif}.shell{display:grid;grid-template-columns:225px 1fr;min-height:100vh}.side{background:#0c1219;border-right:1px solid var(--line);padding:22px 15px}.brand{font-weight:800;letter-spacing:.12em}.sub,.muted{color:var(--muted)}.nav button{display:block;width:100%;text-align:left;margin-top:8px;background:transparent;border:0;color:#cad7e7;padding:11px;border-radius:8px}.nav button.active{background:#192536}.main{padding:18px;max-width:1400px;width:100%;margin:auto}.top{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--line);padding-bottom:15px}.card{background:var(--panel);border:1px solid var(--line);border-radius:13px;padding:15px;margin-top:14px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}.key{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}.value{font-size:21px;margin-top:6px}.form{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}label{font-size:13px;color:#cbd7e7}input,select,button{width:100%;padding:10px;margin-top:5px;background:#0c141e;color:#fff;border:1px solid #39506b;border-radius:8px}button{cursor:pointer;background:#214d39;width:auto}.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.tab{display:none}.tab.active{display:block}pre{white-space:pre-wrap;background:#070a0e;padding:12px;border-radius:8px;overflow:auto;max-height:420px}.pos{color:var(--green)}.neg{color:var(--red)}.warn{color:var(--gold)}table{width:100%;border-collapse:collapse;font-size:13px}th,td{padding:8px;border-bottom:1px solid var(--line);text-align:left}.scroll{overflow:auto}.badge{display:inline-block;padding:4px 8px;border-radius:20px;font-size:11px;background:#1a2635}.real{color:var(--green)}.fake{color:var(--gold)}canvas{width:100%;height:260px;background:#080d13;border:1px solid var(--line);border-radius:10px}@media(max-width:800px){.shell{display:block}.side{border-right:0;border-bottom:1px solid var(--line)}.nav{display:flex;overflow:auto}.nav button{white-space:nowrap;width:auto}.main{padding:12px}}
</style></head><body><div class='shell'><aside class='side'><div class='brand'>ORBIS QUANT LAB</div><div class='sub'>Forex research workstation</div><div class='nav'><button class='active' data-tab='analyze'>Análise</button><button data-tab='data'>Dados reais</button><button data-tab='optimize'>Otimização</button><button data-tab='monte'>Monte Carlo</button><button data-tab='paper'>Paper Trading</button><button onclick="location.href='http://100.87.144.114:8090/'">Painel clássico</button></div></aside><main class='main'>
<div class='top'><div><div class='key'>ORBIS TRADE 2.1</div><h2 style='margin:4px 0'>Laboratório quantitativo</h2></div><div><span class='pos'>● Motor online</span><div id='clock' class='muted'></div></div></div>
<section class='card'><div class='key'>Autenticação</div><div class='form'><label>Token<input id='token' type='password'></label></div><div class='actions'><button id='auth'>Validar</button><button id='reloadData'>Atualizar datasets</button></div><div id='authState' class='muted'>Token não validado.</div></section>
<div id='analyze' class='tab active'><section class='card'><div class='key'>Dataset selecionado</div><div id='datasetNotice' class='warn'>Carregando datasets...</div></section><section class='card'><div class='key'>Analisar estratégia</div><div class='form'>
<label>Dataset<select id='a_dataset'></select></label><label>SMA rápida<input id='a_fast' value='9' type='number'></label><label>SMA lenta<input id='a_slow' value='21' type='number'></label><label>Capital (R$)<input id='a_capital' value='10000' type='number'></label><label>Risco (%)<input id='a_risk_pct' value='1' type='number' step='.1'></label><label>Stop (pips)<input id='a_stop_pips' value='30' type='number'></label><label>Alvo (pips)<input id='a_take_pips' value='60' type='number'></label><label>Spread<input id='a_spread_pips' value='1' type='number' step='.1'></label><label>Pip size<input id='a_pip_size' value='.01' type='number' step='.0001'></label><label>Valor pip/lote<input id='a_pip_value' value='10' type='number'></label><label>Lote máximo<input id='a_max_lots' value='10' type='number'></label></div><button id='analyzeBtn'>Executar análise</button><pre id='analyzeOut'>Pronto.</pre></section><section id='metrics' class='grid'></section><section class='card'><div class='key'>Curva de equity</div><canvas id='equity'></canvas></section><section class='card'><div class='key'>Análise Orbis</div><div id='ai'>Nenhuma análise.</div></section><section class='card'><div class='key'>Operações</div><div id='trades' class='scroll'>Nenhuma operação.</div></section></div>
<div id='data' class='tab'><section class='card'><div class='key'>Datasets instalados</div><div id='datasets'>Carregando...</div></section><section class='card'><div class='key'>Importar CSV do MetaTrader / OHLC</div><p class='muted'>O arquivo DEMO é sintético. Para testar mercado real, exporte candles do MT4/MT5 e importe aqui. Colunas aceitas: Date+Time ou Timestamp, Open, High, Low, Close e Volume opcional.</p><div class='form'><label>Símbolo<input id='i_symbol' value='EURUSD'></label><label>Timeframe<select id='i_timeframe'><option>1m</option><option>5m</option><option>15m</option><option>30m</option><option selected>1h</option><option>4h</option><option>1d</option></select></label><label>Arquivo CSV<input id='i_file' type='file' accept='.csv,.txt'></label></div><button id='importBtn'>Importar dataset real</button><pre id='importOut'>Aguardando arquivo.</pre></section></div>
<div id='optimize' class='tab'><section class='card'><div class='key'>Otimização de parâmetros</div><div class='form'><label>Dataset<select id='o_dataset'></select></label><label>Capital<input id='o_capital' value='10000' type='number'></label><label>Pip size<input id='o_pip_size' value='.01' type='number' step='.0001'></label><label>Rápida mín.<input id='o_fast_min' value='5' type='number'></label><label>Rápida máx.<input id='o_fast_max' value='20' type='number'></label><label>Lenta mín.<input id='o_slow_min' value='20' type='number'></label><label>Lenta máx.<input id='o_slow_max' value='80' type='number'></label><label>Passo lenta<input id='o_slow_step' value='5' type='number'></label><label>Top<input id='o_top' value='10' type='number'></label></div><button id='optBtn'>Otimizar</button><pre id='optOut'>Pronto.</pre><div id='optTable' class='scroll'></div></section></div>
<div id='monte' class='tab'><section class='card'><div class='key'>Monte Carlo</div><p class='muted'>Reamostra as operações e estima cenários de capital, drawdown e ruína.</p><div class='form'><label>Dataset<select id='m_dataset'></select></label><label>SMA rápida<input id='m_fast' value='9' type='number'></label><label>SMA lenta<input id='m_slow' value='21' type='number'></label><label>Capital<input id='m_capital' value='10000' type='number'></label><label>Pip size<input id='m_pip_size' value='.01' type='number' step='.0001'></label><label>Simulações<input id='m_simulations' value='1000' type='number'></label></div><button id='monteBtn'>Simular</button><pre id='monteOut'>Pronto.</pre></section></div>
<div id='paper' class='tab'><section class='card'><div class='key'>Conta simulada</div><div class='actions'><button id='paperInit'>Criar/Reiniciar R$ 10.000</button><button id='paperStatus'>Atualizar conta</button></div><pre id='paperOut'>Pronto.</pre></section><section class='card'><div class='key'>Nova posição</div><div class='form'><label>Ativo<input id='p_symbol' value='EURUSD'></label><label>Lado<select id='p_side'><option>BUY</option><option>SELL</option></select></label><label>Preço<input id='p_price' value='1.085' type='number' step='.00001'></label><label>Lotes<input id='p_lots' value='.1' type='number' step='.01'></label><label>Stop<input id='p_stop' value='1.082' type='number' step='.00001'></label><label>Alvo<input id='p_take' value='1.091' type='number' step='.00001'></label></div><button id='paperOrder'>Abrir posição</button></section></div>
<section class='card'><div class='key'>Diagnóstico</div><div id='diag' class='muted'>Inicializando...</div></section></main></div><script>
'use strict';const $=id=>document.getElementById(id),tok=()=>$('token').value.trim();let sets=[];function show(id,obj){$(id).textContent=typeof obj==='string'?obj:JSON.stringify(obj,null,2)}function diag(s,ok=true){$('diag').textContent=(ok?'OK · ':'ERRO · ')+s+' · '+new Date().toLocaleTimeString('pt-BR')}async function api(path,body){const r=await fetch(path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json','X-Orbis-Token':tok()},body:body?JSON.stringify(body):undefined,cache:'no-store'}),t=await r.text();if(!r.ok)throw new Error((()=>{try{return JSON.parse(t).error}catch{return t}})());return JSON.parse(t)}function selected(id){const [symbol,timeframe]=$(id).value.split('|');return{symbol,timeframe}}function pipFor(symbol){return symbol==='DEMO'||symbol.endsWith('JPY')?.01:.0001}function syncPip(){const d=selected('a_dataset');$('a_pip_size').value=pipFor(d.symbol)}
function draw(curve){const c=$('equity'),x=c.getContext('2d'),w=c.clientWidth,h=c.clientHeight,r=devicePixelRatio||1;c.width=w*r;c.height=h*r;x.scale(r,r);x.clearRect(0,0,w,h);if(!curve?.length){x.fillStyle='#91a4bb';x.fillText('Sem curva de equity',20,h/2);return}const mn=Math.min(...curve),mx=Math.max(...curve),sp=Math.max(1,mx-mn),p=25;x.strokeStyle='#78e7a5';x.lineWidth=2;x.beginPath();curve.forEach((v,i)=>{const px=p+i*(w-2*p)/Math.max(1,curve.length-1),py=h-p-(v-mn)/sp*(h-2*p);i?x.lineTo(px,py):x.moveTo(px,py)});x.stroke()}
async function loadSets(){sets=await api('/api/datasets');const html=sets.map(x=>`<option value='${x.symbol}|${x.timeframe}'>${x.symbol} · ${x.timeframe} · ${x.candles} candles · ${x.is_real?'REAL':'DEMO'}</option>`).join('');['a_dataset','o_dataset','m_dataset'].forEach(id=>$(id).innerHTML=html);$('datasets').innerHTML=sets.map(x=>`<p><b>${x.symbol}/${x.timeframe}</b> · ${x.candles} candles · <span class='badge ${x.is_real?'real':'fake'}'>${x.is_real?'DADOS IMPORTADOS':'DADOS SINTÉTICOS'}</span></p>`).join('')||'Nenhum dataset.';syncPip();notice();diag('Datasets carregados')}
function notice(){const d=selected('a_dataset'),s=sets.find(x=>x.symbol===d.symbol&&x.timeframe===d.timeframe);$('datasetNotice').innerHTML=s?.is_real?`<span class='real'>DADOS REAIS IMPORTADOS</span> · ${s.candles} candles`:`<span class='fake'>DEMO SINTÉTICO</span> · serve para validar o motor, não para avaliar lucratividade real.`}
document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{document.querySelectorAll('[data-tab]').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));b.classList.add('active');$(b.dataset.tab).classList.add('active')});const saved=localStorage.getItem('orbisToken')||'';$('token').value=saved;$('token').oninput=()=>localStorage.setItem('orbisToken',tok());$('auth').onclick=async()=>{try{await api('/api/auth');$('authState').textContent='Token válido.';$('authState').className='pos';await loadSets()}catch(e){$('authState').textContent=e.message;$('authState').className='neg'}};$('reloadData').onclick=loadSets;$('a_dataset').onchange=()=>{syncPip();notice()};
$('analyzeBtn').onclick=async()=>{show('analyzeOut','Executando...');try{const ds=selected('a_dataset'),d=await api('/api/lab/analyze',{...ds,fast:+a_fast.value,slow:+a_slow.value,capital:+a_capital.value,risk_pct:+a_risk_pct.value,stop_pips:+a_stop_pips.value,take_pips:+a_take_pips.value,spread_pips:+a_spread_pips.value,pip_size:+a_pip_size.value,pip_value:+a_pip_value.value,max_lots:+a_max_lots.value});show('analyzeOut',{strategy:d.strategy,candles:d.candles,final_capital:d.final_capital,return_pct:d.return_pct,verdict:d.ai_analysis?.verdict});const f=[['Retorno',d.return_pct+'%'],['Drawdown',d.max_drawdown_pct+'%'],['Profit factor',d.profit_factor],['Sharpe',d.sharpe],['Sortino',d.sortino],['Expectância','R$ '+d.expectancy],['Operações',d.closed_trades],['Win rate',d.win_rate_pct+'%'],['Payoff',d.payoff],['Recovery',d.recovery_factor]];$('metrics').innerHTML=f.map(x=>`<div class='card'><div class='key'>${x[0]}</div><div class='value'>${x[1]}</div></div>`).join('');$('ai').innerHTML=`<h3>${d.ai_analysis?.verdict||'N/D'}</h3><ul>${(d.ai_analysis?.notes||[]).map(n=>`<li>${n}</li>`).join('')}</ul>`;draw(d.equity_curve);$('trades').innerHTML='<table><tr><th>Lado</th><th>Entrada</th><th>Saída</th><th>Pips</th><th>PnL</th><th>Motivo</th></tr>'+(d.trades||[]).map(t=>`<tr><td>${t.side}</td><td>${t.entry}</td><td>${t.exit}</td><td>${t.pips}</td><td>R$ ${t.pnl}</td><td>${t.reason}</td></tr>`).join('')+'</table>';diag('Análise concluída')}catch(e){show('analyzeOut','Falha: '+e.message);diag(e.message,false)}};
$('importBtn').onclick=async()=>{try{const f=$('i_file').files[0];if(!f)throw new Error('Selecione um CSV');show('importOut','Lendo e importando...');const d=await api('/api/import',{symbol:i_symbol.value,timeframe:i_timeframe.value,csv_text:await f.text()});show('importOut',d);await loadSets();diag('Dataset real importado')}catch(e){show('importOut','Falha: '+e.message);diag(e.message,false)}};
$('optBtn').onclick=async()=>{show('optOut','Otimizando...');try{const ds=selected('o_dataset'),d=await api('/api/lab/optimize',{...ds,capital:+o_capital.value,pip_size:+o_pip_size.value,fast_min:+o_fast_min.value,fast_max:+o_fast_max.value,slow_min:+o_slow_min.value,slow_max:+o_slow_max.value,slow_step:+o_slow_step.value,top:+o_top.value});show('optOut',{tested:d.tested});$('optTable').innerHTML='<table><tr><th>Rápida</th><th>Lenta</th><th>Score</th><th>Retorno</th><th>DD</th><th>PF</th></tr>'+d.top.map(x=>`<tr><td>${x.fast}</td><td>${x.slow}</td><td>${x.score}</td><td>${x.return_pct}%</td><td>${x.drawdown_pct}%</td><td>${x.profit_factor}</td></tr>`).join('')+'</table>';diag('Otimização concluída')}catch(e){show('optOut','Falha: '+e.message);diag(e.message,false)}};
$('monteBtn').onclick=async()=>{show('monteOut','Simulando...');try{const ds=selected('m_dataset'),d=await api('/api/lab/monte-carlo',{...ds,fast:+m_fast.value,slow:+m_slow.value,capital:+m_capital.value,pip_size:+m_pip_size.value,simulations:+m_simulations.value});show('monteOut',d);diag('Monte Carlo concluído')}catch(e){show('monteOut','Falha: '+e.message);diag(e.message,false)}};
$('paperInit').onclick=async()=>{try{show('paperOut',await api('/api/lab/paper-init',{capital:10000}));diag('Conta simulada criada')}catch(e){diag(e.message,false)}};$('paperStatus').onclick=async()=>{try{show('paperOut',await api('/api/lab/paper-status',{}))}catch(e){diag(e.message,false)}};$('paperOrder').onclick=async()=>{try{show('paperOut',await api('/api/lab/paper-order',{symbol:p_symbol.value,side:p_side.value,price:+p_price.value,lots:+p_lots.value,stop:+p_stop.value,take:+p_take.value}));diag('Posição simulada aberta')}catch(e){diag(e.message,false)}};setInterval(()=>clock.textContent=new Date().toLocaleString('pt-BR'),1000);if(saved){api('/api/auth').then(loadSets).catch(e=>diag(e.message,false))}
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
            ok = self.authorized()
            self.send_body(json.dumps({"ok": True} if ok else {"error": "não autorizado"}).encode(), "application/json", 200 if ok else 401)
        elif path == "/api/datasets":
            if not self.authorized():
                self.send_body(json.dumps({"error": "não autorizado"}).encode(), "application/json", 401)
            else:
                self.send_body(json.dumps(datasets(), ensure_ascii=False).encode(), "application/json; charset=utf-8")
        elif path == "/":
            self.send_body(page().encode(), "text/html; charset=utf-8")
        else:
            self.send_body(b"not found\n", "text/plain", 404)

    def do_POST(self) -> None:
        path = urllib.parse.urlsplit(self.path).path
        if not self.authorized():
            self.send_body(json.dumps({"error": "não autorizado"}).encode(), "application/json", 401)
            return
        try:
            length = min(int(self.headers.get("Content-Length", "0") or 0), 25_000_000)
            data = json.loads(self.rfile.read(length) or b"{}")
            if path == "/api/import":
                result = import_csv(data)
            else:
                routes = {
                    "/api/lab/analyze": "analyze", "/api/lab/optimize": "optimize",
                    "/api/lab/monte-carlo": "monte-carlo", "/api/lab/paper-init": "paper-init",
                    "/api/lab/paper-status": "paper-status", "/api/lab/paper-order": "paper-order",
                    "/api/lab/paper-close": "paper-close",
                }
                if path not in routes:
                    self.send_body(b"not found\n", "text/plain", 404)
                    return
                result = run_lab(routes[path], data)
            self.send_body(json.dumps(result, ensure_ascii=False).encode(), "application/json; charset=utf-8")
        except (ValueError, OSError, sqlite3.Error, subprocess.SubprocessError, json.JSONDecodeError) as exc:
            self.send_body(json.dumps({"error": str(exc)}, ensure_ascii=False).encode(), "application/json; charset=utf-8", 400)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Orbis Quant Lab Web: http://{HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
