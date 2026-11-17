"""dukafetch command line.

    dukafetch candles XAUUSD 2025-01-01 2025-02-01 --sides BID ASK --out data
    dukafetch ticks   EURUSD 2025-01-06 2025-01-07 --out data
    dukafetch export  XAUUSD --kind candles --side BID --out data --csv xauusd_m1.csv --expect 2650
"""
import argparse

from dukafetch.divisors import divisor as known_divisor
from dukafetch.divisors import sanity_check
from dukafetch.download import download_candles, download_ticks
from dukafetch.store import load_candles, load_ticks


def main(argv=None):
    p = argparse.ArgumentParser(prog="dukafetch", description="Dukascopy historical data: download, decode, export")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("candles", "ticks"):
        s = sub.add_parser(name, help=f"download {name} for [start, end)")
        s.add_argument("symbol")
        s.add_argument("start")
        s.add_argument("end")
        s.add_argument("--out", default="data")
        s.add_argument("--workers", type=int, default=2)
        if name == "candles":
            s.add_argument("--sides", nargs="+", default=["BID"], choices=["BID", "ASK"])
    e = sub.add_parser("export", help="decode downloaded files to one CSV")
    e.add_argument("symbol")
    e.add_argument("--kind", choices=["candles", "ticks"], default="candles")
    e.add_argument("--side", default="BID")
    e.add_argument("--out", default="data")
    e.add_argument("--csv", required=True)
    e.add_argument("--divisor", type=float)
    e.add_argument("--expect", type=float, help="a price you know is roughly right: fails loudly on a wrong divisor")
    a = p.parse_args(argv)

    if a.cmd == "candles":
        print(download_candles(a.symbol, a.start, a.end, a.out, tuple(a.sides), a.workers))
    elif a.cmd == "ticks":
        print(download_ticks(a.symbol, a.start, a.end, a.out, a.workers))
    else:
        div = a.divisor or known_divisor(a.symbol)
        df = load_candles(a.out, a.symbol, a.side, div) if a.kind == "candles" else load_ticks(a.out, a.symbol, div)
        if a.expect:
            sanity_check(df["close" if a.kind == "candles" else "bid"], a.expect, tolerance=0.5)
        df.to_csv(a.csv)
        print(f"wrote {len(df):,} rows {df.index[0]} -> {df.index[-1]} to {a.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
