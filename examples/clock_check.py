"""Which clock is this file on? Synthetic demo of detect_clock_offset. Run: python examples/clock_check.py (needs matplotlib)."""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from dukafetch import detect_clock_offset, nfp_times_utc

DOCS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
start, end = "2022-01-01", "2024-12-31"
idx = pd.date_range(start, end, freq="1min"); idx = idx[idx.dayofweek < 5]
rng = np.random.default_rng(1); r = rng.normal(0, 1e-4, len(idx))
for ev in nfp_times_utc(start, end):                                 # releases cause a short volatility burst
    m = (idx >= ev) & (idx < ev + pd.Timedelta(minutes=5)); r[m] *= rng.uniform(3, 10)
prices = pd.Series(100 * np.exp(np.cumsum(r)), index=idx + pd.Timedelta(hours=7))   # file written in "UTC+7 server time"

best, tab = detect_clock_offset(prices, nfp_times_utc(start, end))
print(f"detected offset: UTC{best:+d} h  (burst ratio {tab.burst_ratio[best]:.1f} vs next best {tab.drop(best).burst_ratio.max():.1f})")
fig, ax = plt.subplots(figsize=(7, 3.6))
ax.bar(tab.index, tab.burst_ratio, color=["#2b8a3e" if h == best else "#adb5bd" for h in tab.index])
ax.axhline(1, color="#333", lw=.8); ax.set_xticks(range(-12, 13, 2))
ax.set_xlabel("candidate offset: file time = UTC + h"); ax.set_ylabel("event-window volatility / baseline")
ax.set_title(f"Payroll-release bursts line up only at UTC{best:+d}: the file is not on UTC"); ax.grid(axis="y", alpha=.3)
fig.tight_layout(); fig.savefig(os.path.join(DOCS, "clock_offset.png"), dpi=130); plt.close(fig)
