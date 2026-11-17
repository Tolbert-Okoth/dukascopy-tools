"""Decode Dukascopy .bi5 files (LZMA-compressed, big-endian fixed-width records).

Tick file, one per UTC hour, 20-byte records:
    uint32 ms since the hour | uint32 ask | uint32 bid | float32 ask volume | float32 bid volume
Minute-candle file, one per UTC day and side (BID or ASK), 24-byte records:
    int32 s since midnight | int32 open | int32 close | int32 low | int32 high | float32 volume
Note the candle order: open, CLOSE, low, high (not OHLC).

Prices are integers that must be divided by an instrument-specific point divisor (see divisors.py).
"""
import lzma

import numpy as np
import pandas as pd

TICK = np.dtype([("ms", ">u4"), ("ask", ">u4"), ("bid", ">u4"), ("ask_vol", ">f4"), ("bid_vol", ">f4")])
CANDLE = np.dtype([("s", ">i4"), ("open", ">i4"), ("close", ">i4"), ("low", ">i4"), ("high", ">i4"), ("volume", ">f4")])


def _records(raw, dtype):
    if not raw:                       # Dukascopy returns 404 / empty for hours or days without data
        return np.zeros(0, dtype)
    buf = lzma.decompress(raw)
    if len(buf) % dtype.itemsize:
        raise ValueError(f"payload length {len(buf)} is not a multiple of {dtype.itemsize}-byte records")
    return np.frombuffer(buf, dtype)


def decode_ticks(raw, hour_start, divisor):
    """bytes of one hourly *_ticks.bi5 -> DataFrame indexed by UTC time with bid, ask, bid_vol, ask_vol."""
    a = _records(raw, TICK)
    t0 = pd.Timestamp(hour_start)
    if t0.tzinfo is None:
        t0 = t0.tz_localize("UTC")
    idx = t0 + pd.to_timedelta(a["ms"].astype(np.int64), unit="ms")
    return pd.DataFrame({"bid": a["bid"] / divisor, "ask": a["ask"] / divisor,
                         "bid_vol": a["bid_vol"].astype(float), "ask_vol": a["ask_vol"].astype(float)},
                        index=pd.DatetimeIndex(idx, name="time"))


def decode_candles(raw, day, divisor, drop_flat_zero_volume=True):
    """bytes of one daily *_candles_min_1.bi5 -> OHLCV DataFrame indexed by UTC bar-open time.

    Dukascopy pads closed-market minutes with flat, zero-volume candles. They look like real prices
    (and silently flatten volatility, returns and session statistics), so they are dropped by default.
    """
    a = _records(raw, CANDLE)
    if drop_flat_zero_volume:
        a = a[a["volume"] > 0]
    t0 = pd.Timestamp(day).normalize()
    if t0.tzinfo is None:
        t0 = t0.tz_localize("UTC")
    idx = t0 + pd.to_timedelta(a["s"].astype(np.int64), unit="s")
    out = pd.DataFrame({k: a[k] / divisor for k in ("open", "high", "low", "close")}, index=pd.DatetimeIndex(idx, name="time"))
    out["volume"] = a["volume"].astype(float)
    return out


def encode(records, dtype):
    """Inverse of decoding (used by the tests and for building fixtures)."""
    return lzma.compress(np.asarray(records, dtype).tobytes(), format=lzma.FORMAT_ALONE)
