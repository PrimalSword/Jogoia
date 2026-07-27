#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import random
import sqlite3
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

DB_DEFAULT = Path('/var/lib/orbis/trade/orbis_trade.db')
PAPER_DEFAULT = Path('/var/lib/orbis/trade/paper_account.json')


@dataclass(frozen=True)
class Candle:
    ts: int
    symbol: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: float


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def candles(conn: sqlite3.Connection, symbol: str, timeframe: str) -> list[Candle]:
    rows = conn.execute(
        'SELECT ts,symbol,timeframe,open,high,low,close,volume FROM candles WHERE symbol=? AND timeframe=? ORDER BY ts',
        (symbol.upper(), timeframe),
    ).fetchall()
    return [Candle(**dict(r)) for r in rows]


def sma(values: list[float], period: int, i: int) -> float | None:
    if period < 1 or i + 1 < period:
        return None
    return statistics.fmean(values[i + 1 - period:i + 1])


def ema(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    seed = statistics.fmean(values[:period])
    out[period - 1] = seed
    alpha = 2 / (period + 1)
    prev = seed
    for i in range(period, len(values)):
        prev = alpha * values[i] + (1 - alpha) * prev
        out[i] = prev
    return out


def rsi(values: list[float], period: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) <= period:
        return out
    gains, losses = [], []
    for i in range(1, period + 1):
        d = values[i] - values[i - 1]
        gains.append(max(d, 0)); losses.append(max(-d, 0))
    avg_gain = statistics.fmean(gains); avg_loss = statistics.fmean(losses)
    out[period] = 100 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    for i in range(period + 1, len(values)):
        d = values[i] - values[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(d, 0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-d, 0)) / period
        out[i] = 100 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    return out


def atr(data: list[Candle], period: int = 14) -> list[float | None]:
    tr: list[float] = []
    for i, c in enumerate(data):
        prev = data[i - 1].close if i else c.close
        tr.append(max(c.high - c.low, abs(c.high - prev), abs(c.low - prev)))
    out: list[float | None] = [None] * len(data)
    for i in range(period - 1, len(data)):
        out[i] = statistics.fmean(tr[i + 1 - period:i + 1])
    return out


def drawdown(curve: Iterable[float]) -> float:
    peak = 0.0; worst = 0.0
    for x in curve:
        peak = max(peak, x)
        if peak:
            worst = max(worst, (peak - x) / peak)
    return worst


def backtest(data: list[Candle], fast: int, slow: int, capital: float, risk_pct: float,
             stop_pips: float, take_pips: float, spread_pips: float, pip_size: float,
             pip_value: float, max_lots: float) -> dict:
    if fast < 1 or slow <= fast:
        raise ValueError('Use 1 <= rápida < lenta')
    if len(data) < slow + 2:
        raise ValueError(f'São necessários pelo menos {slow + 2} candles')
    closes = [c.close for c in data]
    equity = capital
    curve = [capital]
    position = None
    trades: list[dict] = []
    gross_profit = gross_loss = 0.0
    wins = losses = 0
    streak_win = streak_loss = best_win = worst_loss = 0

    def close_trade(c: Candle, price: float, reason: str) -> None:
        nonlocal equity, position, gross_profit, gross_loss, wins, losses, streak_win, streak_loss, best_win, worst_loss
        assert position is not None
        direction = 1 if position['side'] == 'BUY' else -1
        pips = ((price - position['entry']) * direction / pip_size) - spread_pips
        pnl = pips * pip_value * position['lots']
        equity += pnl
        if pnl > 0:
            gross_profit += pnl; wins += 1; streak_win += 1; streak_loss = 0; best_win = max(best_win, streak_win)
        else:
            gross_loss += abs(pnl); losses += 1; streak_loss += 1; streak_win = 0; worst_loss = max(worst_loss, streak_loss)
        trades.append({**position, 'exit_ts': c.ts, 'exit': round(price, 6), 'pips': round(pips, 2), 'pnl': round(pnl, 2), 'reason': reason, 'equity': round(equity, 2)})
        position = None

    for i, c in enumerate(data):
        f = sma(closes, fast, i); s = sma(closes, slow, i)
        fp = sma(closes, fast, i - 1) if i else None; sp = sma(closes, slow, i - 1) if i else None
        if position:
            if position['side'] == 'BUY':
                if c.low <= position['stop']:
                    close_trade(c, position['stop'], 'STOP')
                elif c.high >= position['take']:
                    close_trade(c, position['take'], 'TAKE')
            else:
                if c.high >= position['stop']:
                    close_trade(c, position['stop'], 'STOP')
                elif c.low <= position['take']:
                    close_trade(c, position['take'], 'TAKE')
        if None not in (f, s, fp, sp):
            up = fp <= sp and f > s
            down = fp >= sp and f < s
            if position and ((position['side'] == 'BUY' and down) or (position['side'] == 'SELL' and up)):
                close_trade(c, c.close, 'SIGNAL')
            if not position and (up or down):
                risk_money = equity * risk_pct / 100
                lots = min(max_lots, max(0.01, risk_money / (stop_pips * pip_value)))
                side = 'BUY' if up else 'SELL'
                direction = 1 if side == 'BUY' else -1
                position = {'side': side, 'entry_ts': c.ts, 'entry': c.close, 'lots': round(lots, 2),
                            'stop': c.close - direction * stop_pips * pip_size,
                            'take': c.close + direction * take_pips * pip_size}
        curve.append(equity)
    if position:
        close_trade(data[-1], data[-1].close, 'FIM_DADOS')
        curve.append(equity)
    pnls = [t['pnl'] for t in trades]
    returns = [(curve[i] / curve[i-1] - 1) for i in range(1, len(curve)) if curve[i-1]]
    mean_r = statistics.fmean(returns) if returns else 0
    std_r = statistics.pstdev(returns) if len(returns) > 1 else 0
    downside = [r for r in returns if r < 0]
    downside_std = statistics.pstdev(downside) if len(downside) > 1 else 0
    pf = gross_profit / gross_loss if gross_loss else (999.0 if gross_profit else 0.0)
    expectancy = statistics.fmean(pnls) if pnls else 0
    avg_win = statistics.fmean([x for x in pnls if x > 0]) if wins else 0
    avg_loss = abs(statistics.fmean([x for x in pnls if x <= 0])) if losses else 0
    max_dd = drawdown(curve)
    result = {
        'strategy': 'forex_sma_risk_v2', 'candles': len(data), 'fast': fast, 'slow': slow,
        'initial_capital': round(capital, 2), 'final_capital': round(equity, 2),
        'return_pct': round((equity / capital - 1) * 100, 4), 'max_drawdown_pct': round(max_dd * 100, 4),
        'closed_trades': len(trades), 'wins': wins, 'losses': losses,
        'win_rate_pct': round(wins / len(trades) * 100, 2) if trades else 0,
        'profit_factor': round(pf, 3), 'expectancy': round(expectancy, 2),
        'payoff': round(avg_win / avg_loss, 3) if avg_loss else 0,
        'sharpe': round(mean_r / std_r * math.sqrt(252), 3) if std_r else 0,
        'sortino': round(mean_r / downside_std * math.sqrt(252), 3) if downside_std else 0,
        'recovery_factor': round(((equity / capital - 1) / max_dd), 3) if max_dd else 0,
        'best_win_streak': best_win, 'worst_loss_streak': worst_loss,
        'net_pips': round(sum(t['pips'] for t in trades), 2), 'equity_curve': [round(x, 2) for x in curve],
        'trades': trades,
    }
    result['ai_analysis'] = explain(result)
    return result


def explain(r: dict) -> dict:
    notes: list[str] = []
    pf = r.get('profit_factor', 0); dd = r.get('max_drawdown_pct', 0); n = r.get('closed_trades', 0)
    if n < 30: notes.append('Amostra pequena: valide com pelo menos 30 operações antes de concluir robustez.')
    if pf < 1: notes.append('Estratégia destrutiva no conjunto atual: perdas superam ganhos.')
    elif pf < 1.3: notes.append('Vantagem estatística fraca; custos e slippage podem eliminar o resultado.')
    elif pf >= 1.8: notes.append('Profit factor forte no conjunto analisado; prossiga para walk-forward e Monte Carlo.')
    if dd > 20: notes.append('Drawdown elevado; reduza risco por operação ou adicione filtro de volatilidade.')
    if r.get('worst_loss_streak', 0) >= 5: notes.append('Sequência de perdas relevante; dimensione capital para suportar a pior série.')
    if r.get('sharpe', 0) < 0.5: notes.append('Retorno ajustado ao risco baixo.')
    verdict = 'REJEITAR' if pf < 1 or r.get('return_pct', 0) <= 0 else ('VALIDAR' if n < 30 else 'PROMISSORA')
    return {'verdict': verdict, 'notes': notes}


def optimize(data: list[Candle], args: argparse.Namespace) -> dict:
    rows = []
    for fast in range(args.fast_min, args.fast_max + 1, args.fast_step):
        for slow in range(args.slow_min, args.slow_max + 1, args.slow_step):
            if slow <= fast: continue
            try:
                r = backtest(data, fast, slow, args.capital, args.risk_pct, args.stop_pips, args.take_pips,
                             args.spread_pips, args.pip_size, args.pip_value, args.max_lots)
                score = r['return_pct'] - r['max_drawdown_pct'] * args.dd_penalty
                rows.append({'fast': fast, 'slow': slow, 'score': round(score, 4), 'return_pct': r['return_pct'],
                             'drawdown_pct': r['max_drawdown_pct'], 'profit_factor': r['profit_factor'],
                             'trades': r['closed_trades']})
            except ValueError:
                pass
    rows.sort(key=lambda x: x['score'], reverse=True)
    return {'tested': len(rows), 'top': rows[:args.top]}


def monte_carlo(pnls: list[float], capital: float, simulations: int, seed: int) -> dict:
    if not pnls: raise ValueError('Nenhuma operação disponível')
    rng = random.Random(seed)
    finals, dds, ruin = [], [], 0
    for _ in range(simulations):
        eq = capital; curve = [eq]
        for _ in pnls:
            eq += rng.choice(pnls); curve.append(eq)
            if eq <= 0: ruin += 1; break
        finals.append(eq); dds.append(drawdown(curve) * 100)
    finals.sort(); dds.sort()
    q = lambda xs, p: xs[min(len(xs)-1, int((len(xs)-1)*p))]
    return {'simulations': simulations, 'median_final': round(q(finals, .5), 2),
            'p05_final': round(q(finals, .05), 2), 'p95_final': round(q(finals, .95), 2),
            'median_drawdown_pct': round(q(dds, .5), 2), 'p95_drawdown_pct': round(q(dds, .95), 2),
            'ruin_probability_pct': round(ruin / simulations * 100, 2)}


def load_paper(path: Path) -> dict:
    if path.exists(): return json.loads(path.read_text())
    return {'cash': 10000.0, 'equity': 10000.0, 'positions': [], 'history': [], 'created_at': int(time.time())}


def save_paper(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description='Orbis Quant Lab — pesquisa, robustez e paper trading local')
    p.add_argument('--db', type=Path, default=DB_DEFAULT)
    sub = p.add_subparsers(dest='cmd', required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--symbol', required=True); common.add_argument('--timeframe', default='1h')
    common.add_argument('--fast', type=int, default=9); common.add_argument('--slow', type=int, default=21)
    common.add_argument('--capital', type=float, default=10000); common.add_argument('--risk-pct', type=float, default=1)
    common.add_argument('--stop-pips', type=float, default=30); common.add_argument('--take-pips', type=float, default=60)
    common.add_argument('--spread-pips', type=float, default=1); common.add_argument('--pip-size', type=float, default=.0001)
    common.add_argument('--pip-value', type=float, default=10); common.add_argument('--max-lots', type=float, default=10)
    sub.add_parser('analyze', parents=[common])
    o = sub.add_parser('optimize', parents=[common]); o.add_argument('--fast-min', type=int, default=5); o.add_argument('--fast-max', type=int, default=20); o.add_argument('--fast-step', type=int, default=1); o.add_argument('--slow-min', type=int, default=20); o.add_argument('--slow-max', type=int, default=80); o.add_argument('--slow-step', type=int, default=5); o.add_argument('--top', type=int, default=20); o.add_argument('--dd-penalty', type=float, default=.5)
    m = sub.add_parser('monte-carlo', parents=[common]); m.add_argument('--simulations', type=int, default=1000); m.add_argument('--seed', type=int, default=42)
    pi = sub.add_parser('paper-init'); pi.add_argument('--file', type=Path, default=PAPER_DEFAULT); pi.add_argument('--capital', type=float, default=10000)
    ps = sub.add_parser('paper-status'); ps.add_argument('--file', type=Path, default=PAPER_DEFAULT)
    po = sub.add_parser('paper-order'); po.add_argument('--file', type=Path, default=PAPER_DEFAULT); po.add_argument('--symbol', required=True); po.add_argument('--side', choices=['BUY','SELL'], required=True); po.add_argument('--price', type=float, required=True); po.add_argument('--lots', type=float, required=True); po.add_argument('--stop', type=float); po.add_argument('--take', type=float)
    pc = sub.add_parser('paper-close'); pc.add_argument('--file', type=Path, default=PAPER_DEFAULT); pc.add_argument('--index', type=int, required=True); pc.add_argument('--price', type=float, required=True); pc.add_argument('--pip-size', type=float, default=.0001); pc.add_argument('--pip-value', type=float, default=10)
    return p


def main() -> int:
    args = parser().parse_args()
    try:
        if args.cmd.startswith('paper'):
            if args.cmd == 'paper-init':
                d = {'cash': args.capital, 'equity': args.capital, 'positions': [], 'history': [], 'created_at': int(time.time())}; save_paper(args.file, d); out = d
            elif args.cmd == 'paper-status': out = load_paper(args.file)
            elif args.cmd == 'paper-order':
                d = load_paper(args.file); d['positions'].append({'symbol': args.symbol.upper(), 'side': args.side, 'entry': args.price, 'lots': args.lots, 'stop': args.stop, 'take': args.take, 'opened_at': int(time.time())}); save_paper(args.file, d); out = d
            else:
                d = load_paper(args.file); pos = d['positions'].pop(args.index); direction = 1 if pos['side']=='BUY' else -1; pips=(args.price-pos['entry'])*direction/args.pip_size; pnl=pips*args.pip_value*pos['lots']; d['cash'] += pnl; d['equity']=d['cash']; d['history'].append({**pos,'exit':args.price,'pips':round(pips,2),'pnl':round(pnl,2),'closed_at':int(time.time())}); save_paper(args.file,d); out=d
        else:
            conn = connect(args.db); data = candles(conn, args.symbol, args.timeframe); conn.close()
            r = backtest(data, args.fast, args.slow, args.capital, args.risk_pct, args.stop_pips, args.take_pips, args.spread_pips, args.pip_size, args.pip_value, args.max_lots)
            if args.cmd == 'analyze': out = r
            elif args.cmd == 'optimize': out = optimize(data, args)
            else: out = monte_carlo([t['pnl'] for t in r['trades']], args.capital, args.simulations, args.seed)
        print(json.dumps(out, ensure_ascii=False, indent=2)); return 0
    except (OSError, ValueError, sqlite3.Error, IndexError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False)); return 1


if __name__ == '__main__':
    raise SystemExit(main())
