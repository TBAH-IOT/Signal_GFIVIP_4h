import asyncio
import json
import numpy as np
import pandas as pd
import pytest
from mom_basis.continuous import HistoryCache,apply_book,calculate_book,synchronize
from mom_basis.model import BAR,COINS,ROOT,SIGNAL_NAME,encode
from mom_basis.store import Store


@pytest.fixture(scope="module")
def frames():
    return {c:pd.read_csv(ROOT/'data'/'reference180'/(c+'USDT_15m.csv.gz')) for c in COINS}


@pytest.fixture(scope="module")
def original_book(frames):
    return calculate_book(frames)


def blank_store(path):
    s=Store(path);HistoryCache(s)
    return s


def test_continuous_engine_exact_original_241_and_all_marks(original_book):
    golden=pd.read_csv(ROOT/'data'/'baseline'/'trades.csv')
    b=original_book
    done=[t for t in b.trades if t['exit_price'] is not None]
    assert [(t['coin'],t['entry_ms']) for t in done]==list(zip(golden.coin,golden.entry_ms))
    for k in ('entry_price','exit_price','gross_pnl','total_cost','net_pnl','quantity'):
        assert np.allclose([t[k] for t in done],golden[k],atol=1e-9,rtol=0)
    eq=pd.read_csv(ROOT/'data'/'baseline'/'equity_15m.csv')
    assert np.allclose(b.marks.equity,eq.equity,atol=1e-8,rtol=0)
    assert np.allclose(b.marks.cash,eq.cash,atol=1e-8,rtol=0)
    assert len(b.decisions)==284


def test_open_seam_restart_and_same_time_exit_entry_causal(frames,original_book,tmp_path):
    first=original_book.trades[0]
    cut=first['entry_index']+8
    short={c:d.iloc[:cut+1].copy() for c,d in frames.items()}
    prefix=calculate_book(short)
    assert prefix.metrics['TOTAL']['open_trades']>0
    s=blank_store(tmp_path/'seam.sqlite3')
    apply_book(s,prefix,prefix.asof_ms+1000)
    assert len(s.pending())==prefix.metrics['TOTAL']['open_trades']
    prefix_ids=[t['id'] for t in prefix.trades]
    full_prefix=[t for t in original_book.trades if t['entry_ms']<=prefix.asof_ms]
    assert prefix_ids==[t['id'] for t in full_prefix]
    for a,b in zip(prefix.trades,full_prefix):
        assert a['forecast']==b['forecast']
    resumed=Store(s.path)
    apply_book(resumed,original_book,original_book.asof_ms+1000)
    assert resumed.metrics()['n_trades']==241
    assert resumed.meta('cash')==pytest.approx(11073.690398772418)
    assert not resumed.pending()
    with resumed.connect() as c:
        assert c.execute('SELECT COUNT(*) FROM marks').fetchone()[0]==len(frames[COINS[0]])
    count=resumed.latest_event_id()
    apply_book(resumed,original_book,original_book.asof_ms+2000)
    assert resumed.latest_event_id()==count
    assert len(resumed.trades())==241


def test_historical_catchup_silent_but_fresh_signals_notify(frames,original_book,tmp_path):
    index=original_book.trades[0]['entry_index']
    b=calculate_book({c:d.iloc[:index+1].copy() for c,d in frames.items()})
    s=blank_store(tmp_path/'historical.sqlite3')
    apply_book(s,b,b.asof_ms+1000,live_notices=False)
    assert not any(e['kind']=='signal.opened' for e in s.events(0))
    assert all(not t['unread'] for t in s.notifications('user',b.asof_ms))
    live=blank_store(tmp_path/'live.sqlite3')
    # Fresh book object: apply_book deliberately stamps notification metadata into its rows.
    b2=calculate_book({c:d.iloc[:index+1].copy() for c,d in frames.items()})
    apply_book(live,b2,b2.asof_ms+1000,live_notices=True)
    assert any(e['kind']=='signal.opened' for e in live.events(0))
    assert all(t['signal_name']==SIGNAL_NAME for t in live.notifications('user',b.asof_ms))
    assert any(t['unread'] for t in live.notifications('user',b.asof_ms))
    count=live.latest_event_id()
    apply_book(live,b2,b2.asof_ms+2000,live_notices=True)
    assert live.latest_event_id()==count


