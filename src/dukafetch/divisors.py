"""Point divisors: integer price in the file / divisor = price.

A wrong divisor gives prices off by 10x-1000x, which is easy to miss in ratios and returns but breaks
anything in price units (costs, stops, levels). Always run `sanity_check` against a price you know.
"""
KNOWN = {
    # verified against broker / exchange prices in the source project
    "XAUUSD": 1_000,
    "USDJPY": 1_000,
    "BTCUSD": 10,
    "CHEIDXCHF": 1_000,   # SMI index CFD
    "NLDIDXEUR": 1_000,   # AEX index CFD
    "USA500IDXUSD": 1_000,
    # Dukascopy convention, not independently verified here
    "EURUSD": 100_000,
    "GBPUSD": 100_000,
}


def divisor(symbol):
    s = symbol.upper()
    if s in KNOWN:
        return KNOWN[s]
    if s.endswith("JPY"):
        return 1_000
    raise KeyError(f"no known divisor for {symbol}: pass divisor= explicitly and sanity_check() it")


def sanity_check(prices, expected, tolerance=0.10):
    """Raise if the median price is not within `tolerance` (fraction) of a price you know was roughly right."""
    import numpy as np

    med = float(np.median(np.asarray(prices, float)))
    if not abs(med / expected - 1) <= tolerance:
        ratio = med / expected
        raise ValueError(f"median price {med:g} vs expected {expected:g} (ratio {ratio:.3g}): wrong divisor?")
    return med
