r"""MOM16:L+BASIS:L, original ~180-day sample, top20, 500 USDT/order.
No overlap WITHIN the same coin. Different coins may trade simultaneously.
Initial shared cash 10,000 USDT. Fixed 500 inclusive of entry cost, no leverage.
All-in round-trip cost 10bps. Next-open entry, time exit exactly four hours.
Run: python D:\Live_Trade\backtest_mom16_basis_top20_180d_500usdt.py
"""
from pathlib import Path
import hashlib
import heapq
import json
import sys
import numpy as np
import pandas as pd
import backtest_mom16_basis_local_10bps as e

ROOT=Path(__file__).resolve().parent
DATA=ROOT/"binance_top20_15m_2022_now"
OUT=ROOT/"mom16_basis_top20_180d_500usdt_results"
REPORT=ROOT/"bao_cao_mom16_basis_top20_180ngay_500usdt.md"
START=e.utc_ms("2026-04-25T16:15Z");END=e.utc_ms("2026-10-22T13:00Z")
INITIAL=10000.;ORDER=500.;COST=.001

def md_table(df,cols):
    names=dict(coin="Coin",n_trades="Lệnh",gross_winrate="WR trước phí",net_winrate="WR sau phí",
        net_profit="Net_P",max_drawdown="Max DD",gross_pnl="Lãi gross USDT",total_cost="Chi phí USDT",net_pnl="Lãi net USDT",N="Event",P_up="P_up",mean_4h="Mean 4h",edge_bps="Edge sau 10 bps")
    def fmt(v,c):
        if pd.isna(v):return "—"
        if c in ["gross_winrate","net_winrate","net_profit","max_drawdown","P_up","mean_4h"]:return f"{v*100:.2f}%"
        if isinstance(v,(float,np.floating)):return f"{v:.2f}"
        return str(v)
    lines=["| "+" | ".join(names.get(c,c) for c in cols)+" |","|"+" --- |"*len(cols)]
    for _,r in df.iterrows():lines.append("| "+" | ".join(fmt(r[c],c) for c in cols)+" |")
    return "\n".join(lines)

