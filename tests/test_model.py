import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from mom_basis.model import (BAR, BUDGET, HOLD, INITIAL, LIVE_WARMUP, ROOT, features, forecast,
                             pnl, signal_id, statistics)
from mom_basis.replay import reproduce
from mom_basis.store import Store


@pytest.fixture
def real_onset():
    """Actual Binance signal after sufficient warmup; no fabricated market candles."""
    d = pd.read_csv(ROOT/"data"/"reference180"/"BNBUSDT_15m.csv.gz")
    f = features(d)
    i = next(int(i) for i in np.flatnonzero(f.onset.to_numpy()) if i>=LIVE_WARMUP)
    # Shift the calendar beyond the imported baseline solely for lifecycle unit tests.
    # Market values are real; these shifted timestamps are never exported as performance.
    end=json.loads((ROOT/"data"/"baseline"/"seed.json").read_text(encoding="utf-8"))["metadata"]["end_ms"]
    d.timestamp_ms += end + 2*BAR - int(d.timestamp_ms.iloc[i])
    frame = d.iloc[i-LIVE_WARMUP+1:i+1].reset_index(drop=True)
    assert features(frame).onset.iloc[-1]
    return d,frame,i,int(d.timestamp_ms.iloc[i])+BAR,float(d.open.iloc[i+1])


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path/"test.sqlite3")
    s.seed()
    return s


def test_exact_241_real_trades_and_full_equity():
    r = reproduce()
    assert r["summary"]["n_trades"] == 241
    assert r["candidates"] == 284
    assert r["skipped_same_coin"] == 43
    assert r["checks"]["max_equity_error_usdt"] < 1e-8


def test_seed_statistics_and_no_overwrite(store):
    s = store.metrics()
    assert s["n_trades"] == 241
    assert s["net_profit"] == pytest.approx(.10736903987724178)
    assert s["max_drawdown"] == pytest.approx(-.019480738090079774)
    assert s["gross_winrate"] == pytest.approx(167/241)
    assert s["net_winrate"] == pytest.approx(160/241)
    assert store.seed() is False
    expected = pd.read_csv(ROOT/"data"/"baseline"/"per_coin.csv")
    for r in expected.itertuples():
        own = store.metrics(r.coin)
        assert own["n_trades"] == r.n_trades
        assert own["net_profit"] == pytest.approx(r.net_profit)
        assert own["max_drawdown"] == pytest.approx(r.max_drawdown)


def test_idempotency_restart_expiry_fees_and_stats(store,real_onset):
    d,frame,i,entry,price = real_onset
    initial_cash = store.meta("cash")
    sid = store.accept_batch(entry,{"BNB":frame},{"BNB":price},entry+5000)[0]
    assert len(store.accept_batch(entry,{"BNB":frame},{"BNB":price},entry+6000)) == 0
    assert store.meta("cash") == initial_cash-BUDGET
    restarted = Store(store.path)
    assert len(restarted.pending()) == 1
    t = restarted.pending()[0]
    assert t["forecast"]["latest_training_exit_ms"] <= entry
    assert restarted.view(t,entry+1)["status_label"] == "Đang mở"
    assert restarted.view(t,entry+HOLD*BAR)["status_label"] == "Đã kết thúc"
    assert restarted.view(t,entry+HOLD*BAR)["settlement"] == "PENDING_MARKET_DATA"
    assert restarted.metrics()["n_trades"] == 241
    path = [dict(time_ms=int(r.timestamp_ms),price=float(r.open)) for r in d.iloc[i+1:i+HOLD+2].itertuples()]
    with pytest.raises(ValueError):
        restarted.settle(sid,path[-1]["price"],path,entry+HOLD*BAR-1)
    expected = pnl(price,path[-1]["price"])
    assert restarted.settle(sid,path[-1]["price"],path,entry+HOLD*BAR)
    assert not restarted.settle(sid,path[-1]["price"],path,entry+HOLD*BAR+1)
    assert restarted.meta("cash") == pytest.approx(initial_cash+expected["net_pnl"])
    assert restarted.metrics()["n_trades"] == 242
    assert restarted.metrics()["net_pnl"] == pytest.approx(store.metrics()["net_pnl"])
    assert expected["total_cost"] == pytest.approx(BUDGET/1.0005*.001)
    assert [e["kind"] for e in restarted.events(0)].count("stats.updated") == 1


