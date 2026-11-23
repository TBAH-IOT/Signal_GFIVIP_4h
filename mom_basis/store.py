from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time
from functools import lru_cache
import numpy as np
import pandas as pd
from .model import (BAR, BUDGET, COINS, HOLD, INITIAL, LIVE_WARMUP, MODEL_ID,
                    ROOT, SIGNAL_NAME, SPEC_HASH, clean, encode, features, forecast, pnl, signal_id, statistics)


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


@lru_cache(maxsize=1)
def coin_seed():
    return json.loads((ROOT/"data"/"baseline"/"coin_equity.json").read_text(encoding="utf-8"))


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as c:
            c.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS trades(id TEXT PRIMARY KEY,coin TEXT NOT NULL,
              entry_ms INTEGER NOT NULL,exit_ms INTEGER NOT NULL,exit_price REAL,data TEXT NOT NULL);
            CREATE UNIQUE INDEX IF NOT EXISTS one_open_per_coin ON trades(coin) WHERE exit_price IS NULL;
            CREATE TABLE IF NOT EXISTS paths(id TEXT PRIMARY KEY,coin TEXT,exit_ms INTEGER,data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS marks(time_ms INTEGER PRIMARY KEY,equity REAL,cash REAL,segment TEXT);
            CREATE TABLE IF NOT EXISTS candles(coin TEXT,time_ms INTEGER,data TEXT,PRIMARY KEY(coin,time_ms));
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,kind TEXT,data TEXT,created_ms INTEGER);
            CREATE TABLE IF NOT EXISTS notifications(id TEXT PRIMARY KEY,entry_ms INTEGER);
            CREATE TABLE IF NOT EXISTS reads(user_id TEXT,signal_id TEXT,PRIMARY KEY(user_id,signal_id));
            CREATE TABLE IF NOT EXISTS decisions(coin TEXT,entry_ms INTEGER,reason TEXT,data TEXT,
              PRIMARY KEY(coin,entry_ms));
            """)

    def connect(self):
        c = sqlite3.connect(self.path, timeout=30, factory=ClosingConnection)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA busy_timeout=30000")
        return c

    @contextmanager
    def tx(self):
        c = self.connect()
        try:
            c.execute("BEGIN IMMEDIATE")
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    @staticmethod
    def get(c, key, default=None):
        row = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    @staticmethod
    def put(c, key, value):
        c.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", (key, encode(value)))

    @staticmethod
    def emit(c, kind, data, now):
        c.execute("INSERT INTO events(kind,data,created_ms) VALUES(?,?,?)", (kind, encode(data), now))
        c.execute("DELETE FROM events WHERE id < (SELECT COALESCE(MAX(id),0)-1000 FROM events)")

    @staticmethod
    def notify(c, sid, entry_ms):
        c.execute("INSERT OR IGNORE INTO notifications VALUES(?,?)", (sid, entry_ms))
        c.execute("DELETE FROM notifications WHERE id NOT IN (SELECT id FROM notifications ORDER BY entry_ms DESC,id DESC LIMIT 5)")
        c.execute("DELETE FROM reads WHERE signal_id NOT IN (SELECT id FROM notifications)")

    def seed(self, baseline=ROOT / "data" / "baseline"):
        seed = json.loads((baseline / "seed.json").read_text(encoding="utf-8"))
        with self.tx() as c:
            if self.get(c, "initialized"):
                if self.get(c, "spec_hash") != SPEC_HASH:
                    raise RuntimeError("Model configuration differs from initialized DB; use a new state directory")
                return False
            for t in seed["trades"]:
                c.execute("INSERT INTO trades VALUES(?,?,?,?,?,?)", (t["id"], t["coin"], t["entry_ms"], t["exit_ms"], t["exit_price"], encode(t)))
            for p in seed["paths"]:
                c.execute("INSERT INTO paths VALUES(?,?,?,?)", (p["id"], p["coin"], p["exit_ms"], encode(p)))
            eq = pd.read_csv(baseline / "equity_15m.csv")
            c.executemany("INSERT INTO marks VALUES(?,?,?,?)",
                ((int(pd.Timestamp(r.mark_time).value // 1_000_000), float(r.equity), float(r.cash), "reference") for r in eq.itertuples()))
            self.put(c, "cash", seed["final_cash"])
            self.put(c, "initialized", True)
            self.put(c, "spec_hash", SPEC_HASH)
            self.put(c, "baseline", seed["metadata"])
            self.put(c, "worker", dict(mode="offline", feed_status="not_started"))
            # Historical notifications are READ by default; no fake live trigger is emitted.
            for t in sorted(seed["trades"], key=lambda t: (t["entry_ms"], t["id"]))[-5:]:
                self.notify(c, t["id"], t["entry_ms"])
        return True

    def meta(self, key, default=None):
        with self.connect() as c:
            return self.get(c, key, default)

    def set_meta(self, key, value):
        with self.tx() as c:
            self.put(c, key, value)

    def trades(self, coin=None):
        with self.connect() as c:
            rows = c.execute("SELECT data FROM trades" + (" WHERE coin=?" if coin else "") + " ORDER BY entry_ms,id", (coin,) if coin else ())
            return [json.loads(r[0]) for r in rows]

    def pending(self):
        return [t for t in self.trades() if t["exit_price"] is None]

    def events(self, after):
        with self.connect() as c:
            return [dict(r) for r in c.execute("SELECT * FROM events WHERE id>? ORDER BY id LIMIT 1001", (after,))]

    def latest_event_id(self):
        with self.connect() as c:
            return c.execute("SELECT COALESCE(MAX(id),0) FROM events").fetchone()[0]

    def save_candles(self, frames):
        with self.tx() as c:
            for coin, d in frames.items():
                c.executemany("INSERT OR REPLACE INTO candles VALUES(?,?,?)", ((coin, int(r["timestamp_ms"]), encode(r)) for r in d.to_dict("records")))
                # Keep >=7d warmup; old closed paths are archived separately.
                cutoff = int(d.timestamp_ms.max()) - 14 * 96 * BAR
                if not c.execute("SELECT 1 FROM trades WHERE coin=? AND exit_price IS NULL", (coin,)).fetchone():
                    c.execute("DELETE FROM candles WHERE coin=? AND time_ms<?", (coin, cutoff))

    def accept_batch(self, entry_ms, frames, opens, now_ms, max_lag_ms=120_000):
        """One atomic portfolio decision in fixed priority order. No future price is read."""
        accepted = []
        with self.tx() as c:
            if entry_ms <= self.get(c, "baseline", {}).get("end_ms", -1):
                return []  # an imported historical trade cannot be replayed as a new live notification
            cash = self.get(c, "cash", INITIAL)
            for coin in COINS:
                d = frames.get(coin)
                if d is None or len(d) < LIVE_WARMUP:
                    continue
                d = d.sort_values("timestamp_ms").tail(LIVE_WARMUP).reset_index(drop=True)
                if (int(d.timestamp_ms.iloc[-1]) != entry_ms - BAR or
                    not np.array_equal(d.timestamp_ms.to_numpy(), np.arange(entry_ms - len(d)*BAR, entry_ms, BAR)) or
                    not np.isfinite(d[["open", "high", "low", "close", "basis"]].to_numpy()).all() or
                    (d[["open", "high", "low", "close"]] <= 0).any().any()):
                    continue  # no ffill for missing premium, no partial candles
                f = features(d)
                if not bool(f.onset.iloc[-1]):
                    continue
                if c.execute("SELECT 1 FROM decisions WHERE coin=? AND entry_ms=?", (coin, entry_ms)).fetchone():
                    continue
                info = clean(f.iloc[-1].to_dict())
                reason = "ACCEPTED"
                if not (0 <= now_ms - entry_ms <= max_lag_ms):
                    reason = "SKIP_STALE_SIGNAL"
                elif c.execute("SELECT 1 FROM trades WHERE coin=? AND exit_price IS NULL", (coin,)).fetchone():
                    reason = "SKIP_SAME_COIN"
                elif cash < BUDGET - 1e-8:
                    reason = "SKIP_INSUFFICIENT_CASH"
                elif coin not in opens or not np.isfinite(opens[coin]) or opens[coin] <= 0:
                    # Retry this symbol on a later poll while still inside the admission window.
                    continue
                c.execute("INSERT INTO decisions VALUES(?,?,?,?)", (coin, entry_ms, reason, encode(info)))
                if reason != "ACCEPTED":
                    continue
                sid = signal_id(coin, entry_ms)
                price = float(opens[coin])
                paths = [json.loads(r[0]) for r in c.execute("SELECT data FROM paths WHERE exit_ms<=?", (entry_ms,))]
                fp = forecast(paths, coin, entry_ms, price)
                history = [dict(time_ms=int(r.timestamp_ms)+BAR, price=float(r.close)) for r in d.tail(32).itertuples()]
                t = dict(id=sid, coin=coin, symbol=coin+"USDT", direction="LONG", model_id=MODEL_ID,
                    origin="forward_paper", signal_ms=entry_ms-BAR, entry_ms=entry_ms,
                    exit_ms=entry_ms+HOLD*BAR, detected_ms=now_ms, latency_ms=now_ms-entry_ms,
                    entry_price=price, exit_price=None, order_budget=BUDGET,
                    gross_notional=BUDGET/1.0005, quantity=BUDGET/1.0005/price,
                    gross_pnl=None, total_cost=None, net_pnl=None,
                    features=info, forecast=fp, history=history, actual_path=[],
                    entry_reference="Binance next 15m open; not a guaranteed user fill",
                    settlement="OPEN", stop_loss=None, take_profit=None)
                c.execute("INSERT INTO trades VALUES(?,?,?,?,?,?)", (sid, coin, entry_ms, t["exit_ms"], None, encode(t)))
                cash -= BUDGET
                self.notify(c, sid, entry_ms)
                if self.get(c,"forward_first_boundary_ms") is None:
                    self.put(c,"forward_first_boundary_ms",entry_ms)
                self.put(c,"marks_dirty_from",min(entry_ms,self.get(c,"marks_dirty_from",entry_ms)))
                self.emit(c, "signal.opened", dict(signal_id=sid, coin=coin, entry_ms=entry_ms), now_ms)
                accepted.append(sid)
            self.put(c, "cash", cash)
        return accepted

    def settle(self, sid, exit_price, path, now_ms):
        with self.tx() as c:
            row = c.execute("SELECT data FROM trades WHERE id=?", (sid,)).fetchone()
            if not row:
                raise KeyError(sid)
            t = json.loads(row[0])
            if t["exit_price"] is not None:
                return False
            if now_ms < t["exit_ms"]:
                raise ValueError("Cannot settle before the four-hour deadline")
            if not np.isfinite(exit_price) or exit_price <= 0:
                raise ValueError("Invalid exit price")
            t.update(pnl(t["entry_price"], exit_price), exit_price=float(exit_price),
                     settlement="SETTLED", settled_at_ms=now_ms, actual_path=path)
            c.execute("UPDATE trades SET exit_price=?,data=? WHERE id=?", (exit_price, encode(t), sid))
            self.put(c, "cash", self.get(c, "cash") + BUDGET + t["net_pnl"])
            if len(path) == HOLD+1 and [p["time_ms"] for p in path] == list(range(t["entry_ms"], t["exit_ms"]+BAR, BAR)):
                p = dict(id=sid, coin=t["coin"], exit_ms=t["exit_ms"], returns=[r["price"]/t["entry_price"]-1 for r in path])
                c.execute("INSERT OR IGNORE INTO paths VALUES(?,?,?,?)", (sid, t["coin"], t["exit_ms"], encode(p)))
            self.emit(c, "signal.ended", dict(signal_id=sid, coin=t["coin"]), now_ms)
            self.emit(c, "stats.updated", dict(signal_id=sid, coin=t["coin"]), now_ms)
            dirty = self.get(c, "marks_dirty_from", t["entry_ms"])
            self.put(c, "marks_dirty_from", min(dirty, t["entry_ms"]))
        return True

    def reconcile_marks(self, boundary_ms):
        """Rebuild missing forward MTM from real opens, including downtime and delayed exits."""
        with self.tx() as c:
            first = self.get(c, "forward_first_boundary_ms")
            if first is None:
                # Earliest admitted forward position is also a real deployment observation.
                oldest = c.execute("SELECT MIN(entry_ms) FROM trades WHERE exit_price IS NULL").fetchone()[0]
                first = min(boundary_ms, oldest) if oldest is not None else boundary_ms
                self.put(c, "forward_first_boundary_ms", first)
            latest = c.execute("SELECT MAX(time_ms) FROM marks WHERE segment='forward'").fetchone()[0]
            changed = latest is None or latest < boundary_ms or self.get(c,"marks_dirty_from") is not None
            start = max(first, min(latest or first, self.get(c, "marks_dirty_from", latest or first)))
            all_trades = [json.loads(r[0]) for r in c.execute("SELECT data FROM trades")]
            trades = [t for t in all_trades if t["origin"] == "forward_paper"]
            base = INITIAL + sum(t["net_pnl"] for t in all_trades if t["origin"] == "backtest")
            prices = {(r["coin"],r["time_ms"]):json.loads(r["data"])["open"] for r in c.execute("SELECT * FROM candles WHERE time_ms>=? AND time_ms<=?",(start,boundary_ms))}
            for t in trades:
                for p in t.get("actual_path",[]):
                    prices[(t["coin"],p["time_ms"])] = p["price"]
                prices[(t["coin"],t["entry_ms"])] = t["entry_price"]
            missing = []
            for mark in range(start,boundary_ms+BAR,BAR):
                cash = base; inventory = 0.; valid = True
                for t in trades:
                    if t["entry_ms"] > mark:
                        continue
                    if t["exit_price"] is not None and t["exit_ms"] <= mark:
                        cash += t["net_pnl"]
                    else:
                        if t["exit_ms"] < mark or (t["coin"],mark) not in prices:
                            valid = False
                            break
                        cash -= BUDGET
                        inventory += t["quantity"]*prices[(t["coin"],mark)]
                if not valid:
                    missing.append(mark)
                    continue
                c.execute("INSERT INTO marks VALUES(?,?,?,?) ON CONFLICT(time_ms) DO UPDATE SET equity=excluded.equity,cash=excluded.cash,segment=excluded.segment",(mark,cash+inventory,cash,"forward"))
            self.put(c,"marks_quality",dict(missing_forward_marks=len(missing),first_missing_ms=min(missing) if missing else None))
            if missing:
                self.put(c,"marks_dirty_from",min(missing))
            else:
                c.execute("DELETE FROM meta WHERE key='marks_dirty_from'")
            if changed:
                self.emit(c,"equity.updated",dict(time_ms=boundary_ms,complete=not missing),int(time.time()*1000))
            return not missing

    def mark(self, boundary_ms, prices, segment="forward"):
        if boundary_ms % BAR:
            raise ValueError("Equity mark must use a 15m open boundary")
        with self.tx() as c:
            pending = [json.loads(r[0]) for r in c.execute("SELECT data FROM trades WHERE exit_price IS NULL")]
            if any(t["entry_ms"] > boundary_ms or t["exit_ms"] < boundary_ms or t["coin"] not in prices for t in pending):
                return False
            cash = self.get(c, "cash", INITIAL)
            equity = cash + sum(t["quantity"] * prices[t["coin"]] for t in pending)
            c.execute("INSERT INTO marks VALUES(?,?,?,?) ON CONFLICT(time_ms) DO UPDATE SET equity=excluded.equity,cash=excluded.cash,segment=excluded.segment", (boundary_ms, equity, cash, segment))
        return True

    def metrics(self, coin=None):
        if self.meta("continuous_version")==1:
            from .continuous import metrics
            return metrics(self,coin)
        trades = self.trades(coin)
        with self.connect() as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM marks ORDER BY time_ms")]
        if coin is None:
            result = statistics(trades, rows)
        else:
            # Per-coin metrics use an explicitly separate 500 USDT reference, not portfolio capital.
            curve = list(coin_seed().get(coin, []))
            forward = [t for t in trades if t["origin"] == "forward_paper"]
            if forward:
                base_profit = sum(t["net_pnl"] for t in trades if t["origin"] == "backtest")
                with self.connect() as c:
                    for row in (r for r in rows if r["segment"] == "forward"):
                        mark = row["time_ms"]
                        value = BUDGET + base_profit
                        valid = True
                        for t in forward:
                            if t["entry_ms"] > mark:
                                continue
                            if t["exit_price"] is not None and t["exit_ms"] <= mark:
                                value += t["net_pnl"]
                            else:
                                bar = c.execute("SELECT data FROM candles WHERE coin=? AND time_ms=?", (coin, mark)).fetchone()
                                if not bar:
                                    valid = False
                                    break
                                value += t["quantity"]*json.loads(bar[0])["open"]-BUDGET
                        if valid:
                            curve.append(dict(time_ms=mark, equity=value, segment="forward"))
            rows = curve
            result = statistics(trades, rows, BUDGET)
            result["capital_note"] = "Per-coin attribution divided by 500 USDT; shared portfolio starts at 10,000 USDT"
        result.update(coin=coin or "TOTAL", model_id=MODEL_ID, updated_at_ms=int(time.time()*1000),
                      baseline=self.meta("baseline"), forward_started_ms=self.meta("forward_started_ms"),
                      marks_quality=self.meta("marks_quality", {}),
                      equity_curve=[dict(time_ms=r["time_ms"], equity=r["equity"], segment=r["segment"]) for r in rows])
        return result

    def view(self, t, now_ms):
        r = dict(t)
        r["signal_name"] = SIGNAL_NAME
        ended = now_ms >= t["exit_ms"]
        r["status"] = "ENDED" if ended else "OPEN"
        r["status_label"] = "Đã kết thúc" if ended else "Đang mở"
        if ended and t["exit_price"] is None:
            r["settlement"] = "PENDING_MARKET_DATA"
        quote = self.meta("quotes", {}).get(t["coin"])
        r["quote"] = quote
        r["quote_stale"] = not quote or now_ms-quote["received_ms"] > 20_000 or now_ms-quote["exchange_ms"] > 20_000
        r["remaining_seconds"] = max(0, (t["exit_ms"]-now_ms)//1000)
        if t["exit_price"] is None and quote:
            r["unrealized_net_pnl"] = pnl(t["entry_price"], quote["price"])["net_pnl"]
        with self.connect() as c:
            if not r.get("actual_path"):
                rows = c.execute("SELECT time_ms,data FROM candles WHERE coin=? AND time_ms>=? AND time_ms<=? ORDER BY time_ms",
                                 (t["coin"], t["entry_ms"], min(now_ms, t["exit_ms"])))
                r["actual_path"] = [dict(time_ms=x[0], price=json.loads(x[1])["open"]) for x in rows]
        return r

    def notifications(self, user_id, now_ms):
        with self.connect() as c:
            rows = c.execute("SELECT t.data,EXISTS(SELECT 1 FROM reads r WHERE r.signal_id=t.id AND r.user_id=?) AS was_read FROM notifications n JOIN trades t ON t.id=n.id ORDER BY n.entry_ms DESC,n.id DESC LIMIT 5", (user_id,))
            result = []
            for row in rows:
                t = self.view(json.loads(row[0]), now_ms)
                t["unread"] = not bool(row[1]) and t.get("notification_live",t["origin"]=="forward_paper")
                result.append(t)
            return result

    def detail(self, sid, now_ms):
        with self.connect() as c:
            row = c.execute("SELECT data FROM trades WHERE id=? AND id IN (SELECT id FROM notifications)", (sid,)).fetchone()
        return self.view(json.loads(row[0]), now_ms) if row else None

    def read(self, user_id, sid):
        with self.tx() as c:
            if c.execute("SELECT 1 FROM notifications WHERE id=?", (sid,)).fetchone():
                c.execute("INSERT OR IGNORE INTO reads VALUES(?,?)", (user_id, sid))