def main():
    sys.stdout.reconfigure(encoding="utf-8");OUT.mkdir(exist_ok=True)
    ready=json.loads((DATA/"READY.json").read_text(encoding="utf-8"))
    frames={};candidates=[];raw=[];sources=[]
    for priority,coin in enumerate(e.TOP20):
        path=DATA/"datasets"/f"{coin}USDT_15m.csv"
        item=next(x for x in ready["coverage"] if x["coin"]==coin)
        sha=hashlib.sha256(path.read_bytes()).hexdigest();assert sha==item["dataset_sha256"]
        d=pd.read_csv(path,usecols=e.NEEDED);d=d[d.timestamp_ms.between(START,END)].reset_index(drop=True)
        ts=d.timestamp_ms.to_numpy();assert np.array_equal(ts,np.arange(START,END+e.BAR,e.BAR))
        assert d.open.notna().all() and d.close.notna().all()
        f=e.features(d);prefix=e.features(d.iloc[:len(d)//2])
        assert np.array_equal(prefix["events"],f["events"][:len(d)//2])
        frames[coin]=d;sources.append(dict(coin=coin,sha256=sha,prefix_invariance=True))
        for i in np.flatnonzero(f["events"]):
            if i+16<len(d):raw.append(dict(coin=coin,signal_ms=int(ts[i]),gross_return=d.close.iloc[i+16]/d.close.iloc[i]-1))
            en=i+1;ex=en+16
            if ex>=len(d):continue
            assert ts[i]+e.BAR-1<ts[en] and ts[ex]-ts[en]==16*e.BAR
            candidates.append(dict(coin=coin,priority=priority,signal_ms=int(ts[i]),entry_ms=int(ts[en]),exit_ms=int(ts[ex]),
                signal_time=e.stamp(ts[i]+e.BAR),entry_time=e.stamp(ts[en]),exit_time=e.stamp(ts[ex]),
                entry_index=int(en),exit_index=int(ex),entry_price=float(d.open.iloc[en]),exit_price=float(d.open.iloc[ex]),
                mom16=float(f["mom16"][i]),mom_q01=float(f["mom_q01"][i]),basis=float(d.basis.iloc[i]),basis_q01=float(f["basis_q01"][i])))
    n=len(next(iter(frames.values())));cash=INITIAL;pending=[];last_exit={};trades=[];decisions=[]
    cashdelta=np.zeros(n);active=np.zeros(n);realized=np.zeros(n)
    quantity={c:np.zeros(n) for c in e.TOP20};coinactive={c:np.zeros(n) for c in e.TOP20};coindelta={c:np.zeros(n) for c in e.TOP20}
    peak=0;seq=0
    for c in sorted(candidates,key=lambda x:(x["entry_ms"],x["priority"])):
        while pending and pending[0][0]<=c["entry_ms"]:
            _,_,proceeds=heapq.heappop(pending);cash+=proceeds
        row=dict(c,cash_before=cash)
        if c["entry_ms"]<last_exit.get(c["coin"],-1):
            decisions.append(dict(row,status="SKIP_SAME_COIN"));continue
        if cash<ORDER-1e-8:
            decisions.append(dict(row,status="SKIP_INSUFFICIENT_CASH"));continue
        en=c["entry_index"];ex=c["exit_index"];coin=c["coin"];op=frames[coin].open.to_numpy()
        notional=ORDER/(1+COST/2);qty=notional/c["entry_price"]
        gp=notional*(c["exit_price"]/c["entry_price"]-1);cost=COST*notional;net=gp-cost
        cash-=ORDER;seq+=1;heapq.heappush(pending,(c["exit_ms"],seq,ORDER+net));last_exit[coin]=c["exit_ms"]
        peak=max(peak,len(pending));cashdelta[en]-=ORDER;cashdelta[ex]+=ORDER+net
        quantity[coin][en]+=qty;quantity[coin][ex]-=qty
        floating=qty*op[en:ex]-ORDER
        active[en:ex]+=floating;realized[ex]+=net;coinactive[coin][en:ex]+=floating;coindelta[coin][ex]+=net
        t=dict(row,trade_id=f"T{seq:04d}",order_budget=ORDER,gross_notional=notional,quantity=qty,
            gross_pnl=gp,total_cost=cost,net_pnl=net,gross_return=gp/notional,net_return=net/notional,cash_after_entry=cash)
        trades.append(t);decisions.append(dict(t,status="EXECUTED"))
    t=pd.DataFrame(trades);eq=INITIAL+np.cumsum(realized)+active
    actualcash=INITIAL+np.cumsum(cashdelta)
    inventory=sum(np.cumsum(quantity[c])*frames[c].open.to_numpy() for c in e.TOP20)
    assert np.allclose(eq,actualcash+inventory,atol=1e-8) and actualcash.min()>=-1e-8
    assert np.isclose(eq[-1],INITIAL+t.net_pnl.sum())
    assert np.allclose(t.total_cost,COST*t.gross_notional)
    assert np.allclose(t.order_budget,500.)
    for coin,g in t.groupby("coin"):
        assert (g.entry_ms.to_numpy()[1:]>=g.exit_ms.to_numpy()[:-1]).all()
    summary=dict(coin="TOTAL",**e.performance(t,eq,INITIAL),gross_pnl=float(t.gross_pnl.sum()),
        total_cost=float(t.total_cost.sum()),net_pnl=float(t.net_pnl.sum()),peak_positions=peak,
        skipped_same_coin=sum(x["status"]=="SKIP_SAME_COIN" for x in decisions),
        skipped_cash=sum(x["status"]=="SKIP_INSUFFICIENT_CASH" for x in decisions))
    percoin=[]
    for coin in e.TOP20:
        g=t[t.coin==coin];ce=500+np.cumsum(coindelta[coin])+coinactive[coin]
        percoin.append(dict(coin=coin,**e.performance(g,ce,500),gross_pnl=float(g.gross_pnl.sum()),
            total_cost=float(g.total_cost.sum()),net_pnl=float(g.net_pnl.sum())))
    # Same initialization, rule and period as the known 60-order top5 subset.
    assert len(t[t.coin.isin(e.TOP5)])==60
    pool=e.event_stats([r["gross_return"] for r in raw])
    pd.DataFrame([summary]).to_csv(OUT/"summary.csv",index=False)
    pd.DataFrame(percoin).to_csv(OUT/"per_coin.csv",index=False)
    pd.DataFrame([pool]).to_csv(OUT/"event_summary.csv",index=False)
    t.to_csv(OUT/"trades.csv",index=False);pd.DataFrame(decisions).to_csv(OUT/"signal_decisions.csv",index=False)
    pd.DataFrame(dict(mark_time=pd.to_datetime(next(iter(frames.values())).timestamp_ms,unit="ms",utc=True),equity=eq,
                      cash=actualcash,inventory_value=inventory)).to_csv(OUT/"equity_15m.csv",index=False)
    meta=dict(start=e.stamp(START),last_mark=e.stamp(END),coins=e.TOP20,cost_bps=10,initial_usd=INITIAL,
        order_budget_usd=ORDER,no_overlap_scope="same coin only; different coins may overlap",
        cash="Shared settled cash, fixed 500/order including entry costs; skip if insufficient; no leverage",
        signal="Original MOM16:L+BASIS:L, 672/168 quantile1%, onset; reset feature warmup at sample start",
        holding="Next-open entry, exit exactly 4h later",sources=sources,
        checks=dict(independent_cash_inventory=True,no_same_coin_overlap=True,all_orders_fixed500=True,
          cost10bps=True,top5_subset_exactly60=True,no_borrowing=True))
    (OUT/"metadata.json").write_text(json.dumps(meta,indent=2),encoding="utf-8")
    cols=["coin","n_trades","gross_winrate","net_winrate","net_profit","max_drawdown","net_pnl"]
    report=["# MOM16:L + BASIS:L: 20 coin, mẫu 180 ngày, 500 USDT/lệnh", "",
        "Chỉ mẫu nghiên cứu ban đầu: **25/04/2026 16:15 đến 22/10/2026 13:00 UTC**, khoảng 180 ngày. Nến 15m, vốn đầu **10.000 USDT**, tổng phí và slippage **10 bps hai đầu**.","",
        "Không mở thêm vị thế khi **cùng coin** đang có lệnh. Coin khác được giao dịch đồng thời, giống quy tắc tạo 60 lệnh top5 trước đây. Mỗi lệnh mua một lần dùng cố định 500 USDT gồm chi phí đầu vào; mua tại open sau nến tín hiệu và bán tại open sau đúng 4h. Không DCA hoặc stop loss trong bảng này.","",
        "Vốn dùng chung 10.000 USDT, chỉ tái sử dụng tiền sau khi thoát. Không cố định 500 USDT tiền mặt vào từng coin sau lỗ vì ngân sách vào lệnh lần này là cố định 500. Tín hiệu bị bỏ nếu tiền khả dụng không đủ. Khi nhiều coin cùng xuất hiện, xử lý theo thứ tự danh sách 20 coin đã công bố, không chọn bằng return tương lai.","",
        "## Kết quả tổng hợp", "",md_table(pd.DataFrame([summary]),cols),"",
        f"Gross PnL **{summary['gross_pnl']:+.2f} USDT**; chi phí **{summary['total_cost']:.2f} USDT**; Net PnL **{summary['net_pnl']:+.2f} USDT**. Vốn cuối **{eq[-1]:.2f} USDT**.","",
        f"Có {len(candidates)} onset đủ giá thực thi; bỏ {summary['skipped_same_coin']} vì cùng coin đang có lệnh; bỏ {summary['skipped_cash']} vì thiếu tiền. Tối đa {peak} vị thế mở đồng thời, tương đương {peak*ORDER:.0f} USDT ngân sách vào đang hoạt động. Không tự cấp thêm vốn hoặc vay tiền.","",
        "## Từng coin", "",md_table(pd.DataFrame(percoin),cols),"",
        "Net_P/Max DD từng coin dùng mốc quy ước 500 USDT để thể hiện đóng góp riêng, không phải tài khoản tiền mặt bị khóa riêng cho coin đó. Max DD danh mục tính từ equity tổng mark-to-market tại open mỗi 15m.","",
        "## Bảng tín hiệu trước khi bỏ overlap trong coin", "",md_table(pd.DataFrame([dict(coin="TOTAL",**pool)]),["coin","N","P_up","mean_4h","edge_bps"]),"",
        "Đây là return close-to-close theo toàn bộ event, không phải số lệnh thực thi. Mô phỏng danh mục ở trên dùng next-open và loại overlap trong coin. Các coin có tương quan, các event không được coi là quan sát độc lập.","",
        "## Chạy lại", "", "```powershell",f"python {Path(__file__)}","```", "",f"Kết quả chi tiết, ledger và equity: `{OUT}`.",
        "Dữ liệu local Binance thật đã có sẵn, không gọi API. Tất cả 20 coin đã niêm yết trước cửa sổ này. Không tối ưu lại ngưỡng hoặc loại coin thua sau khi xem kết quả.",""]
    REPORT.write_text("\n".join(report),encoding="utf-8")
    text="\n".join(["MOM16:L+BASIS:L TOP20 ORIGINAL ~180D | NON OVERLAP PER COIN | FIXED 500 USDT | COST10BPS",
        e.text_table([summary],e.PERF_COLS),"PER COIN:",e.text_table(percoin,e.PERF_COLS),
        f"Gross PnL {summary['gross_pnl']:.2f}, cost {summary['total_cost']:.2f}, net {summary['net_pnl']:.2f} USDT",
        f"Peak positions={peak}, skipped occupied={summary['skipped_same_coin']}, skipped cash={summary['skipped_cash']}",
        f"Saved: {REPORT}"])
    (OUT/"terminal_results.txt").write_text(text+"\n",encoding="utf-8");print(text,flush=True)

if __name__=="__main__":main()
