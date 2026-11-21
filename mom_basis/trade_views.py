"""Read-only archive and real OHLC views. Latest-five alerts remain separate."""
import json
import math
from .model import BAR, BUDGET, COINS, clean


def summary(trade):
    keys=('id','coin','symbol','direction','entry_ms','exit_ms','entry_price','exit_price',
          'net_pnl','gross_return','net_return','order_budget','settlement','status','status_label')
    r={k:trade.get(k) for k in keys}
    settled=trade.get('exit_price') is not None and trade.get('net_pnl') is not None
    r['return_on_budget']=trade['net_pnl']/trade.get('order_budget',BUDGET) if settled else None
    tag=('TP' if trade['net_pnl']>0 else 'SL' if trade['net_pnl']<0 else 'FLAT') if settled else None
    r['result_tag']=tag
    r['exit_reason']='TIME_4H' if settled else None
    r['exit_label']=(('Hòa vốn' if tag=='FLAT' else tag)+' · Thoát sau 4h') if settled else 'Thoát dự kiến sau 4h'
    return clean(r)


def list_trades(store,coin,now_ms,limit=50,offset=0):
    with store.connect() as c:
        c.execute('BEGIN')
        count=c.execute('SELECT COUNT(*) FROM trades WHERE coin=?',(coin,)).fetchone()[0]
        rows=c.execute('SELECT data FROM trades WHERE coin=? ORDER BY entry_ms DESC,id DESC LIMIT ? OFFSET ?',
            (coin,limit,offset)).fetchall()
        asof=store.get(c,'continuous_asof_ms')
    return dict(coin=coin,total=count,offset=offset,limit=limit,data_as_of_ms=asof,
        items=[summary(store.view(json.loads(r[0]),now_ms)) for r in rows])


def trade_detail(store,sid,now_ms):
    with store.connect() as c:
        c.execute('BEGIN')
        row=c.execute('SELECT data FROM trades WHERE id=?',(sid,)).fetchone()
        if not row:return None
        t=json.loads(row[0]);coin=t['coin'];entry=t['entry_ms'];deadline=t['exit_ms']
        order=(coin,entry,entry,sid)
        older=c.execute('SELECT id FROM trades WHERE coin=? AND (entry_ms<? OR (entry_ms=? AND id<?)) ORDER BY entry_ms DESC,id DESC LIMIT 1',order).fetchone()
        newer=c.execute('SELECT id FROM trades WHERE coin=? AND (entry_ms>? OR (entry_ms=? AND id>?)) ORDER BY entry_ms,id LIMIT 1',order).fetchone()
        total=c.execute('SELECT COUNT(*) FROM trades WHERE coin=?',(coin,)).fetchone()[0]
        position=c.execute('SELECT COUNT(*) FROM trades WHERE coin=? AND (entry_ms<? OR (entry_ms=? AND id<=?))',order).fetchone()[0]
        asof=store.get(c,'continuous_asof_ms',now_ms//BAR*BAR)
        start=entry-32*BAR
        end=max(deadline,min(deadline+8*BAR,asof))
        observed_end=min(end,asof,now_ms//BAR*BAR)
        rows=[]
        if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='history_bars'").fetchone():
            rows=c.execute('SELECT timestamp_ms,open,high,low,close,is_closed FROM history_bars WHERE coin=? AND timestamp_ms>=? AND timestamp_ms<=? ORDER BY timestamp_ms',
                (coin,start,observed_end)).fetchall()
        updates=store.get(c,'chart_candle_updates',{}).get(coin)
    candles=[]
    for r in rows:
        values=[r[k] for k in ('open','high','low','close')]
        if not all(v is not None and math.isfinite(v) and v>0 for v in values):continue
        candles.append(dict(time_ms=r['timestamp_ms'],open=r['open'],high=r['high'],low=r['low'],close=r['close'],
            closed=bool(r['is_closed']) and r['timestamp_ms']+BAR<=now_ms))
    view=store.view(t,now_ms);view.update(summary(view))
    closed_expected=max(0,(min(observed_end,now_ms//BAR*BAR-BAR)-start)//BAR+1)
    closed_count=sum(r['closed'] for r in candles)
    return dict(trade=view,navigation=dict(previous_id=older[0] if older else None,
        next_id=newer[0] if newer else None,position=position,total=total,coin=coin),
        chart=dict(interval_ms=BAR,start_ms=start,end_ms=end,observed_through_ms=observed_end,
            data_as_of_ms=asof,candles=candles,current_candle_update=updates,
            missing_closed_bars=max(0,closed_expected-closed_count),
            source='Binance USD-M real 15m OHLC',
            entry_marker=dict(time_ms=entry,price=t['entry_price'],label='ENTRY'),
            exit_marker=dict(time_ms=deadline,price=t['exit_price'],label=view['exit_label'],
                kind='REALIZED' if t['exit_price'] is not None else 'SCHEDULED',reason='TIME_4H')),
        server_time_ms=now_ms)
