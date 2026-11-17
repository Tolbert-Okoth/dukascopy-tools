"""How much "edge" does a bar backtest invent? A zero-edge experiment on synthetic ticks.

Ticks follow a driftless random walk with a fixed spread, so EVERY bracket strategy has an expected value of exactly
minus the cost. We enter long at random minutes with a symmetric bracket (stop = target distance) and resolve each
trade three ways on 1-minute bars and once on the ticks themselves.

    python examples/bar_vs_tick.py          (~1-2 minutes)
"""
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from dukafetch import ambiguity_report, resolve_on_bars, resolve_on_ticks, ticks_to_bars

OUT = Path(__file__).resolve().parents[1] / "docs"
rng = np.random.default_rng(42)

# 10 trading days of 1 tick per second, gold-like scale: price 2000, M1 range ~ $0.9, spread $0.10
n = 10 * 86_400
idx = pd.date_range("2025-01-06", periods=n, freq="s", tz="UTC")
bid = 2000 + np.cumsum(rng.normal(0, 0.06, n))
ticks = pd.DataFrame(dict(bid=bid, ask=bid + 0.10), index=idx)
bars = ticks_to_bars(ticks, "1min")
m1_range = float((bars.high - bars.low).median())

entries = np.sort(rng.choice(bars.index[:-200], 600, replace=False))
rows = []
for width in (0.25, 0.5, 1.0, 2.0, 4.0):          # bracket distance in units of the median M1 range
    d = width * m1_range
    for t in entries:
        entry = float(ticks.ask.asof(t))           # buy at the ask
        stop, target = entry - d, entry + d
        r_tick, _ = resolve_on_ticks(ticks, t, +1, entry, stop, target)
        row = dict(width=width, R_ticks=r_tick)
        for rule in ("optimistic", "ohlc_path", "pessimistic"):
            row[f"R_{rule}"], _, row["ambiguous"] = resolve_on_bars(bars, t, +1, entry, stop, target, rule)
        rows.append(row)
    print("width", width, "done", flush=True)
T = pd.DataFrame(rows)
T.to_csv(OUT / "bar_vs_tick_trades.csv", index=False)

summary = []
for w, g in T.groupby("width"):
    rep = ambiguity_report(g.rename(columns={"R_ohlc_path": "R_bars"}))
    summary.append(dict(bracket_vs_m1_range=w, trades=rep["trades"], ambiguous_share=rep["ambiguous_share"],
                        R_ticks=g.R_ticks.mean(), R_optimistic=g.R_optimistic.mean(),
                        R_ohlc_path=g.R_ohlc_path.mean(), R_pessimistic=g.R_pessimistic.mean()))
S = pd.DataFrame(summary)
S.round(3).to_csv(OUT / "bar_vs_tick_summary.csv", index=False)
print(f"median M1 range ${m1_range:.2f}")
print(S.round(3).to_string(index=False))

fig, ax = plt.subplots(figsize=(7.5, 4.5))
style = dict(R_ticks=("ticks (truth)", "k", "-"), R_optimistic=("bars, target-first", "#C44E52", "--"),
             R_ohlc_path=("bars, open→near→far path", "#DD8452", "--"), R_pessimistic=("bars, stop-first", "#4C72B0", "--"))
for col, (lab, c, ls) in style.items():
    ax.plot(S.bracket_vs_m1_range, S[col], ls, color=c, marker="o", label=lab, lw=2 if col == "R_ticks" else 1.5)
ax.axhline(0, color="grey", lw=0.8)
ax2 = ax.twinx()
ax2.bar(S.bracket_vs_m1_range, S.ambiguous_share, width=S.bracket_vs_m1_range * 0.25, color="#999", alpha=0.25)
ax2.set_ylabel("share of trades the bars had to guess", color="#777")
ax2.set_ylim(0, 1)
ax.set_xscale("log", base=2)
ax.set_xticks(S.bracket_vs_m1_range)
ax.set_xticklabels([f"{w:g}x" for w in S.bracket_vs_m1_range])
ax.set_xlabel("bracket distance (stop = target) in multiples of the median 1-minute range")
ax.set_ylabel("mean R per trade")
ax.set_title("Zero-edge random walk: the backtest 'edge' is the bar assumption")
ax.legend(fontsize=8, loc="upper right")
ax.set_zorder(ax2.get_zorder() + 1)
ax.patch.set_visible(False)
fig.tight_layout()
fig.savefig(OUT / "bar_vs_tick.png", dpi=150)
