import json
import sqlite3
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from mom_basis.continuous import HistoryCache,apply_book,calculate_book,initialize_snapshot
from mom_basis.model import BACKTEST_START_MS,HISTORY_START_MS,LIVE_WARMUP,BAR,COINS,ROOT,PROFILE_ID
from mom_basis.store import Store
from mom_basis.api import create_app


@pytest.fixture(scope='module')
def frames():
    return {c:pd.read_csv(ROOT/'data'/'continuous'/(c+'USDT_15m.csv.gz'),float_precision='round_trip') for c in COINS}


@pytest.fixture(scope='module')
def book(frames):
    return calculate_book(frames)


def test_actual_may1_research_outcomes_and_warmup_are_separated(book,frames):
    assert book.profile_id==PROFILE_ID
    assert book.start_ms==BACKTEST_START_MS
    assert int(frames['BTC'].timestamp_ms.iloc[0])==HISTORY_START_MS
    assert (BACKTEST_START_MS-HISTORY_START_MS)//BAR==LIVE_WARMUP
    assert book.marks.time_ms.iloc[0]==BACKTEST_START_MS
    assert book.marks.equity.iloc[0]==10000
    assert book.marks.cash.min()>=0
    assert all(t['entry_ms']>=BACKTEST_START_MS for t in book.trades)
    assert all(d['entry_ms']>=BACKTEST_START_MS for d in book.decisions)
    assert len(book.marks)==(book.asof_ms-BACKTEST_START_MS)//BAR+1
    s=book.metrics['TOTAL']
    assert s['n_trades']==301 and s['gross_wins']==195
    assert s['gross_winrate']==pytest.approx(195/301)
    assert s['net_pnl']==pytest.approx(886.510541400755,abs=1e-8)
    assert s['max_drawdown']==pytest.approx(-.045324752213224406,abs=1e-10)
    assert sum(book.metrics[c]['net_pnl'] for c in COINS)==pytest.approx(s['net_pnl'])
    for t in book.trades:
        assert t['exit_ms']-t['entry_ms']==16*BAR
        cutoff=t['forecast']['latest_training_exit_ms']
        assert cutoff is None or BACKTEST_START_MS<=cutoff<=t['entry_ms']
    assert book.trades[0]['forecast']['sample_count']==0


def test_default_offline_api_is_may1_not_the_old_reference(tmp_path):
    with TestClient(create_app(tmp_path,live=False)) as client:
        stats=client.get('/api/stats').json();model=client.get('/api/model').json()
        assert stats['data_start_ms']==BACKTEST_START_MS
        assert stats['profile_id']==PROFILE_ID
        assert model['backtest_start_ms']==BACKTEST_START_MS
        assert model['history_start_ms']==HISTORY_START_MS
        assert stats['n_trades']==301
        assert stats['equity_curve'][0]['time_ms']==BACKTEST_START_MS
        assert stats['equity_curve'][0]['equity']==10000
        assert len(client.get('/api/notifications').json()['items'])==5


def test_upgrade_archives_old_profile_and_rebuilds_all_stats(tmp_path,book):
    s=Store(tmp_path/'model.sqlite3');s.seed();HistoryCache(s)
    legacy={c:pd.read_csv(ROOT/'data'/'reference180'/(c+'USDT_15m.csv.gz')) for c in COINS}
    old=calculate_book(legacy,start_ms=int(legacy['BTC'].timestamp_ms.iloc[0]))
    apply_book(s,old,old.asof_ms+1000)
    # Simulate the old deployment's cache marker; migration must import warmup too.
    s.set_meta('history_cache_seeded',{'source':'continuous','asof_ms':old.asof_ms})
    initialize_snapshot(s)
    assert s.meta('continuous_profile_id')==PROFILE_ID
    assert s.meta('continuous_start_ms')==BACKTEST_START_MS
    assert s.metrics()['n_trades']==301
    assert s.metrics()['net_pnl']==pytest.approx(book.metrics['TOTAL']['net_pnl'])
    assert all(t['entry_ms']>=BACKTEST_START_MS for t in s.trades())
    assert s.trades()[0]['forecast']['sample_count']==0
    assert not any(e['kind']=='signal.opened' for e in s.events(0))
    backups=list(tmp_path.glob('before_profile_*.sqlite3'))
    assert len(backups)==1
    with sqlite3.connect(backups[0]) as c:
        assert c.execute('SELECT COUNT(*) FROM trades').fetchone()[0]==241
        value=c.execute("SELECT value FROM meta WHERE key='continuous_start_ms'").fetchone()[0]
        assert json.loads(value)==old.start_ms
    count=s.latest_event_id()
    initialize_snapshot(Store(s.path))
    apply_book(s,book,book.asof_ms+2000)
    assert s.latest_event_id()==count
    assert len(s.trades())==301
