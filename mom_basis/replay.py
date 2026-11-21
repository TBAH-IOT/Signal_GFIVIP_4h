"""Portable real-data reproduction of the exact 241-trade reference portfolio."""
from __future__ import annotations
import hashlib
import heapq
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .model import BAR, BUDGET, COINS, HOLD, INITIAL, ROOT, clean, features, pnl, statistics


def reproduce(out=None):
    ref = ROOT/"data"/"reference180"
    baseline = ROOT/"data"/"baseline"
    manifest = json.loads((ref/"manifest.json").read_text(encoding="utf-8"))
    frames, candidates = {}, []
    checks = dict(source_checksums=True, causal_prefix=True, no_coin_overlap=True,
                  no_borrowing=True, exact_4h=True, cost_10bps=True)
    for priority, coin in enumerate(COINS):
        path = ref/(coin+"USDT_15m.csv.gz")
        item = next(r for r in manifest["datasets"] if r["coin"] == coin)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["export_sha256"]
        d = pd.read_csv(path)
        assert len(d) == item["rows"]
        ts = d.timestamp_ms.to_numpy()
        assert np.array_equal(ts, np.arange(manifest["start_ms"], manifest["end_ms"]+BAR, BAR))
        frames[coin] = d
        f = features(d)
        prefix = features(d.iloc[:len(d)//2])
        pd.testing.assert_frame_equal(prefix, f.iloc[:len(prefix)])
        for i in np.flatnonzero(f.onset.to_numpy()):
            en, ex = i+1, i+1+HOLD
            if ex >= len(d):
                continue
            candidates.append(dict(coin=coin, priority=priority, entry_index=int(en), exit_index=int(ex),
                signal_ms=int(ts[i]), entry_ms=int(ts[en]), exit_ms=int(ts[ex]),
                entry_price=float(d.open.iloc[en]), exit_price=float(d.open.iloc[ex]),
                mom16=float(f.mom16.iloc[i]), mom_q01=float(f.mom_q01.iloc[i]),
                basis=float(f.basis.iloc[i]), basis_q01=float(f.basis_q01.iloc[i])))
    n = len(next(iter(frames.values())))
    cash, pending, occupied, trades, decisions = INITIAL, [], {}, [], []
    realized, floating = np.zeros(n), np.zeros(n)
    cashdelta = np.zeros(n)
    for row in sorted(candidates, key=lambda r:(r["entry_ms"], r["priority"])):
        while pending and pending[0][0] <= row["entry_ms"]:
            cash += heapq.heappop(pending)[2]
        coin = row["coin"]
        if row["entry_ms"] < occupied.get(coin, -1):
            decisions.append(dict(row, status="SKIP_SAME_COIN"))
            continue
        if cash < BUDGET-1e-8:
            decisions.append(dict(row, status="SKIP_INSUFFICIENT_CASH"))
            continue
        t = dict(row, **pnl(row["entry_price"], row["exit_price"]))
        trades.append(t)
        decisions.append(dict(row, status="EXECUTED"))
        occupied[coin] = row["exit_ms"]
        cash -= BUDGET
        heapq.heappush(pending, (row["exit_ms"], len(trades), BUDGET+t["net_pnl"]))
        en, ex = row["entry_index"], row["exit_index"]
        floating[en:ex] += t["quantity"]*frames[coin].open.to_numpy()[en:ex]-BUDGET
        realized[ex] += t["net_pnl"]
        cashdelta[en] -= BUDGET
        cashdelta[ex] += BUDGET+t["net_pnl"]
        assert row["exit_ms"]-row["entry_ms"] == HOLD*BAR
    equity = INITIAL+np.cumsum(realized)+floating
    cash_curve = INITIAL+np.cumsum(cashdelta)
    assert cash_curve.min() >= -1e-8
    golden = pd.read_csv(baseline/"trades.csv")
    t = pd.DataFrame(trades)
    assert list(zip(t.coin,t.entry_ms)) == list(zip(golden.coin,golden.entry_ms))
    for key in ("entry_price", "exit_price", "mom16", "mom_q01", "basis", "basis_q01", "gross_pnl", "total_cost", "net_pnl", "quantity"):
        assert np.allclose(t[key], golden[key], rtol=1e-11, atol=1e-10), key
    gd = pd.read_csv(baseline/"signal_decisions.csv")
    assert list(zip(gd.coin,gd.entry_ms,gd.status)) == [(r["coin"],r["entry_ms"],r["status"]) for r in decisions]
    ge = pd.read_csv(baseline/"equity_15m.csv")
    assert np.allclose(equity, ge.equity, atol=1e-8, rtol=0)
    assert np.allclose(cash_curve, ge.cash, atol=1e-8, rtol=0)
    for _, group in t.groupby("coin"):
        assert (group.entry_ms.to_numpy()[1:] >= group.exit_ms.to_numpy()[:-1]).all()
    marks = [dict(time_ms=int(ts),equity=float(eq),segment="reference") for ts,eq in zip(next(iter(frames.values())).timestamp_ms,equity)]
    result = statistics(trades, marks)
    expected = pd.read_csv(baseline/"summary.csv").iloc[0]
    for key in ("n_trades", "net_profit", "max_drawdown", "gross_winrate", "net_winrate", "net_pnl", "gross_pnl", "total_cost", "profit_factor"):
        assert np.isclose(result[key],expected[key],atol=1e-9,rtol=0), key
    checks.update(all_241_trade_rows_match=True, all_284_decisions_match=True,
        all_17268_equity_marks_match=True, all_17268_cash_marks_match=True,
        max_equity_error_usdt=float(np.max(np.abs(equity-ge.equity.to_numpy()))))
    result = clean(dict(summary=result, checks=checks, candidates=len(candidates),
                        skipped_same_coin=sum(r["status"]=="SKIP_SAME_COIN" for r in decisions)))
    if out:
        out = Path(out);out.mkdir(parents=True,exist_ok=True)
        (out/"reference_verification.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
        t.to_csv(out/"reproduced_trades.csv",index=False)
    return result
