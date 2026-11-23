"""Continuous causal replay from May1, with a separate earlier feature warmup.

Closed bars drive signals. The current unclosed bar contributes ONLY its known open
for entry/exit/MTM. No historical notification is presented as a fresh live alert.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
import heapq
import json
from pathlib import Path
import sqlite3
import time
import numpy as np
import pandas as pd
from .model import (BAR, BUDGET, COINS, HOLD, INITIAL, MODEL_ID, ROOT, SIGNAL_NAME,
                    BACKTEST_START_MS, HISTORY_START_MS, PROFILE_ID,
                    clean, encode, features, forecast, pnl, signal_id, statistics)

COLUMNS = ["timestamp_ms", "open", "high", "low", "close", "basis"]


class HistoryCache:
    def __init__(self, store):
        self.store = store
        with store.connect() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS history_bars(
              coin TEXT, timestamp_ms INTEGER, open REAL, high REAL, low REAL,
              close REAL, basis REAL, is_closed INTEGER,
              PRIMARY KEY(coin,timestamp_ms));
            CREATE TABLE IF NOT EXISTS coin_marks(
              coin TEXT,time_ms INTEGER,equity REAL,segment TEXT,
              PRIMARY KEY(coin,time_ms));
            """)
        self.start_ms = HISTORY_START_MS

    def ingest(self, coin, d, now_ms):
        d = d[COLUMNS].sort_values("timestamp_ms").drop_duplicates("timestamp_ms").copy()
        if d.empty:
            return
        if (d.timestamp_ms % BAR != 0).any() or not np.isfinite(d.open).all() or (d.open <= 0).any():
            raise ValueError(f"Invalid bar time/open: {coin}")
        d["is_closed"] = (d.timestamp_ms+BAR <= now_ms).astype(int)
        # A closed row is immutable. A partial candle may be completed on the next poll.
        rows = [(coin,int(r.timestamp_ms),float(r.open),float(r.high),float(r.low),
                 float(r.close),None if pd.isna(r.basis) else float(r.basis),int(r.is_closed))
                for r in d.itertuples()]
        with self.store.tx() as c:
            c.executemany("""INSERT INTO history_bars VALUES(?,?,?,?,?,?,?,?)
              ON CONFLICT(coin,timestamp_ms) DO UPDATE SET
              high=excluded.high,low=excluded.low,close=excluded.close,basis=excluded.basis,
              is_closed=excluded.is_closed
              WHERE history_bars.is_closed=0 OR history_bars.basis IS NULL""", rows)

    def bootstrap(self, use_bundle=True):
        seeded=self.store.meta("history_cache_seeded",{})
        if isinstance(seeded,dict) and seeded.get("profile_id")==PROFILE_ID:
            return
        directory = ROOT/"data"/("continuous" if use_bundle else "reference180")
        if not (directory/"manifest.json").exists():
            directory = ROOT/"data"/"reference180"
        manifest = json.loads((directory/"manifest.json").read_text(encoding="utf-8"))
        asof = manifest.get("captured_server_ms", manifest["end_ms"]+BAR)
        for item in manifest["datasets"]:
            path = directory/item["file"]
            if hashlib.sha256(path.read_bytes()).hexdigest() != item["export_sha256"]:
                raise ValueError(f"Bundled history checksum mismatch: {path.name}")
            d = pd.read_csv(path,float_precision="round_trip" if directory.name=="continuous" else None)
            self.ingest(item["coin"],d,asof)
        self.store.set_meta("history_cache_seeded", dict(source=directory.name,asof_ms=asof,profile_id=PROFILE_ID))

    def import_local(self, directory):
        directory = Path(directory)
        snap = json.loads((directory/"snapshot.json").read_text(encoding="utf-8"))
        ready = json.loads((directory/"READY.json").read_text(encoding="utf-8"))
        for coin in COINS:
            path = directory/"datasets"/(coin+"USDT_15m.csv")
            item = next(r for r in ready["coverage"] if r["coin"]==coin)
            if hashlib.sha256(path.read_bytes()).hexdigest() != item["dataset_sha256"]:
                raise ValueError(f"Local source checksum mismatch: {coin}")
            d = pd.read_csv(path,usecols=COLUMNS)
            d = d[d.timestamp_ms>=self.start_ms]
            self.ingest(coin,d,snap["last_closed_end_ms"]+1)
        self.store.set_meta("history_local_import",dict(source=str(directory),closed_through_ms=snap["last_closed_end_ms"]))

    def cursor(self, coin):
        with self.store.connect() as c:
            # Start at a missing/incomplete/invalid bar; pagination never jumps over holes.
            rows = c.execute("SELECT timestamp_ms,is_closed,basis FROM history_bars WHERE coin=? AND timestamp_ms>=? ORDER BY timestamp_ms",(coin,self.start_ms))
            expected = self.start_ms
            for row in rows:
                if row[0] != expected or not row[1] or row[2] is None:
                    return expected
                expected += BAR
            return expected

    def frames(self, target_ms):
        frames = {}
        expected = np.arange(self.start_ms,target_ms+BAR,BAR,dtype=np.int64)
        with self.store.connect() as c:
            for coin in COINS:
                d = pd.read_sql_query("SELECT timestamp_ms,open,high,low,close,basis,is_closed FROM history_bars WHERE coin=? AND timestamp_ms>=? AND timestamp_ms<=? ORDER BY timestamp_ms",
                    c,params=(coin,self.start_ms,target_ms))
                if not np.array_equal(d.timestamp_ms.to_numpy(),expected):
                    raise ValueError(f"History not continuous through target: {coin}")
                closed = d.iloc[:-1]
                if (not closed.is_closed.all() or not np.isfinite(closed[COLUMNS[1:]].to_numpy()).all()
                    or (closed[["open","high","low","close"]]<=0).any().any()):
                    raise ValueError(f"Closed price/premium data incomplete: {coin}")
                frames[coin] = d[COLUMNS]
        return frames

    async def download(self, source, target_ms, now_ms):
        done = set()
        errors = {}
        async def one(coin):
            cursor = self.cursor(coin)
            while cursor <= target_ms:
                end = min(target_ms,cursor+999*BAR)
                d = await source.candles(coin,start=cursor,end=end+BAR-1,limit=1000)
                d = d[d.timestamp_ms.between(cursor,end)]
                expected = np.arange(cursor,end+BAR,BAR)
                if not np.array_equal(d.timestamp_ms.to_numpy(),expected):
                    raise ValueError(f"Missing Binance price bars {coin}: {cursor}..{end}")
                required = d[d.timestamp_ms<target_ms]
                if not np.isfinite(required[COLUMNS[1:]].to_numpy()).all():
                    raise ValueError(f"Premium/closed candle not ready for {coin}")
                self.ingest(coin,d,now_ms)
                cursor = end+BAR
            done.add(coin)
            self.store.set_meta("history_status",dict(phase="downloading",signal_name=SIGNAL_NAME,
                target_ms=target_ms,complete_coins=len(done),total_coins=len(COINS),updated_at_ms=int(time.time()*1000)))
        results = await asyncio.gather(*(one(coin) for coin in COINS),return_exceptions=True)
        for coin,result in zip(COINS,results):
            if isinstance(result,Exception):
                errors[coin] = f"{type(result).__name__}: {result}"
        if errors:
            raise RuntimeError(encode(errors))

    def export(self, directory, target_ms, now_ms):
        directory = Path(directory);directory.mkdir(parents=True,exist_ok=True)
        frames = self.frames(target_ms)
        items = []
        for coin,d in frames.items():
            path = directory/(coin+"USDT_15m.csv.gz")
            d.to_csv(path,index=False,compression="gzip")
            items.append(dict(coin=coin,file=path.name,rows=len(d),
                export_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        manifest = dict(start_ms=BACKTEST_START_MS,history_start_ms=self.start_ms,
            profile_id=PROFILE_ID,end_ms=target_ms,captured_server_ms=now_ms,
            last_closed_open_ms=target_ms-BAR,datasets=items,signal_name=SIGNAL_NAME,
            source="real Binance USD-M local reference + public REST catchup",
            last_row_policy="current 15m candle contributes ONLY its OPEN")
        (directory/"manifest.json").write_text(encode(manifest),encoding="utf-8")
        return manifest


@dataclass
class Book:
    trades: list
    paths: list
    decisions: list
    marks: pd.DataFrame
    coin_equity: dict
    metrics: dict
    start_ms: int
    asof_ms: int
    cash: float
    profile_id: str


def calculate_book(frames, asof_ms=None, start_ms=None):
    """Complete growing-period replay. All choices use only information at entry."""
    sample = frames[COINS[0]]
    ts = sample.timestamp_ms.to_numpy(dtype=np.int64)
    asof_ms = int(ts[-1]) if asof_ms is None else asof_ms
    start_ms = BACKTEST_START_MS if start_ms is None else int(start_ms)
    if start_ms<int(ts[0]) or start_ms>asof_ms or start_ms%BAR:
        raise ValueError("Backtest start is outside the available aligned timeline")
    expected = np.arange(int(ts[0]),asof_ms+BAR,BAR)
    if not np.array_equal(ts,expected):
        raise ValueError("Reference timeline is not continuous")
    n = len(ts)
    candidates = []
    for priority,coin in enumerate(COINS):
        d = frames[coin].reset_index(drop=True)
        if not np.array_equal(d.timestamp_ms.to_numpy(),ts):
            raise ValueError(f"Coin timestamps differ: {coin}")
        # Never evaluate the incomplete last candle. Only its OPEN is observable.
        f = features(d.iloc[:-1])
        for i in np.flatnonzero(f.onset.to_numpy()):
            en,ex = int(i)+1,int(i)+1+HOLD
            if int(ts[en])<start_ms:
                continue  # warmup affects features only; no positions/PnL before start
            info = clean(f.iloc[int(i)].to_dict())
            candidates.append(dict(coin=coin,priority=priority,entry_index=en,exit_index=ex,
                signal_ms=int(ts[i]),entry_ms=int(ts[en]),exit_ms=int(ts[en])+HOLD*BAR,
                entry_price=float(d.open.iloc[en]),features=info))
    realized=np.zeros(n);floating=np.zeros(n);cash_delta=np.zeros(n)
    coin_realized={coin:np.zeros(n) for coin in COINS}
    coin_float={coin:np.zeros(n) for coin in COINS}
    trades=[];decisions=[];mature=[];pending=[];occupied={};cash=INITIAL

    def release(until):
        nonlocal cash
        while pending and pending[0][0]<=until:
            _,_,t,path=heapq.heappop(pending)
            cash += BUDGET+t["net_pnl"]
            mature.append(path)

    for row in sorted(candidates,key=lambda r:(r["entry_ms"],r["priority"])):
        release(row["entry_ms"])
        coin=row["coin"];entry=row["entry_ms"];price=row["entry_price"]
        if entry<occupied.get(coin,-1):
            decisions.append(dict(row,reason="SKIP_SAME_COIN"));continue
        if cash<BUDGET-1e-8:
            decisions.append(dict(row,reason="SKIP_INSUFFICIENT_CASH"));continue
        en,ex=row["entry_index"],row["exit_index"]
        d=frames[coin];sid=signal_id(coin,entry);notional=BUDGET/1.0005;qty=notional/price
        actual=[dict(time_ms=int(ts[j]),price=float(d.open.iloc[j])) for j in range(en,min(ex+1,n))]
        hist=[dict(time_ms=int(ts[j])+BAR,price=float(d.close.iloc[j])) for j in range(max(0,en-32),en)]
        t=dict(row,id=sid,signal_name=SIGNAL_NAME,model_id=MODEL_ID,symbol=coin+"USDT",direction="LONG",
            origin="backfill",notification_live=False,history=hist,actual_path=actual,
            forecast=forecast(mature,coin,entry,price),exit_price=None,order_budget=BUDGET,
            gross_notional=notional,quantity=qty,gross_pnl=None,total_cost=None,net_pnl=None,
            entry_reference="Binance next 15m open; modeled reference, not a user fill",
            settlement="OPEN",stop_loss=None,take_profit=None)
        occupied[coin]=row["exit_ms"];cash-=BUDGET;cash_delta[en]-=BUDGET
        fp=qty*d.open.to_numpy()[en:min(ex,n)]-BUDGET
        floating[en:min(ex,n)]+=fp;coin_float[coin][en:min(ex,n)]+=fp
        if ex<n:
            exit_price=float(d.open.iloc[ex]);t.update(pnl(price,exit_price),exit_price=exit_price,settlement="SETTLED")
            realized[ex]+=t["net_pnl"];coin_realized[coin][ex]+=t["net_pnl"]
            cash_delta[ex]+=BUDGET+t["net_pnl"]
            path=dict(id=sid,coin=coin,exit_ms=row["exit_ms"],returns=[p["price"]/price-1 for p in actual])
            heapq.heappush(pending,(row["exit_ms"],len(trades),t,path))
        trades.append(t);decisions.append(dict(row,reason="ACCEPTED"))
    release(asof_ms)
    eq=INITIAL+np.cumsum(realized)+floating
    cash_curve=INITIAL+np.cumsum(cash_delta)
    if cash_curve.min() < -1e-7:
        raise AssertionError("Borrowed cash in continuous reference book")
    if not np.isclose(cash,cash_curve[-1],atol=1e-7,rtol=0):
        raise AssertionError("Ledger cash does not reconcile")
    visible=ts>=start_ms
    marks=pd.DataFrame(dict(time_ms=ts[visible],equity=eq[visible],cash=cash_curve[visible],segment="continuous"))
    coin_eq={coin:(BUDGET+np.cumsum(coin_realized[coin])+coin_float[coin])[visible] for coin in COINS}
    metrics={"TOTAL":statistics(trades,marks.to_dict("records"))}
    for coin in COINS:
        own=[t for t in trades if t["coin"]==coin]
        ce=[dict(time_ms=int(k),equity=float(v),segment="continuous") for k,v in zip(ts[visible],coin_eq[coin])]
        metrics[coin]=statistics(own,ce,BUDGET)
    profile=f"{MODEL_ID}:start{start_ms}:warmup{(start_ms-int(ts[0]))//BAR}"
    return Book(trades,mature,decisions,marks,coin_eq,metrics,start_ms,asof_ms,float(cash),profile)


def apply_book(store, book, now_ms, live_notices=False):
    """Replace a legacy book once, then append continuous marks/trades atomically."""
    prior_profile=store.meta("continuous_profile_id")
    changing=store.meta("continuous_version")==1 and prior_profile!=book.profile_id
    if changing:
        suffix=hashlib.sha256(str(prior_profile).encode()).hexdigest()[:12]
        archive=store.path.parent/("before_profile_"+suffix+".sqlite3")
        if not archive.exists():
            with store.connect() as source:
                target=sqlite3.connect(archive)
                try:source.backup(target)
                finally:target.close()
    with store.tx() as c:
        continuous=store.get(c,"continuous_version") == 1 and store.get(c,"continuous_profile_id")==book.profile_id
        previous={r[0]:json.loads(r[1]) for r in c.execute("SELECT id,data FROM trades")} if continuous else {}
        old_asof=store.get(c,"continuous_asof_ms",-1)
        if continuous and book.asof_ms<old_asof:
            raise ValueError("Refusing to rewind continuous history")
        if not continuous:
            c.execute("DELETE FROM trades");c.execute("DELETE FROM marks");c.execute("DELETE FROM paths")
            c.execute("DELETE FROM decisions");c.execute("DELETE FROM coin_marks")
            c.execute("DELETE FROM notifications");c.execute("DELETE FROM reads")
            if changing:
                c.execute("DELETE FROM events")
                live_notices=False  # a profile rebuild must not replay live alerts
        new_ids={t["id"] for t in book.trades}
        if continuous and not set(previous).issubset(new_ids):
            raise ValueError("An immutable historical trade disappeared; refusing silent rewrite")
        opened=[];ended=[];historical_added=0
        for t in book.trades:
            old=previous.get(t["id"])
            if old:
                for key in ("origin","detected_ms","latency_ms","notification_live"):
                    if key in old:t[key]=old[key]
                if old.get("forecast") and old["entry_price"] == t["entry_price"]:
                    t["forecast"]=old["forecast"]
                if old.get("exit_price") is None and t["exit_price"] is not None:
                    ended.append(t["id"])
            else:
                fresh=(live_notices and t["entry_ms"]==book.asof_ms and
                       0<=now_ms-t["entry_ms"]<=120_000 and t["exit_price"] is None)
                if fresh:
                    t.update(origin="forward_paper",notification_live=True,detected_ms=now_ms,latency_ms=now_ms-t["entry_ms"])
                    opened.append(t)
                else:
                    historical_added+=1
            if not old or not continuous or old.get("exit_price")!=t["exit_price"] or old.get("actual_path")!=t["actual_path"]:
                c.execute("INSERT INTO trades VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET exit_price=excluded.exit_price,data=excluded.data",
                    (t["id"],t["coin"],t["entry_ms"],t["exit_ms"],t["exit_price"],encode(t)))
        for p in book.paths:
            c.execute("INSERT OR IGNORE INTO paths VALUES(?,?,?,?)",(p["id"],p["coin"],p["exit_ms"],encode(p)))
        floor=old_asof if continuous else book.start_ms
        tail=book.marks[book.marks.time_ms>=floor]
        c.executemany("INSERT INTO marks VALUES(?,?,?,?) ON CONFLICT(time_ms) DO UPDATE SET equity=excluded.equity,cash=excluded.cash,segment=excluded.segment",
            ((int(r.time_ms),float(r.equity),float(r.cash),"continuous") for r in tail.itertuples()))
        ts=book.marks.time_ms.to_numpy()
        keep=ts>=floor
        for coin in COINS:
            c.executemany("INSERT INTO coin_marks VALUES(?,?,?,?) ON CONFLICT(coin,time_ms) DO UPDATE SET equity=excluded.equity,segment=excluded.segment",
                ((coin,int(t),float(eq),"continuous") for t,eq in zip(ts[keep],book.coin_equity[coin][keep])))
        c.executemany("INSERT OR REPLACE INTO decisions VALUES(?,?,?,?)",((d["coin"],d["entry_ms"],d["reason"],encode(d["features"])) for d in book.decisions if not continuous or d["entry_ms"]>=floor))
        c.execute("DELETE FROM notifications")
        for t in sorted(book.trades,key=lambda r:(r["entry_ms"],r["id"]))[-5:]:
            c.execute("INSERT INTO notifications VALUES(?,?)",(t["id"],t["entry_ms"]))
        c.execute("DELETE FROM reads WHERE signal_id NOT IN (SELECT id FROM notifications)")
        store.put(c,"cash",book.cash);store.put(c,"continuous_version",1)
        store.put(c,"continuous_profile_id",book.profile_id)
        store.put(c,"continuous_asof_ms",book.asof_ms)
        store.put(c,"continuous_start_ms",book.start_ms)
        store.put(c,"marks_quality",dict(missing_forward_marks=0,continuous=True))
        for scope,stats in book.metrics.items():store.put(c,"continuous_stats_"+scope,stats)
        status=dict(phase="ready",signal_name=SIGNAL_NAME,profile_id=book.profile_id,start_ms=book.start_ms,as_of_ms=book.asof_ms,
            last_closed_open_ms=book.asof_ms-BAR,n_closed=book.metrics["TOTAL"]["n_trades"],
            n_open=book.metrics["TOTAL"]["open_trades"],historical_trades_added=historical_added,
            updated_at_ms=now_ms,continuous=True)
        store.put(c,"history_status",status)
        if not continuous or old_asof!=book.asof_ms:
            store.emit(c,"history.updated",status,now_ms)
            store.emit(c,"stats.updated",dict(as_of_ms=book.asof_ms),now_ms)
        for t in opened:store.emit(c,"signal.opened",dict(signal_id=t["id"],coin=t["coin"],entry_ms=t["entry_ms"],signal_name=SIGNAL_NAME),now_ms)
        for sid in ended:store.emit(c,"signal.ended",dict(signal_id=sid),now_ms)
    return status


def initialize_snapshot(store):
    cache=HistoryCache(store)
    cache.bootstrap()
    if store.meta("continuous_version")==1 and store.meta("continuous_profile_id")==PROFILE_ID:
        return
    manifest_path=ROOT/"data"/"continuous"/"manifest.json"
    if not manifest_path.exists():
        return
    # Preserve a deployed v1 ledger before its old gap policy is replaced by full reconstruction.
    if any(t.get("origin")=="forward_paper" for t in store.trades()):
        archive=store.path.parent/"legacy_v1_before_continuous.sqlite3"
        if not archive.exists():
            with store.connect() as source:
                target=sqlite3.connect(archive)
                try:source.backup(target)
                finally:target.close()
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    target=max(manifest["end_ms"],store.meta("continuous_asof_ms",0))
    book=calculate_book(cache.frames(target))
    apply_book(store,book,max(manifest["captured_server_ms"],int(time.time()*1000)),live_notices=False)


def metrics(store,coin=None):
    scope=coin or "TOTAL"
    result=store.meta("continuous_stats_"+scope)
    with store.connect() as c:
        if coin:
            rows=[dict(r) for r in c.execute("SELECT time_ms,equity,segment FROM coin_marks WHERE coin=? ORDER BY time_ms",(coin,))]
        else:
            rows=[dict(r) for r in c.execute("SELECT time_ms,equity,segment FROM marks ORDER BY time_ms")]
    baseline=store.meta("baseline")
    if baseline:baseline.update(gap_policy="Archived Apr25 reference only; current profile starts May1 with earlier feature warmup")
    result.update(coin=scope,signal_name=SIGNAL_NAME,model_id=MODEL_ID,profile_id=store.meta("continuous_profile_id"),
        updated_at_ms=int(time.time()*1000),baseline=baseline,history=store.meta("history_status"),
        data_start_ms=store.meta("continuous_start_ms"),data_as_of_ms=store.meta("continuous_asof_ms"),
        marks_quality=store.meta("marks_quality"),equity_curve=rows)
    if coin:result["capital_note"]="Per-coin attribution divided by 500 USDT; shared portfolio starts at 10,000 USDT"
    return result


async def synchronize(store,source,local_data=None,export=None,live_notices=False):
    cache=HistoryCache(store);cache.bootstrap()
    if local_data:cache.import_local(local_data)
    # If a new 15m boundary arrives during download/replay, catch it before reporting ready.
    for attempt in range(4):
        now=await source.server_ms();target=now//BAR*BAR
        store.set_meta("history_status",dict(phase="downloading",signal_name=SIGNAL_NAME,
            target_ms=target,start_ms=BACKTEST_START_MS,history_start_ms=cache.start_ms,updated_at_ms=now))
        await cache.download(source,target,now)
        store.set_meta("history_status",dict(phase="replaying",target_ms=target,signal_name=SIGNAL_NAME,updated_at_ms=now))
        frames=await asyncio.to_thread(cache.frames,target)
        book=await asyncio.to_thread(calculate_book,frames)
        check_now=await source.server_ms()
        if check_now//BAR*BAR!=target:
            continue
        status=await asyncio.to_thread(apply_book,store,book,check_now,live_notices)
        if export:cache.export(export,target,check_now)
        return status
    raise RuntimeError("History is still crossing boundaries; retry catchup before declaring ready")
