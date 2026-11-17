"""Resolve stop-loss / take-profit brackets on bars vs on ticks.

On a bar where BOTH the stop and the target lie inside [low, high], OHLC data cannot tell which was hit first.
Backtesters resolve that bar by assumption, and the assumption becomes "edge" when stops and targets are tight:
    optimistic   target first
    pessimistic  stop first
    ohlc_path    open -> nearer extreme -> farther extreme -> close (a common default; still a guess)
Ticks remove the guess. `ambiguity_report` measures how many trades depended on it.
"""
import numpy as np
import pandas as pd

RULES = ("optimistic", "pessimistic", "ohlc_path")


def resolve_on_bars(bars, entry_time, side, entry, stop, target, rule="ohlc_path", max_bars=10_000):
    """Exit of one bracket using only OHLC. Returns (R, exit_time, ambiguous). side: +1 long, -1 short.
    Entry happens at `entry_time` (bar open); the entry bar itself is checked."""
    if rule not in RULES:
        raise ValueError(f"rule must be one of {RULES}")
    risk = abs(entry - stop)
    win_r = abs(target - entry) / risk
    i0 = bars.index.searchsorted(pd.Timestamp(entry_time))
    for i in range(i0, min(i0 + max_bars, len(bars))):
        o, h, l, c = bars.iloc[i][["open", "high", "low", "close"]]
        hit_stop = (l <= stop) if side > 0 else (h >= stop)
        hit_tgt = (h >= target) if side > 0 else (l <= target)
        if hit_stop and hit_tgt:
            if rule == "optimistic":
                first_tgt = True
            elif rule == "pessimistic":
                first_tgt = False
            else:   # open -> nearer extreme first
                high_first = (h - o) < (o - l)
                first_tgt = high_first == (side > 0)
            return (win_r if first_tgt else -1.0), bars.index[i], True
        if hit_stop:
            return -1.0, bars.index[i], False
        if hit_tgt:
            return win_r, bars.index[i], False
    return np.nan, None, False


def resolve_on_ticks(ticks, entry_time, side, entry, stop, target, max_ticks=10_000_000):
    """Exit of one bracket on bid/ask ticks. Long exits on the bid, short exits on the ask. Returns (R, exit_time)."""
    risk = abs(entry - stop)
    win_r = abs(target - entry) / risk
    i0 = ticks.index.searchsorted(pd.Timestamp(entry_time))
    px = (ticks["bid"] if side > 0 else ticks["ask"]).to_numpy()[i0:i0 + max_ticks]
    if side > 0:
        s_hit, t_hit = np.flatnonzero(px <= stop), np.flatnonzero(px >= target)
    else:
        s_hit, t_hit = np.flatnonzero(px >= stop), np.flatnonzero(px <= target)
    s = s_hit[0] if len(s_hit) else np.inf
    t = t_hit[0] if len(t_hit) else np.inf
    if s == t == np.inf:
        return np.nan, None
    k = int(min(s, t))
    return (-1.0 if s <= t else win_r), ticks.index[i0 + k]


def ambiguity_report(results):
    """results: DataFrame with columns R_bars, R_ticks, ambiguous -> summary dict."""
    r = results.dropna(subset=["R_bars", "R_ticks"])
    amb = r[r.ambiguous]
    return dict(trades=len(r), ambiguous_share=float(r.ambiguous.mean()),
                mean_R_bars=float(r.R_bars.mean()), mean_R_ticks=float(r.R_ticks.mean()),
                bar_minus_tick_R=float(r.R_bars.mean() - r.R_ticks.mean()),
                disagreement_on_ambiguous=float((amb.R_bars != amb.R_ticks).mean()) if len(amb) else 0.0)
