"""Assemble downloaded raw files into one tidy DataFrame."""
from pathlib import Path

import pandas as pd

from dukafetch.decode import decode_candles, decode_ticks
from dukafetch.divisors import divisor as known_divisor


def load_candles(out_dir, symbol, side="BID", divisor=None, start=None, end=None):
    """All downloaded daily M1 files for one symbol and side -> one UTC-indexed OHLCV frame."""
    div = divisor or known_divisor(symbol)
    root = Path(out_dir) / symbol.upper() / f"{side.upper()}_m1"
    parts = []
    for f in sorted(root.glob("*/*.bi5")):
        day = pd.Timestamp(f"{f.parent.name}-{f.stem}")
        if (start and day < pd.Timestamp(start)) or (end and day >= pd.Timestamp(end)):
            continue
        parts.append(decode_candles(f.read_bytes(), day, div))
    if not parts:
        raise FileNotFoundError(f"no candle files under {root}")
    return pd.concat(parts).sort_index()


def load_ticks(out_dir, symbol, divisor=None, start=None, end=None):
    """All downloaded hourly tick files for one symbol -> one UTC-indexed bid/ask frame."""
    div = divisor or known_divisor(symbol)
    root = Path(out_dir) / symbol.upper() / "ticks"
    parts = []
    for f in sorted(root.glob("*/*.bi5")):
        md, hh = f.stem.split("_")
        hour = pd.Timestamp(f"{f.parent.name}-{md} {hh[:2]}:00")
        if (start and hour < pd.Timestamp(start)) or (end and hour >= pd.Timestamp(end)):
            continue
        parts.append(decode_ticks(f.read_bytes(), hour, div))
    if not parts:
        raise FileNotFoundError(f"no tick files under {root}")
    return pd.concat(parts).sort_index()


def ticks_to_bars(ticks, freq="1min", price="bid"):
    """OHLC bars from ticks (bars with no ticks are dropped, not forward-filled)."""
    o = ticks[price].resample(freq, label="left", closed="left").ohlc().dropna()
    o["ticks"] = ticks[price].resample(freq, label="left", closed="left").count()
    return o
