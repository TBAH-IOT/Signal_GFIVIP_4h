r"""Offline MOM16:L + BASIS:L report. Python 3.10+, numpy, pandas only.

Run: python D:\Live_Trade\backtest_mom16_basis_local_10bps.py
Default: overlapping positions, eight independently funded cash sleeves/coin.
Use --no-overlap for the prior one-position-per-coin execution.
All newly computed event studies and portfolios use 10 bps ALL-IN round trip.
Reads real local CSVs, recomputes signals, writes CSV/JSON and terminal tables.
No network imports, exchange account, synthetic data, or order submission.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd

BASE=Path(__file__).resolve().parent
TOP5=["BTC","ETH","SOL","BNB","XRP"]
TOP20=["BTC","ETH","SOL","ZEC","BNB","XRP","NEAR","DOGE","UNI","SUI",
       "ENA","LINK","AVAX","ADA","BCH","FIL","LTC","DOT","ARB","AAVE"]
BAR=900_000;HOLD=16;WINDOW=672;MIN_PERIODS=168;COST=.001;INITIAL=10000.
METHODS=["single","dca_atr"]
NEEDED=["timestamp_ms","open","high","low","close","basis"]

def utc_ms(value):
    t=pd.Timestamp(value)
    t=t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
    ms=int(t.value//1_000_000)
    if ms%BAR:raise ValueError("Date must align to a 15-minute candle OPEN")
    return ms

def stamp(ms):return pd.Timestamp(int(ms),unit="ms",tz="UTC").isoformat()

def features(d):
    m=d.close.pct_change(HOLD,fill_method=None);tails=[];qs=[]
    for s in [m,d.basis]:
        lower=s.rolling(WINDOW,min_periods=MIN_PERIODS).quantile(1-.99)
        upper=s.rolling(WINDOW,min_periods=MIN_PERIODS).quantile(.99)
        tails.append(((s<=lower)&(upper>lower)&s.notna()).fillna(False))
        qs.append(lower)
    active=tails[0]&tails[1]
    onset=(active&~active.shift(1,fill_value=False)).to_numpy(bool)
    h=d.high.to_numpy();l=d.low.to_numpy();c=d.close.to_numpy()
    prev=np.r_[np.nan,c[:-1]]
    tr=np.fmax(h-l,np.fmax(abs(h-prev),abs(l-prev)))
    valid=np.isfinite(h)&np.isfinite(l)&np.isfinite(c)
    atr=np.full(len(d),np.nan);acc=0.;count=0;last=np.nan
    for i in range(len(d)):
        if not valid[i]:acc=0.;count=0;last=np.nan;continue
        if count<14:
            acc+=tr[i];count+=1
            if count==14:last=acc/14;atr[i]=last
        else:last=(13*last+tr[i])/14;atr[i]=last
    return dict(events=onset,atr=atr,mom16=m.to_numpy(),mom_q01=qs[0].to_numpy(),
                basis_q01=qs[1].to_numpy(),active=active.to_numpy(bool))

def event_stats(returns):
    a=np.asarray(returns,dtype=float);a=a[np.isfinite(a)];n=len(a)
    mean=float(a.mean()) if n else np.nan
    sd=float(a.std(ddof=1)) if n>1 else np.nan
    return dict(N=n,P_up=float((a>0).mean()) if n else np.nan,
        P_down=float((a<0).mean()) if n else np.nan,
        P_flat=float((a==0).mean()) if n else np.nan,mean_4h=mean,
        edge_bps=(mean-COST)*10000,t_stat=mean/(sd/np.sqrt(n)) if sd>0 else np.nan,
        cost_bps=10.)

def event_study(d,f,start,end,scenario,coin):
    ts=d.timestamp_ms.to_numpy();cl=d.close.to_numpy();rows=[]
    for i in np.flatnonzero(f["events"]&(ts>=start)&(ts<=end)):
        j=i+HOLD
        if j>=len(d) or ts[j]>end:continue
        if not np.isfinite(cl[[i,j]]).all():continue
        r=cl[j]/cl[i]-1
        rows.append(dict(scenario=scenario,coin=coin,signal_bar_ms=int(ts[i]),
            signal_time=stamp(ts[i]+BAR),label_end_time=stamp(ts[j]+BAR),
            gross_return=r,net_return=r-COST,mom16=f["mom16"][i],
            mom_q01=f["mom_q01"][i],basis=d.basis.iloc[i],basis_q01=f["basis_q01"][i],
            close_t=cl[i],close_t16=cl[j]))
    return rows

def replay(d,f,start,end,scenario,coin,method,overlap_slots=8):
    if not isinstance(overlap_slots,int) or overlap_slots<1:
        raise ValueError("overlap_slots must be a positive integer")
    ts=d.timestamp_ms.to_numpy();op=d.open.to_numpy();lo=d.low.to_numpy();n=len(d)
    change=np.zeros(n);active=np.zeros(n);trades=[];fills=[]
    slot_initial=1./overlap_slots
    slot_cash=np.full(overlap_slots,slot_initial)
    busy_until=np.full(overlap_slots,-1,dtype=np.int64)
    pending=np.zeros(overlap_slots)
    counts=dict(onsets=0,censored=0,occupied=0,missing_price=0,accepted=0,
                overlap_accepted=0,peak_concurrent=0,no_cash=0)
    positions=np.flatnonzero(f["events"])
    # Consecutive onset events must be at least two bars apart. In a 16-bar
    # holding window there can be at most eight simultaneous onset positions.
    assert not len(positions)>1 or (np.diff(positions)>=2).all()
    for i in np.flatnonzero(f["events"]&(ts>=start)&(ts<=end)):
        counts["onsets"]+=1;e=int(i)+1;j=e+HOLD
        if j>=n or ts[j]>end:counts["censored"]+=1;continue
        # Release reserved principal and realized PnL only at the actual exit.
        # No proceeds from a future exit may size an earlier overlapping order.
        matured=(busy_until<=e)&(pending!=0)
        slot_cash[matured]+=pending[matured];pending[matured]=0.
        free=np.flatnonzero(busy_until<=e)
        if not len(free):counts["occupied"]+=1;continue
        atr=f["atr"][i]
        if not (np.isfinite(op[e:j+1]).all() and np.isfinite(lo[e:j]).all() and np.isfinite(atr) and atr>0):
            counts["missing_price"]+=1;continue
        # Rotate sleeves by oldest exit; sizing uses that sleeve's settled cash.
        free=free[np.argsort(busy_until[free],kind="stable")]
        funded=free[slot_cash[free]>0]
        if not len(funded):counts["no_cash"]+=1;continue
        slot=int(funded[0]);cash_before=float(slot_cash[slot])
        budget=min(slot_initial,cash_before)
        already_open=int((busy_until>e).sum())
        counts["overlap_accepted"]+=int(already_open>0)
        counts["peak_concurrent"]=max(counts["peak_concurrent"],already_open+1)
        first=op[e];orders=[(e,e,0.,first,1. if method=="single" else 1/3)]
        if method=="dca_atr":
            for level in [1.,2.]:
                trigger=first-level*atr
                if trigger<=0:continue
                hit=np.flatnonzero(lo[e:j]<=trigger)
                if len(hit):
                    b=e+int(hit[0]);mark=b if op[b]<=trigger else b+1
                    orders.append((b,mark,level,min(op[b],trigger),1/3))
        gp=cost=net=notional=used=0.
        tid=f"{scenario}_{coin}_{method}_{int(ts[i])}"
        for b,k,level,price,weight in orders:
            alloc=budget*weight;amount=alloc/(1+COST/2);qty=amount/price
            gross=amount*(op[j]/price-1);fee=COST*amount;pnl=gross-fee
            active[k:j]+=qty*op[k:j]-alloc;change[j]+=pnl
            gp+=gross;cost+=fee;net+=pnl;notional+=amount;used+=alloc
            fills.append(dict(trade_id=tid,scenario=scenario,coin=coin,method=method,slot_id=slot,
                fill_bar_ms=int(ts[b]),mark_ms=int(ts[k]),exit_ms=int(ts[j]),level_atr=level,
                fill_price=price,quantity=qty,allocated_cash=alloc,notional=amount,
                gross_pnl=gross,total_cost=fee,net_pnl=pnl))
        assert ts[i]+BAR-1<ts[e] and ts[j]-ts[e]==HOLD*BAR
        slot_cash[slot]-=budget
        pending[slot]=budget+net;busy_until[slot]=j;counts["accepted"]+=1
        trades.append(dict(trade_id=tid,scenario=scenario,coin=coin,method=method,
            slot_id=slot,overlap_slots=overlap_slots,concurrent_at_entry=already_open+1,
            signal_ms=int(ts[i]),entry_ms=int(ts[e]),exit_ms=int(ts[j]),
            signal_time=stamp(ts[i]+BAR),entry_time=stamp(ts[e]),exit_time=stamp(ts[j]),
            entry_price=first,exit_price=op[j],atr=float(atr),n_fills=len(orders),
            reserved_cash=budget,used_fraction=used/budget,gross_notional=notional,
            gross_pnl=gp,total_cost=cost,net_pnl=net,gross_return=gp/notional,
            net_return=net/notional,slot_cash_before_entry=cash_before,
            slot_cash_at_exit=cash_before+net))
    eq=1.+np.cumsum(change)+active
    grid=np.arange(start,end+BAR,BAR,dtype=np.int64);global_eq=np.ones(len(grid))
    mask=(ts>=start)&(ts<=end);ix=(ts[mask]-start)//BAR;global_eq[ix]=eq[mask]
    assert (busy_until[busy_until>=0]<=np.searchsorted(ts,end,side="right")-1).all()
    final_cash=float(slot_cash.sum()+pending.sum())
    assert abs(global_eq[-1]-final_cash)<1e-10
    assert abs(global_eq[-1]-1.-sum(x["net_pnl"] for x in trades))<1e-10
    for t in trades:
        assert np.isclose(t["total_cost"],COST*t["gross_notional"])
        assert np.isclose(t["gross_return"]-t["net_return"],COST)
    return trades,fills,global_eq,counts

def performance(trades,equity,initial=1.):
    t=pd.DataFrame(trades) if not isinstance(trades,pd.DataFrame) else trades
    peak=np.maximum.accumulate(np.r_[initial,equity])[1:]
    r=dict(n_trades=len(t),net_profit=float(equity[-1]/initial-1),
           max_drawdown=float((equity/peak-1).min()),final_equity=float(equity[-1]))
    if t.empty:return dict(**r,gross_winrate=np.nan,net_winrate=np.nan,profit_factor=np.nan)
    gains=t.loc[t.net_pnl>0,"net_pnl"].sum();loss=-t.loc[t.net_pnl<0,"net_pnl"].sum()
    return dict(**r,gross_winrate=float((t.gross_pnl>0).mean()),net_winrate=float((t.net_pnl>0).mean()),
                profit_factor=float(gains/loss) if loss else np.nan)

def text_table(rows,columns):
    def fmt(v,key):
        if key in ["method"]:return {"single":"Mua mot lan","dca_atr":"DCA ATR"}.get(v,str(v))
        if isinstance(v,(float,np.floating)):
            if not np.isfinite(v):return "--"
            if key in ["P_up","P_down","gross_winrate","net_winrate"]:return f"{v*100:.2f}%"
            if key in ["mean_4h"]:return f"{v*100:+.3f}%"
            if key in ["net_profit","max_drawdown"]:return f"{v*100:+.2f}%"
            return f"{v:+.2f}" if key=="edge_bps" else f"{v:.2f}"
        return str(v)
    cells=[[fmt(row.get(key,""),key) for key,_ in columns] for row in rows]
    widths=[max(len(label),max((len(r[j]) for r in cells),default=0)) for j,(_,label) in enumerate(columns)]
    line=lambda row:" | ".join(v.ljust(w) for v,w in zip(row,widths))
    return "\n".join([line([label for _,label in columns]),"-+-".join("-"*w for w in widths)]+[line(r) for r in cells])

EVENT_COLS=[("coin","Coin"),("N","N event"),("P_up","P_up"),("P_down","P_down"),
            ("mean_4h","Mean 4h"),("edge_bps","Edge 10bps"),("t_stat","t-stat")]
PERF_COLS=[("coin","Coin"),("n_trades","Lenh"),("gross_winrate","WR gross"),
           ("net_winrate","WR net"),("net_profit","Net_P"),("max_drawdown","Max DD"),("profit_factor","PF net")]

def main():
    for stream in [sys.stdout,sys.stderr]:
        if hasattr(stream,"reconfigure"):stream.reconfigure(encoding="utf-8",errors="replace")
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir",type=Path,default=BASE/"binance_top20_15m_2022_now")
    parser.add_argument("--out-dir",type=Path,default=None)
    parser.add_argument("--overlap-slots",type=int,default=8,
        help="Independently funded sleeves per coin; default 8 covers every onset without leverage")
    parser.add_argument("--no-overlap",action="store_true",help="Prior execution: one position per coin")
    parser.add_argument("--audit-overlap",action="store_true",
        help="Print all 76 original top5 orders, 16 exclusions, cross-coin coincidence and fixed-budget controls")
    args=parser.parse_args()
    if args.audit_overlap:
        if args.data_dir!=BASE/"binance_top20_15m_2022_now" or args.out_dir is not None:
            parser.error("--audit-overlap uses the original local snapshot and a separate audit output folder")
        from audit_mom16_basis_overlap_180d import main as run_audit
        run_audit()
        return
    slots=1 if args.no_overlap else args.overlap_slots
    if slots<1:parser.error("--overlap-slots must be >= 1")
    mode="no_overlap" if slots==1 else f"overlap{slots}"
    out=args.out_dir or BASE/f"mom16_basis_local_10bps_{mode}_results"
    out.mkdir(parents=True,exist_ok=True)
    ready=json.loads((args.data_dir/"READY.json").read_text(encoding="utf-8"));snap=ready["snapshot"]
    end=int(snap["last_closed_open_ms"]);start=utc_ms("2022-01-01T00:00Z")
    short_start=utc_ms("2026-04-25T16:15Z");short_end=utc_ms("2026-10-22T13:00Z")
    periods=[dict(id="top5_original_180d",title="TOP 5 - MAU NGHIEN CUU BAN DAU ~180 NGAY",coins=TOP5,
                  start=short_start,end=short_end,reset_features=True),
        dict(id="top20_4years_2022_2025",title="TOP 20 - 4 NAM TRON 2022-2025",coins=TOP20,
             start=start,end=utc_ms("2025-12-31T23:45Z"),reset_features=False),
        dict(id="top20_2022_now",title="TOP 20 - 2022 DEN SNAPSHOT HIEN TAI",coins=TOP20,
             start=start,end=end,reset_features=False),
        dict(id="top5_2022_now",title="DOI CHIEU CUNG TOP 5 - 2022 DEN SNAPSHOT",coins=TOP5,
             start=start,end=end,reset_features=False),
        dict(id="top5_first180_2022",title="PHU LUC - TOP 5, 180 NGAY DAU TU 01/01/2022",coins=TOP5,
             start=start,end=start+180*86400000-BAR,reset_features=False)]
    if any(p["end"]>end for p in periods):raise ValueError("Local snapshot does not cover a requested period")
    event_rows=[];events=[];coin_perf=[];alltr=[];allfill=[];counts=[];audits=[]
    portfolios={(p["id"],m):np.zeros((p["end"]-p["start"])//BAR+1) for p in periods for m in METHODS}
    for coin in TOP20:
        item=next(x for x in ready["coverage"] if x["coin"]==coin)
        path=args.data_dir/"datasets"/f"{coin}USDT_15m.csv"
        sha=hashlib.sha256(path.read_bytes()).hexdigest()
        if sha!=item["dataset_sha256"]:raise ValueError(f"Dataset SHA256 mismatch: {coin}")
        d=pd.read_csv(path,usecols=NEEDED)
        if not (d.timestamp_ms.diff().dropna()==BAR).all():raise ValueError("Timestamp grid must preserve gaps as NaN")
        f=features(d);cut=len(d)//2;pf=features(d.iloc[:cut+1])
        assert np.array_equal(f["events"][:cut+1],pf["events"])
        changed=d.copy();changed.loc[cut+1:,["open","high","low","close"]]*=2
        changed.loc[cut+1:,"basis"]+=.1;cf=features(changed)
        assert np.array_equal(f["events"][:cut+1],cf["events"][:cut+1])
        assert np.allclose(f["atr"][:cut+1],cf["atr"][:cut+1],equal_nan=True)
        audits.append(dict(coin=coin,dataset_sha256=sha,prefix_invariance=True,future_perturbation=True))
        for p in periods:
            if coin not in p["coins"]:continue
            if p["reset_features"]:
                frame=d[d.timestamp_ms.between(p["start"],p["end"])].reset_index(drop=True);feat=features(frame)
            else:frame=d;feat=f
            ev=event_study(frame,feat,p["start"],p["end"],p["id"],coin)
            events.extend(ev);event_rows.append(dict(scenario=p["id"],coin=coin,**event_stats([r["gross_return"] for r in ev])))
            for method in METHODS:
                tr,ff,eq,cnt=replay(frame,feat,p["start"],p["end"],p["id"],coin,method,slots)
                portfolios[(p["id"],method)]+=eq*INITIAL/len(p["coins"])
                coin_perf.append(dict(scenario=p["id"],coin=coin,method=method,**performance(tr,eq)))
                counts.append(dict(scenario=p["id"],coin=coin,method=method,**cnt));alltr.extend(tr);allfill.extend(ff)
        print(f"Recomputed and verified {coin}",flush=True)
    t=pd.DataFrame(alltr);summaries=[];pooled=[];yearly=[];transcript=[]
    evdf=pd.DataFrame(events);cp=pd.DataFrame(coin_perf)
    for p in periods:
        sid=p["id"];g=evdf[evdf.scenario==sid];er=dict(scenario=sid,coin="TOTAL",**event_stats(g.gross_return))
        pooled.append(er)
        transcript.extend(["",p["title"],f"Bar opens UTC: {stamp(p['start'])} -> {stamp(p['end'])}",
          "Coins: "+", ".join(p["coins"]),"EVENT STUDY close[t+16]/close[t]-1; overlaps allowed; cost=10bps",
          text_table([dict(er,coin="MOM16:L+BASIS:L")],[("coin","Logic")]+EVENT_COLS[1:]),
          "TUNG COIN:",text_table([x for x in event_rows if x["scenario"]==sid],EVENT_COLS)])
        eqout={"mark_time":pd.to_datetime(np.arange(p["start"],p["end"]+BAR,BAR),unit="ms",utc=True)}
        for method in METHODS:
            subset=t[(t.scenario==sid)&(t.method==method)];eq=portfolios[(sid,method)]
            r=dict(scenario=sid,coin="TOTAL",method=method,**performance(subset,eq,INITIAL));summaries.append(r)
            assert np.isclose(eq[-1],INITIAL+subset.net_pnl.sum()*INITIAL/len(p["coins"]))
            rows=cp[(cp.scenario==sid)&(cp.method==method)].to_dict("records")
            transcript.extend([f"PORTFOLIO {method} - next open, hold 4h, {mode}; {slots} funded sleeves/coin",text_table([r],PERF_COLS),
                               "TUNG COIN:",text_table(rows,PERF_COLS)])
            eqout[method]=eq;dt=pd.DatetimeIndex(eqout["mark_time"])
            exits=pd.to_datetime(subset.exit_ms,unit="ms",utc=True)
            for yr in sorted(set(dt.year)):
                ix=np.flatnonzero(dt.year==yr);prev=INITIAL if ix[0]==0 else eq[ix[0]-1]
                yearly.append(dict(scenario=sid,method=method,year=int(yr),**performance(subset[exits.dt.year==yr],eq[ix],prev)))
        pd.DataFrame(eqout).to_csv(out/f"equity_{sid}.csv.gz",index=False,compression="gzip")
    for sid in ["top20_4years_2022_2025","top20_2022_now"]:
        yr=[r for r in yearly if r["scenario"]==sid]
        transcript.extend(["", "TUNG NAM - "+sid, text_table(yr,
            [("year","Nam"),("method","Cach vao")]+PERF_COLS[1:])])
    for name,rows in [("event_summary",pooled),("event_per_coin",event_rows),("summary",summaries),
                      ("per_coin",coin_perf),("yearly",yearly),("event_counts",counts),("causality_audit",audits)]:
        pd.DataFrame(rows).to_csv(out/f"{name}.csv",index=False)
    evdf.to_csv(out/"events.csv.gz",index=False,compression="gzip")
    t.to_csv(out/"trades_normalized.csv.gz",index=False,compression="gzip")
    pd.DataFrame(allfill).to_csv(out/"fills_normalized.csv.gz",index=False,compression="gzip")
    meta=dict(cost_bps=10.,cost_decimal=COST,initial_usd=INITIAL,top5=TOP5,top20=TOP20,periods=periods,
       snapshot=snap,window_bars=WINDOW,min_periods=MIN_PERIODS,horizon_bars=HOLD,
       event_label="close-to-close; overlapping events allowed",execution=f"next-open, 4h, {mode}",
       overlap_enabled=slots>1,overlap_slots=slots,
       sizing="Each coin splits starting cash into fixed independent sleeves. Reserve entire budget until exit; no leverage. Only settled proceeds can fund the next order in that sleeve.",
       short_initialization="Original short sample resets quantile at first row; extended samples use real Dec2021 warmup",
       ledger_unit="Initial coin cash=1; multiply by 10000/Ncoins for monetary PnL",source_audit=audits)
    (out/"metadata.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8")
    text="\n".join(["MOM16:L + BASIS:L - LOCAL REAL DATA - ALL OUTPUTS COST 10BPS",
        "P_up/P_down and t-stat are GROSS. Edge bps = Mean gross * 10000 - 10.",
        f"Portfolio mode: {mode}. Each coin has {slots} cash sleeves; each order reserves at most 1/{slots} of initial coin cash.",
        "Eight sleeves suffice: onset signals are at least 2 bars apart, holding time is 16 bars.",
        "Event study is unchanged. Portfolio allows overlap up to funded sleeves; no borrowed capital.",
        "Portfolio costs include ALL fees and slippage; no extra funding/fee is added."]+transcript)
    (out/"terminal_results.txt").write_text(text+"\n",encoding="utf-8")
    print(text,flush=True);print("\nSaved:",out,flush=True)

if __name__=="__main__":main()