def test_future_or_unclosed_last_candle_cannot_change_entry_or_forecast(frames):
    cut=1300
    short={c:d.iloc[:cut+1].copy() for c,d in frames.items()}
    before=calculate_book(short)
    for d in short.values():
        d.loc[cut,['high','low','close','basis']]=[1e9,.00001,1e9,-100]
    after=calculate_book(short)
    assert encode(before.trades)==encode(after.trades)
    assert np.array_equal(before.marks.equity,after.marks.equity)
    for t in before.trades:
        f=t['forecast']
        assert f['latest_training_exit_ms'] is None or f['latest_training_exit_ms']<=t['entry_ms']


def test_download_paginates_and_resumes_every_gap_without_fake_alerts(frames,tmp_path):
    s=blank_store(tmp_path/'download.sqlite3')
    cache=HistoryCache(s)
    start=int(frames[COINS[0]].timestamp_ms.iloc[0]);target=start+1250*BAR
    for coin,d in frames.items():cache.ingest(coin,d.iloc[:200],start+200*BAR)
    s.set_meta('history_cache_seeded',True)
    class Source:
        calls=[]
        async def server_ms(self):return target+10000
        async def candles(self,coin,start,end,limit):
            self.calls.append((coin,start,end))
            d=frames[coin]
            return d[d.timestamp_ms.between(start,end)].head(limit).copy()
    source=Source()
    asyncio.run(synchronize(s,source))
    assert len(source.calls)==40 # 1051 missing bars/coin, two pages
    assert s.metrics()['data_as_of_ms']==target
    assert all(t['entry_ms']<=target for t in s.trades())
    count=s.latest_event_id()
    source.calls=[]
    asyncio.run(synchronize(s,source))
    assert len(source.calls)==20 # only refresh the unclosed current candle
    assert s.latest_event_id()==count
    assert not any(e['kind']=='signal.opened' for e in s.events(0))
    with s.tx() as c:c.execute('DELETE FROM history_bars WHERE coin=? AND timestamp_ms=?',('BTC',start+777*BAR))
    assert cache.cursor('BTC')==start+777*BAR
    source.calls=[]
    asyncio.run(synchronize(s,source))
    assert any(coin=='BTC' and en==start+777*BAR for coin,en,_ in source.calls)
    assert s.metrics()['data_as_of_ms']==target


def test_missing_real_data_does_not_publish_a_partial_portfolio(frames,tmp_path):
    s=blank_store(tmp_path/'incomplete.sqlite3')
    cache=HistoryCache(s);s.set_meta('history_cache_seeded',True)
    start=int(frames[COINS[0]].timestamp_ms.iloc[0]);target=start+300*BAR
    class Source:
        async def server_ms(self):return target+1000
        async def candles(self,coin,start,end,limit):
            d=frames[coin]
            result=d[d.timestamp_ms.between(start,end)].copy()
            return result.iloc[1:] if coin=='BTC' else result
    with pytest.raises(RuntimeError):asyncio.run(synchronize(s,Source()))
    assert s.meta('continuous_asof_ms') is None
    assert s.latest_event_id()==0


def test_completed_history_persists_and_forecasts_stay_frozen(frames,original_book,tmp_path):
    s=blank_store(tmp_path/'frozen.sqlite3')
    apply_book(s,original_book,original_book.asof_ms+1000)
    sid=s.trades()[-1]['id'];frozen=s.trades()[-1]['forecast']
    # Test that a retry keeps the forecast originally published under this signal ID.
    copy=calculate_book(frames)
    next(t for t in copy.trades if t['id']==sid)['forecast']={'available':False,'points':[]}
    apply_book(s,copy,copy.asof_ms+2000)
    assert next(t for t in s.trades() if t['id']==sid)['forecast']==frozen
