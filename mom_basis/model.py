from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SIGNAL_NAME = "Signal_GFIVIP_4h"
COINS = ("BTC", "ETH", "SOL", "ZEC", "BNB", "XRP", "NEAR", "DOGE", "UNI", "SUI",
         "ENA", "LINK", "AVAX", "ADA", "BCH", "FIL", "LTC", "DOT", "ARB", "AAVE")
BAR = 900_000
HOLD = 16
WINDOW = 672
MIN_PERIODS = 168
LIVE_WARMUP = WINDOW + HOLD + 1  # also preserves the preceding active state
INITIAL = 10_000.0
BUDGET = 500.0
COST = 0.001  # ALL-IN total both sides; do not add a second slippage deduction
MODEL_ID = "mom16_basis_L_q01_w672_min168_h16_fixed500_v1"
SPEC = dict(model_id=MODEL_ID, coins=COINS, bar_ms=BAR, hold_bars=HOLD,
            window=WINDOW, min_periods=MIN_PERIODS, quantile=0.01,
            initial_usdt=INITIAL, order_budget_usdt=BUDGET, cost_bps=10,
            direction="LONG", overlap="blocked within coin, allowed across coins",
            entry="next 15m open reference", exit="open exactly 4h after entry",
            basis="Binance USD-M premiumIndexKlines close, dimensionless",
            stop_loss=None, take_profit=None, dca=False)
SPEC_HASH = hashlib.sha256(json.dumps(SPEC, sort_keys=True).encode()).hexdigest()
SPEC["signal_name"] = SIGNAL_NAME  # display name does not change strategy identity or historical IDs


def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [clean(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def encode(value):
    return json.dumps(clean(value), ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def features(frame: pd.DataFrame) -> pd.DataFrame:
    """Exact original trailing quantiles, including the current CLOSED candle."""
    d = frame.reset_index(drop=True)
    m = d.close.pct_change(HOLD, fill_method=None)
    result = pd.DataFrame({"mom16": m, "basis": d.basis})
    active = pd.Series(True, index=d.index)
    for name, series in (("mom", m), ("basis", d.basis)):
        q1 = series.rolling(WINDOW, min_periods=MIN_PERIODS).quantile(1 - .99)
        q99 = series.rolling(WINDOW, min_periods=MIN_PERIODS).quantile(.99)
        result[name + "_q01"] = q1
        active &= (series <= q1) & (q99 > q1) & series.notna()
    result["active"] = active
    result["onset"] = active & ~active.shift(1, fill_value=False)
    return result


def signal_id(coin, entry_ms):
    return hashlib.sha256(f"{MODEL_ID}:{coin}:{entry_ms}".encode()).hexdigest()[:24]


def pnl(entry_price, exit_price):
    n = BUDGET / (1 + COST / 2)
    gross = n * (exit_price / entry_price - 1)
    return dict(order_budget=BUDGET, gross_notional=n, quantity=n / entry_price,
                gross_pnl=gross, total_cost=n * COST, net_pnl=gross - n * COST,
                gross_return=exit_price / entry_price - 1,
                net_return=exit_price / entry_price - 1 - COST)


def forecast(paths, coin, entry_ms, entry_price):
    """Freeze a historical conditional mean; only fully matured paths are eligible."""
    mature = [p for p in paths if p["exit_ms"] <= entry_ms and len(p["returns"]) == HOLD + 1]
    own = [p for p in mature if p["coin"] == coin]
    cohort, scope = (own, "same_coin") if len(own) >= 5 else (mature, "pooled_top20")
    base = dict(method="historical_conditional_mean_v1", scope=scope,
                sample_count=len(cohort), as_of_ms=entry_ms,
                latest_training_exit_ms=max((p["exit_ms"] for p in cohort), default=None),
                frozen=True, interval="pointwise empirical p10-p90; not a confidence interval",
                stop_loss=None, take_profit=None, risk_reward=None)
    if not cohort:
        return dict(base, available=False, points=[], p_up=None, mean_4h=None)
    a = np.asarray([p["returns"] for p in cohort], dtype=float)
    mean = a.mean(axis=0)
    lo, hi = np.quantile(a, [.1, .9], axis=0)
    return clean(dict(base, available=True, p_up=(a[:, -1] > 0).mean(), mean_4h=mean[-1],
        points=[dict(time_ms=entry_ms + k * BAR, mean_price=entry_price * (1 + mean[k]),
                     p10_price=entry_price * (1 + lo[k]), p90_price=entry_price * (1 + hi[k]))
                for k in range(HOLD + 1)]))


def statistics(trades, equity, initial=INITIAL):
    """Closed trades for WR/settled PnL; 15m open MTM for drawdown/daily Sharpe."""
    done = [t for t in trades if t.get("exit_price") is not None]
    net = np.array([t["net_pnl"] for t in done], dtype=float)
    gross = np.array([t["gross_pnl"] for t in done], dtype=float)
    values = np.r_[initial, [r["equity"] for r in equity]]
    dd = values / np.maximum.accumulate(values) - 1
    # Calendar gaps between the original backtest and forward deployment are NOT zero returns.
    daily = []
    if equity:
        d = pd.DataFrame(equity)
        for _, group in d.groupby(d.get("segment", pd.Series("reference", index=d.index))):
            s = pd.Series(group.equity.to_numpy(), index=pd.to_datetime(group.time_ms, unit="ms", utc=True))
            daily_close = s.sort_index().resample("1D").last().dropna()
            # Only consecutive fully observed UTC days (00:00 through 23:45).
            counts = s.resample("1D").count()
            complete = counts[counts >= 96].index
            ret = daily_close.pct_change(fill_method=None)
            for day in complete:
                if day - pd.Timedelta(days=1) in complete and pd.notna(ret.loc[day]):
                    daily.append(float(ret.loc[day]))
    sd = np.std(daily, ddof=1) if len(daily) > 1 else 0
    loss = -net[net < 0].sum()
    return clean(dict(n_trades=len(done), open_trades=len(trades) - len(done),
        gross_wins=int((gross > 0).sum()), net_wins=int((net > 0).sum()),
        gross_winrate=float((gross > 0).mean()) if len(done) else None,
        net_winrate=float((net > 0).mean()) if len(done) else None,
        gross_pnl=float(gross.sum()), total_cost=sum(t["total_cost"] for t in done),
        net_pnl=float(net.sum()), net_profit=float(net.sum() / initial),
        settled_equity=initial + float(net.sum()),
        max_drawdown=float(dd.min()),
        profit_factor=float(net[net > 0].sum() / loss) if loss else None,
        sharpe_ratio=float(np.mean(daily) / sd * np.sqrt(365)) if sd > 0 else None,
        sharpe_observed_daily_returns=len(daily),
        sharpe_definition="UTC daily 15m-open MTM, sqrt(365), zero risk-free, no unobserved gap returns",
        initial_usdt=initial, order_budget_usdt=BUDGET, cost_bps=10,
        equity_basis="15m open mark-to-market", pnl_basis="closed-trade net PnL / initial capital"))
