"""One-time export from the owner's verified local research. No API or fake data."""
from pathlib import Path
import hashlib
import json
import shutil
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mom_basis.model import BAR, BUDGET, COINS, HOLD, MODEL_ID, SPEC_HASH, encode, forecast, signal_id


def main():
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent
    original = source/"mom16_basis_top20_180d_500usdt_results"
    baseline = ROOT/"data"/"baseline"
    ref = ROOT/"data"/"reference180"
    meta = json.loads((original/"metadata.json").read_text(encoding="utf-8"))
    start = int(pd.Timestamp(meta["start"]).value//1_000_000)
    end = int(pd.Timestamp(meta["last_mark"]).value//1_000_000)
    t = pd.read_csv(original/"trades.csv")
    exports, candles, coins = [], {}, {}
    for name in ("summary.csv", "per_coin.csv", "trades.csv", "metadata.json", "equity_15m.csv", "signal_decisions.csv", "terminal_results.txt"):
        shutil.copy2(original/name, baseline/name)
    for coin in COINS:
        path = source/"binance_top20_15m_2022_now"/"datasets"/(coin+"USDT_15m.csv")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == next(r["sha256"] for r in meta["sources"] if r["coin"] == coin)
        d = pd.read_csv(path, usecols=["timestamp_ms", "open", "high", "low", "close", "basis"])
        d = d[d.timestamp_ms.between(start, end)].reset_index(drop=True)
        assert np.array_equal(d.timestamp_ms.to_numpy(), np.arange(start, end+BAR, BAR))
        dest = ref/(coin+"USDT_15m.csv.gz")
        d.to_csv(dest, index=False, compression="gzip")
        exports.append(dict(coin=coin, file=dest.name, rows=len(d), source_sha256=digest,
            export_sha256=hashlib.sha256(dest.read_bytes()).hexdigest()))
        candles[coin] = d
    paths, trades = [], []
    for row in t.to_dict("records"):
        coin = row["coin"]
        d = candles[coin]
        sid = signal_id(coin, int(row["entry_ms"]))
        actual = [dict(time_ms=int(r.timestamp_ms), price=float(r.open))
            for r in d[d.timestamp_ms.between(row["entry_ms"], row["exit_ms"])].itertuples()]
        assert len(actual) == HOLD+1
        path = dict(id=sid, coin=coin, exit_ms=int(row["exit_ms"]),
            returns=[p["price"]/row["entry_price"]-1 for p in actual])
        fp = forecast(paths, coin, int(row["entry_ms"]), row["entry_price"])
        history = [dict(time_ms=int(r.timestamp_ms)+BAR, price=float(r.close))
            for r in d[d.timestamp_ms < row["entry_ms"]].tail(32).itertuples()]
        trades.append(dict(row, id=sid, model_id=MODEL_ID, symbol=coin+"USDT", direction="LONG", origin="backtest",
            forecast=fp, history=history, actual_path=actual, settlement="SETTLED",
            features={k:row[k] for k in ("mom16", "mom_q01", "basis", "basis_q01")},
            detected_ms=int(row["entry_ms"]), stop_loss=None, take_profit=None,
            entry_reference="Historical next 15m open, 10 bps modeled total costs"))
        paths.append(path)
    summary = pd.read_csv(original/"summary.csv").iloc[0].to_dict()
    for coin in COINS:
        d = candles[coin]
        realized = np.zeros(len(d)); floating = np.zeros(len(d))
        for r in t[t.coin == coin].itertuples():
            en, ex = int(r.entry_index), int(r.exit_index)
            realized[ex] += r.net_pnl
            floating[en:ex] += r.quantity*d.open.to_numpy()[en:ex]-BUDGET
        curve = BUDGET+np.cumsum(realized)+floating
        coins[coin] = [dict(time_ms=int(ts), equity=float(eq), segment="reference") for ts, eq in zip(d.timestamp_ms, curve)]
    (baseline/"coin_equity.json").write_text(encode(coins), encoding="utf-8")
    (baseline/"seed.json").write_text(encode(dict(trades=trades, paths=paths, final_cash=summary["final_equity"],
        metadata=dict(start_ms=start, end_ms=end, source="real local Binance USD-M data", n_trades=241,
            period="2026-04-25 16:15 to 2026-10-22 13:00 UTC (~180d)",
            initial_usdt=10000, spec_hash=SPEC_HASH, gap_policy="Reference comparison snapshot; v1.1 reconstructs all subsequent bars continuously"))), encoding="utf-8")
    (ref/"manifest.json").write_text(encode(dict(start_ms=start, end_ms=end, datasets=exports)), encoding="utf-8")
    provenance = ROOT/"data"/"provenance"
    provenance.mkdir(exist_ok=True)
    for name in ("backtest_mom16_basis_top20_180d_500usdt.py", "backtest_mom16_basis_local_10bps.py", "bao_cao_mom16_basis_top20_180ngay_500usdt.md"):
        shutil.copy2(source/name, provenance/name)
    print(encode(dict(exported_coins=len(exports), trades=len(trades), path_count=len(paths), summary=summary)))


if __name__ == "__main__":
    main()