def test_stale_missing_and_occupied_signals(store,real_onset):
    d,frame,i,entry,price = real_onset
    broken = frame.drop(index=200).reset_index(drop=True)
    assert not store.accept_batch(entry,{"BNB":broken},{"BNB":price},entry+5000)
    nan = frame.copy();nan.loc[200,"basis"] = np.nan
    assert not store.accept_batch(entry,{"BNB":nan},{"BNB":price},entry+5000)
    assert not store.accept_batch(entry,{"BNB":frame},{},entry+5000)
    assert store.accept_batch(entry,{"BNB":frame},{"BNB":price},entry+5000)
    # Shift only timestamps to exercise admission controls with the same real factor observations.
    shifted = frame.copy();shifted.timestamp_ms += BAR
    assert not store.accept_batch(entry+BAR,{"BNB":shifted},{"BNB":price},entry+BAR+5000)
    with store.connect() as c:
        assert c.execute("SELECT reason FROM decisions WHERE entry_ms=?",(entry+BAR,)).fetchone()[0] == "SKIP_SAME_COIN"
    later = frame.copy();later.timestamp_ms += 20*BAR
    assert not store.accept_batch(entry+20*BAR,{"BNB":later},{"BNB":price},entry+20*BAR+120001)


def test_shared_cash_priority_and_notification_retention(store,real_onset):
    _,frame,_,entry,price = real_onset
    with store.tx() as c:
        store.put(c,"cash",500)
    # Deliberately reverse the input: published coin priority, not input iteration order, wins.
    assert len(store.accept_batch(entry,{"ETH":frame,"BTC":frame},{"ETH":price,"BTC":price},entry+1000)) == 1
    assert store.pending()[0]["coin"] == "BTC"
    assert store.meta("cash") == 0
    for n in range(7):
        with store.tx() as c:
            store.notify(c, "test-notification-"+str(n),entry+n)
    with store.connect() as c:
        assert c.execute("SELECT COUNT(*) FROM notifications").fetchone()[0] == 5
        assert c.execute("SELECT MIN(entry_ms) FROM notifications").fetchone()[0] == entry+2
    assert len(store.trades()) == 242  # notification pruning never deletes the trade ledger


def test_forecast_cutoff_and_frozen_output():
    # Mathematical unit fixture, not presented as market data or backtest performance.
    paths=[dict(coin="BTC",exit_ms=10,returns=[k*.01 for k in range(17)]),
           dict(coin="BTC",exit_ms=30,returns=[-k*.01 for k in range(17)])]
    fp=forecast(paths,"BTC",20,100)
    assert fp["sample_count"] == 1
    assert fp["latest_training_exit_ms"] == 10
    assert fp["points"][-1]["mean_price"] == pytest.approx(116)
    assert fp["stop_loss"] is None and fp["risk_reward"] is None
    paths.append(dict(coin="BTC",exit_ms=100,returns=[0]*17))
    assert fp == forecast(paths,"BTC",20,100)


def test_user_reads_are_isolated(store,real_onset):
    _,frame,_,entry,price = real_onset
    sid=store.accept_batch(entry,{"BNB":frame},{"BNB":price},entry+1000)[0]
    assert next(t for t in store.notifications("A",entry) if t["id"]==sid)["unread"]
    store.read("A",sid)
    assert not next(t for t in store.notifications("A",entry) if t["id"]==sid)["unread"]
    assert next(t for t in store.notifications("B",entry) if t["id"]==sid)["unread"]


def test_daily_sharpe_ignores_unobserved_calendar_gap():
    rows=[dict(time_ms=i*BAR,equity=100+i,segment="reference") for i in range(288)]
    first=statistics([],rows)
    gap=[dict(time_ms=(1000+i)*BAR,equity=388+i,segment="forward") for i in range(40)]
    second=statistics([],rows+gap)
    assert first["sharpe_observed_daily_returns"] == second["sharpe_observed_daily_returns"]
