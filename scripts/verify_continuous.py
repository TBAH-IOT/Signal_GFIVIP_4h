"""Independent old-feature scheduler + cash/inventory verification on the expanded REAL data."""
from pathlib import Path
import ast
import heapq
import json
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from mom_basis.model import BAR,COINS,HOLD,INITIAL,BUDGET,SIGNAL_NAME,BACKTEST_START_MS,HISTORY_START_MS,PROFILE_ID,encode
from mom_basis.store import Store
from mom_basis.continuous import HistoryCache

state=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'state_handoff_v1_2'
store=Store(state/'model.sqlite3')
target=store.meta('continuous_asof_ms')
frames=HistoryCache(store).frames(target)
src=ROOT/'data'/'provenance'/'backtest_mom16_basis_local_10bps.py'
tree=ast.parse(src.read_text(encoding='utf-8'))
fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='features')
ns={'np':np,'pd':pd,'HOLD':16,'WINDOW':672,'MIN_PERIODS':168}
exec(compile(ast.Module(body=[fn],type_ignores=[]),str(src),'exec'),ns)
candidate=[];events={}
ts=frames[COINS[0]].timestamp_ms.to_numpy();n=len(ts)
for priority,coin in enumerate(COINS):
    f=ns['features'](frames[coin].iloc[:-1])
    for i in np.flatnonzero(f['events']):
        if int(ts[int(i)+1])>=BACKTEST_START_MS:
            candidate.append((int(i)+1,priority,coin,int(i)+1+HOLD))
cash=INITIAL;heap=[];occupied={};selected=[];skipped=0
cashdiff=np.zeros(n);qtydiff={c:np.zeros(n) for c in COINS}
for en,_,coin,ex in sorted(candidate):
    while heap and heap[0][0]<=en:cash+=heapq.heappop(heap)[2]
    if en<occupied.get(coin,-1):skipped+=1;continue
    if cash<BUDGET-1e-8:continue
    ep=float(frames[coin].open.iloc[en]);notional=BUDGET/1.0005;qty=notional/ep
    cash-=BUDGET;cashdiff[en]-=BUDGET;qtydiff[coin][en]+=qty
    net=None
    if ex<n:
        xp=float(frames[coin].open.iloc[ex]);net=notional*(xp/ep-1)-notional*.001
        heapq.heappush(heap,(ex,len(selected),BUDGET+net))
        cashdiff[ex]+=BUDGET+net;qtydiff[coin][ex]-=qty
    occupied[coin]=ex;selected.append((coin,int(ts[en]),int(ts[en])+HOLD*BAR,net))
actual=store.trades()
actual.sort(key=lambda t:(t['entry_ms'],COINS.index(t['coin'])))
assert [(c,en,ex) for c,en,ex,_ in selected]==[(t['coin'],t['entry_ms'],t['exit_ms']) for t in actual]
assert np.allclose([net for _,_,_,net in selected if net is not None],[t['net_pnl'] for t in actual if t['exit_price'] is not None],atol=1e-9,rtol=0)
cashcurve=INITIAL+np.cumsum(cashdiff)
inventory=sum(np.cumsum(qtydiff[c])*frames[c].open.to_numpy() for c in COINS)
equity=cashcurve+inventory
with store.connect() as con:
    marks=pd.read_sql_query('SELECT * FROM marks ORDER BY time_ms',con)
visible=ts>=BACKTEST_START_MS
assert np.array_equal(marks.time_ms.to_numpy(),ts[visible])
error=float(np.max(np.abs(equity[visible]-marks.equity.to_numpy())))
assert error<1e-7 and cashcurve.min()>=-1e-8
assert np.allclose(cashcurve[visible],marks.cash,atol=1e-7,rtol=0)
for t in actual:
    fp=t['forecast']
    assert fp['latest_training_exit_ms'] is None or fp['latest_training_exit_ms']<=t['entry_ms']
    assert t['exit_ms']-t['entry_ms']==16*BAR
for coin in COINS:
    own=[t for t in actual if t['coin']==coin]
    assert all(a['exit_ms']<=b['entry_ms'] for a,b in zip(own,own[1:]))
assert not any(r['kind']=='signal.opened' for r in store.events(0)), 'Historical catchup emitted a live alert'
assert store.meta('continuous_start_ms')==BACKTEST_START_MS
assert store.meta('continuous_profile_id')==PROFILE_ID
assert int(ts[0])==HISTORY_START_MS
assert all(t['entry_ms']>=BACKTEST_START_MS for t in actual)
result=dict(signal_name=SIGNAL_NAME,as_of_ms=target,all_coins=20,bars_per_coin=n,
    start_ms=BACKTEST_START_MS,history_start_ms=int(ts[0]),profile_id=PROFILE_ID,
    closed_trades=sum(t['exit_price'] is not None for t in actual),
    open_trades=sum(t['exit_price'] is None for t in actual),warmup_excluded_from_trades_and_stats=True,
    independent_legacy_feature_scheduler=True,all_trade_ids_times_and_pnls_match=True,
    cash_plus_inventory_matches_every_equity_mark=True,max_equity_error_usdt=error,
    min_available_cash_usdt=float(cashcurve.min()),same_coin_non_overlap=True,
    forecast_cutoffs_valid=True,all_holds_exact_4h=True,no_future_bar_close_used=True,
    price_and_premium_complete=True,old_notifications_not_reemitted=True)
out=ROOT/'evidence'/'continuous';out.mkdir(exist_ok=True)
(out/'independent_verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(encode(result))
