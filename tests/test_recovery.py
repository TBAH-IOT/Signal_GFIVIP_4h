import numpy as np
import pandas as pd
from mom_basis.model import BAR, BUDGET, HOLD, LIVE_WARMUP, ROOT, features, pnl
from mom_basis.store import Store


def test_rebuild_full_real_mtm_after_downtime(tmp_path):
    s=Store(tmp_path/'recovery.sqlite3');s.seed()
    d=pd.read_csv(ROOT/'data'/'reference180'/'BNBUSDT_15m.csv.gz')
    i=next(int(i) for i in np.flatnonzero(features(d).onset) if i>=LIVE_WARMUP)
    # Unit lifecycle only: actual Binance prices, dates shifted beyond the frozen baseline.
    d.timestamp_ms += s.meta('baseline')['end_ms']+2*BAR-int(d.timestamp_ms.iloc[i])
    frame=d.iloc[i-LIVE_WARMUP+1:i+1].reset_index(drop=True)
    entry=int(d.timestamp_ms.iloc[i])+BAR;price=float(d.open.iloc[i+1]);cash=s.meta('cash')
    sid=s.accept_batch(entry,{'BNB':frame},{'BNB':price},entry+1000)[0]
    assert s.meta('forward_first_boundary_ms')==entry  # survives crash before the first mark
    assert s.reconcile_marks(entry)
    assert not s.reconcile_marks(entry+8*BAR)  # missing real opens must stay visibly missing
    path=[dict(time_ms=int(r.timestamp_ms),price=float(r.open)) for r in d.iloc[i+1:i+HOLD+2].itertuples()]
    s.settle(sid,path[-1]['price'],path,entry+HOLD*BAR)
    resumed=Store(s.path)
    assert resumed.reconcile_marks(entry+HOLD*BAR)
    with resumed.connect() as c:
        marks=[dict(r) for r in c.execute("SELECT * FROM marks WHERE segment='forward' ORDER BY time_ms")]
    assert len(marks)==17
    n=BUDGET/1.0005
    expected=[cash+n*p['price']/price-BUDGET for p in path[:-1]]+[cash+pnl(price,path[-1]['price'])['net_pnl']]
    assert np.allclose([r['equity'] for r in marks],expected,atol=1e-9,rtol=0)
    assert resumed.meta('marks_quality')['missing_forward_marks']==0
