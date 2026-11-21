import asyncio
import json
import time
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from mom_basis.api import create_app
from mom_basis.continuous import HistoryCache,calculate_book,apply_book
from mom_basis.feed import Worker
from mom_basis.model import BAR,COINS,ROOT
from mom_basis.store import Store
from mom_basis.trade_views import trade_detail,summary


@pytest.fixture(scope='module')
def client(tmp_path_factory):
    app=create_app(tmp_path_factory.mktemp('archive'),live=False)
    with TestClient(app) as c:yield c,app.state.store


def test_all_coin_history_is_accessible_beyond_latest_five(client):
    c,s=client
    latest=c.get('/api/notifications').json()['items'];ids={r['id'] for r in latest}
    coin=latest[0]['coin'];own=s.trades(coin)
    assert len(own)>5
    first=c.get('/api/trades',params={'coin':coin,'limit':2}).json()
    second=c.get('/api/trades',params={'coin':coin,'limit':2,'offset':2}).json()
    assert first['total']==len(own)
    assert not {t['id'] for t in first['items']} & {t['id'] for t in second['items']}
    old=own[0];assert old['id'] not in ids
    detail=c.get('/api/trades/'+old['id']).json()
    assert detail['trade']['id']==old['id'] and detail['navigation']['position']==1
    assert detail['navigation']['previous_id'] is None
    assert detail['navigation']['coin']==coin
    assert c.get('/api/trades/missing').status_code==404
    for params in ({'coin':'FAKE'},{'coin':coin,'limit':101},{'coin':coin,'offset':-1}):
        assert c.get('/api/trades',params=params).status_code==422
    assert len(c.get('/api/notifications').json()['items'])==5


def test_navigation_walks_every_trade_of_the_same_coin(client):
    c,s=client;coin='BTC';expected=s.trades(coin)
    current=c.get('/api/trades?coin=BTC&limit=1').json()['items'][0]['id']
    seen=[]
    while current:
        r=c.get('/api/trades/'+current).json()
        assert r['trade']['coin']==coin
        assert r['navigation']['position']==len(expected)-len(seen)
        assert current not in seen
        seen.append(current);current=r['navigation']['previous_id']
    assert seen==[t['id'] for t in reversed(expected)]


def test_real_ohlc_and_markers_match_reference_fills_and_net_labels(client):
    c,s=client
    trades=s.trades()
    win=next(t for t in trades if t['net_pnl']>0)
    fee_loss=next(t for t in trades if t['gross_pnl']>0 and t['net_pnl']<0)
    for t,tag in ((win,'TP'),(fee_loss,'SL')):
        r=c.get('/api/trades/'+t['id']).json();v=r['trade'];chart=r['chart']
        assert v['result_tag']==tag and v['exit_reason']=='TIME_4H'
        assert v['return_on_budget']==pytest.approx(t['net_pnl']/500)
        assert chart['exit_marker']['kind']=='REALIZED'
        assert chart['exit_marker']['time_ms']-chart['entry_marker']['time_ms']==16*BAR
        en=next(b for b in chart['candles'] if b['time_ms']==t['entry_ms'])
        ex=next(b for b in chart['candles'] if b['time_ms']==t['exit_ms'])
        assert en['open']==t['entry_price'] and ex['open']==t['exit_price']
        assert chart['missing_closed_bars']==0
        assert all(b['low']<=min(b['open'],b['close'])<=max(b['open'],b['close'])<=b['high'] for b in chart['candles'])
    assert summary(dict(win,net_pnl=0))['result_tag']=='FLAT'


def test_open_trade_exposes_only_scheduled_exit_and_real_visible_candles(tmp_path):
    frames={c:pd.read_csv(ROOT/'data'/'continuous'/(c+'USDT_15m.csv.gz'),float_precision='round_trip') for c in COINS}
    full=calculate_book(frames);first=full.trades[0];cut=first['entry_index']
    short={c:d.iloc[:cut+1].copy() for c,d in frames.items()}
    for d in short.values():d.loc[d.index[-1],['high','low','close','basis']]=np.nan
    prefix=calculate_book(short);now=prefix.asof_ms+5000
    s=Store(tmp_path/'open.sqlite3');s.seed();cache=HistoryCache(s)
    for coin,d in short.items():cache.ingest(coin,d,now)
    apply_book(s,prefix,now)
    t=prefix.trades[0];r=trade_detail(s,t['id'],now)
    assert r['trade']['exit_price'] is None and r['trade']['return_on_budget'] is None
    assert r['trade']['result_tag'] is None
    assert r['chart']['exit_marker']['kind']=='SCHEDULED'
    assert r['chart']['exit_marker']['price'] is None
    assert r['chart']['end_ms']==t['entry_ms']+16*BAR
    assert all(b['time_ms']<prefix.asof_ms for b in r['chart']['candles'])
    # Actual in-progress OHLC may be updated; already closed bars remain immutable.
    coin=t['coin'];price=t['entry_price']
    class Source:
        async def get(self,endpoint,**params):
            return [[prefix.asof_ms,price,price*1.001,price*.999,price*1.0002]]
    worker=Worker(s,source=Source())
    asyncio.run(worker.refresh_open_candles(now))
    updated=trade_detail(s,t['id'],now)
    current=next(b for b in updated['chart']['candles'] if b['time_ms']==prefix.asof_ms)
    assert not current['closed'] and current['close']==price*1.0002
    assert s.trades()[0]['forecast']==t['forecast']
    assert s.trades()[0]['exit_price'] is None
    with s.tx() as con:con.execute('UPDATE history_bars SET is_closed=1 WHERE coin=? AND timestamp_ms=?',(coin,prefix.asof_ms))
    before=current['close'];asyncio.run(worker.refresh_open_candles(now))
    with s.connect() as con:
        assert con.execute('SELECT close FROM history_bars WHERE coin=? AND timestamp_ms=?',(coin,prefix.asof_ms)).fetchone()[0]==before
