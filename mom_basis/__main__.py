from __future__ import annotations
import argparse
import asyncio
import json
import os
from pathlib import Path
import time
from .model import BAR, COINS, ROOT, SIGNAL_NAME, encode, features


async def probe(coins):
    from .feed import BinancePublic
    source = BinancePublic()
    try:
        now = await source.server_ms()
        rows = []
        for coin in coins:
            d = await source.candles(coin)
            closed = d[d.timestamp_ms+BAR <= now].tail(689).reset_index(drop=True)
            f = features(closed)
            rows.append(dict(coin=coin, closed_candles=len(closed),
                last_closed_open_ms=int(closed.timestamp_ms.iloc[-1]),
                basis_missing=int(closed.basis.isna().sum()),
                continuous=bool((closed.timestamp_ms.diff().dropna()==BAR).all()),
                latest_features=f.iloc[-1].to_dict(), latest_close=float(closed.close.iloc[-1])))
        quotes = await source.quotes(now)
        return dict(signal_name=SIGNAL_NAME,real_public_api=True, server_time_ms=now, checked_at_ms=int(time.time()*1000),
                    rows=rows, quote_count=len(quotes), notifications_created=0, orders_submitted=0)
    finally:
        await source.close()


def main():
    p = argparse.ArgumentParser(description=SIGNAL_NAME+" continuous backtest and live signal service")
    sub = p.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init");init.add_argument("--state-dir",type=Path,default=ROOT/"state")
    serve = sub.add_parser("serve")
    serve.add_argument("--mode",choices=["offline","live"],default="live")
    serve.add_argument("--state-dir",type=Path,default=ROOT/"state")
    serve.add_argument("--host",default="127.0.0.1");serve.add_argument("--port",type=int,default=8765)
    replay = sub.add_parser("replay");replay.add_argument("--out",type=Path,default=ROOT/"evidence")
    replay.add_argument("--legacy-reference",action="store_true",help="Audit the archived Apr25/241-trade reference instead of the current May1 profile")
    sync=sub.add_parser("sync",help="Catch up the May1 profile with prior feature warmup through current Binance time")
    sync.add_argument("--state-dir",type=Path,default=ROOT/"state")
    sync.add_argument("--local-data",type=Path)
    sync.add_argument("--export",type=Path)
    sync.add_argument("--report",type=Path,default=ROOT/"evidence"/"continuous")
    check = sub.add_parser("probe");check.add_argument("--coins",nargs="+",choices=COINS,default=list(COINS))
    check.add_argument("--out",type=Path,default=ROOT/"evidence"/"live_public_api_probe.json")
    sub.add_parser("stats")
    args = p.parse_args()
    if args.command == "replay":
        from .replay import reproduce,reproduce_current
        r = reproduce(args.out) if args.legacy_reference else reproduce_current(args.out)
        s = r["summary"]
        print(f"TOTAL | {s['n_trades']} trades | WR gross {s['gross_winrate']:.2%} | WR net {s['net_winrate']:.2%} | Net_P {s['net_profit']:+.2%} | Max DD {s['max_drawdown']:.2%}")
        print(encode(r["checks"]))
    elif args.command == "sync":
        from .continuous import synchronize
        from .feed import BinancePublic
        from .store import Store
        store=Store(args.state_dir/"model.sqlite3")
        async def run():
            source=BinancePublic()
            try:
                return await synchronize(store,source,local_data=args.local_data,export=args.export)
            finally:
                await source.close()
        from .api import ProcessLock
        with ProcessLock(args.state_dir/"worker.lock"):
            store.seed()
            status=asyncio.run(run())
        args.report.mkdir(parents=True,exist_ok=True)
        import pandas as pd
        total=store.metrics();total.pop("equity_curve")
        per_coin=[]
        for coin in COINS:
            own=store.metrics(coin);own.pop("equity_curve");per_coin.append(own)
        (args.report/"summary.json").write_text(json.dumps(total,ensure_ascii=False,indent=2),encoding="utf-8")
        pd.DataFrame(per_coin).drop(columns=["history","baseline"],errors="ignore").to_csv(args.report/"per_coin.csv",index=False)
        pd.DataFrame(store.trades()).to_csv(args.report/"trades.csv",index=False)
        pd.DataFrame([total]).drop(columns=["history","baseline"],errors="ignore").to_csv(args.report/"summary.csv",index=False)
        print(encode(dict(status=status,summary=total)))
    elif args.command == "probe":
        result = asyncio.run(probe(args.coins))
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(json.loads(encode(result)),ensure_ascii=False,indent=2),encoding="utf-8")
        print(encode(result))
    elif args.command == "serve":
        import uvicorn
        from .api import create_app
        # Pass the constructed app; no reload or multi-worker forks for this SQLite MVP.
        uvicorn.run(create_app(args.state_dir,live=args.mode=="live"),host=args.host,port=args.port,log_level="info")
    else:
        from .store import Store
        store = Store(getattr(args,"state_dir",ROOT/"state")/"model.sqlite3")
        seeded = store.seed()
        from .continuous import initialize_snapshot
        initialize_snapshot(store)
        if args.command == "init":
            print(encode(dict(initialized=seeded,db=str(store.path))))
        else:
            r = store.metrics();r.pop("equity_curve")
            print(json.dumps(r,ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
