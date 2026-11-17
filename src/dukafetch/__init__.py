"""Download, decode and sanity-check Dukascopy tick and 1-minute data; measure how much a bar backtest guesses."""
from dukafetch.brackets import ambiguity_report, resolve_on_bars, resolve_on_ticks
from dukafetch.decode import decode_candles, decode_ticks
from dukafetch.divisors import divisor, sanity_check
from dukafetch.download import download_candles, download_ticks
from dukafetch.store import load_candles, load_ticks, ticks_to_bars

__version__ = "0.1.0"
__all__ = ["ambiguity_report", "decode_candles", "decode_ticks", "divisor", "download_candles", "download_ticks",
           "load_candles", "load_ticks", "resolve_on_bars", "resolve_on_ticks", "sanity_check", "ticks_to_bars"]
