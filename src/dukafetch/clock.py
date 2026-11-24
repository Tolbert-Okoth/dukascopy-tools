"""Detect which clock a price file is really on, from the market's own reaction to scheduled news.

Broker and vendor files are often stamped in "server time" (e.g. UTC+2/+3 with DST, or New York +7) rather than UTC, and
the documentation is not always right. Scheduled releases such as US non-farm payrolls (08:30 New York) produce a burst of
volatility in the first minutes. If a file is shifted by h hours, that burst appears h hours after the true UTC release time.
`detect_clock_offset` scores every candidate shift and returns the one where the bursts line up.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def nfp_times_utc(start, end) -> pd.DatetimeIndex:
    """Approximate US employment-report release times in UTC: first Friday of each month, 08:30 America/New_York.
    (A few releases move for holidays or shutdowns; a handful of misses do not change the detected offset.)"""
    months = pd.date_range(pd.Timestamp(start).to_period("M").to_timestamp(), end, freq="MS")
    fridays = [m + pd.Timedelta(days=(4 - m.dayofweek) % 7) for m in months]
    ny = pd.DatetimeIndex([f + pd.Timedelta(hours=8, minutes=30) for f in fridays]).tz_localize("America/New_York")
    out = ny.tz_convert("UTC").tz_localize(None)
    return out[(out >= pd.Timestamp(start)) & (out <= pd.Timestamp(end))]


def detect_clock_offset(prices: pd.Series, events_utc, offsets_hours=range(-12, 13), window_min: int = 5,
                        baseline_min: int = 60) -> tuple[float, pd.DataFrame]:
    """Score each candidate offset h (file time = UTC + h) by the event-window volatility burst.

    score(h) = median over events of  mean |1-min return| in [event+h, event+h+window)  /  mean |1-min return| in the
    preceding `baseline_min` minutes. Returns (best offset in hours, table of scores). A clear winner scores several times
    higher than every other offset; a flat table means the events are not visible in this market or the file is too short."""
    p = prices[~prices.index.duplicated()].sort_index()
    if p.index.tz is not None:                                   # compare wall-clock stamps as written in the file
        p = p.tz_localize(None)
    r = np.log(p).diff().abs()
    r = r.resample("1min").sum(min_count=1)
    rows = []
    for h in offsets_hours:
        ratios = []
        for ev in pd.DatetimeIndex(events_utc):
            t0 = ev + pd.Timedelta(hours=h)
            burst = r.loc[t0: t0 + pd.Timedelta(minutes=window_min - 1)]
            base = r.loc[t0 - pd.Timedelta(minutes=baseline_min): t0 - pd.Timedelta(minutes=1)]
            if burst.count() >= max(2, window_min // 2) and base.count() >= baseline_min // 3 and base.mean() > 0:
                ratios.append(burst.mean() / base.mean())
        rows.append((h, float(np.median(ratios)) if ratios else np.nan, len(ratios)))
    tab = pd.DataFrame(rows, columns=["offset_hours", "burst_ratio", "events_used"]).set_index("offset_hours")
    best = tab.burst_ratio.idxmax() if tab.burst_ratio.notna().any() else np.nan
    return best, tab
