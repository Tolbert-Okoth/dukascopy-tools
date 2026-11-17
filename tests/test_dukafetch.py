import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from dukafetch import (
    decode_candles, decode_ticks, divisor, load_candles, resolve_on_bars, resolve_on_ticks, sanity_check, ticks_to_bars,
)
from dukafetch.decode import CANDLE, TICK, encode
from dukafetch.download import Fetcher, candle_path, candle_url, download_candles, tick_url


class DecodeTest(unittest.TestCase):
    def test_tick_roundtrip_and_field_order(self):
        raw = encode([(250, 2_000_500, 2_000_300, 1.5, 2.5), (1_250, 2_000_600, 2_000_400, 1.0, 1.0)], TICK)
        t = decode_ticks(raw, "2025-01-02 13:00", 1_000)
        self.assertEqual(str(t.index[0]), "2025-01-02 13:00:00.250000+00:00")
        self.assertEqual(t.bid.iloc[0], 2000.3)
        self.assertEqual(t.ask.iloc[0], 2000.5)
        self.assertTrue((t.ask >= t.bid).all())

    def test_candle_order_is_open_close_low_high(self):
        raw = encode([(60, 100_000, 101_000, 99_000, 102_000, 3.0)], CANDLE)
        c = decode_candles(raw, "2025-01-02", 1_000)
        self.assertEqual(c.iloc[0][["open", "high", "low", "close"]].tolist(), [100.0, 102.0, 99.0, 101.0])
        self.assertEqual(str(c.index[0]), "2025-01-02 00:01:00+00:00")

    def test_flat_zero_volume_padding_dropped(self):
        raw = encode([(0, 1, 1, 1, 1, 0.0), (60, 1, 2, 1, 2, 4.0)], CANDLE)
        self.assertEqual(len(decode_candles(raw, "2025-01-02", 1)), 1)
        self.assertEqual(len(decode_candles(raw, "2025-01-02", 1, drop_flat_zero_volume=False)), 2)

    def test_empty_file_is_empty_frame(self):
        self.assertTrue(decode_ticks(b"", "2025-01-02", 1000).empty)

    def test_divisors_and_sanity(self):
        self.assertEqual(divisor("xauusd"), 1000)
        self.assertEqual(divisor("CADJPY"), 1000)
        with self.assertRaises(KeyError):
            divisor("NOPE")
        with self.assertRaises(ValueError):
            sanity_check([2.0, 2.1], expected=2050)     # off by 1000x


class DownloadTest(unittest.TestCase):
    def test_url_month_is_zero_based(self):
        self.assertTrue(candle_url("xauusd", pd.Timestamp("2025-01-31")).endswith("/XAUUSD/2025/00/31/BID_candles_min_1.bi5"))
        self.assertTrue(tick_url("EURUSD", pd.Timestamp("2025-12-01 07:00")).endswith("/2025/11/01/07h_ticks.bi5"))

    def test_resume_404_and_throttle(self):
        calls = []

        class Resp:
            def __init__(self, code, content=b""):
                self.status_code, self.content = code, content

            def raise_for_status(self):
                pass

        class FakeSession:
            headers = {}

            def get(self, url, timeout):
                calls.append(url)
                if url.endswith("/02/BID_candles_min_1.bi5") and calls.count(url) == 1:
                    return Resp(503)                      # throttled once
                if url.endswith("/03/BID_candles_min_1.bi5"):
                    return Resp(404)                      # no data that day
                return Resp(200, encode([(0, 1, 1, 1, 1, 1.0)], CANDLE))

        with tempfile.TemporaryDirectory() as d:
            f = Fetcher(rate=1000, max_rate=1000, session_factory=FakeSession)
            import dukafetch.download as dl
            sleep, dl.time.sleep = dl.time.sleep, (lambda s: None)
            try:
                st = download_candles("XAUUSD", "2025-03-02", "2025-03-04", d, workers=1, fetcher=f)
                self.assertEqual((st["new"], st["empty"], st["failed"]), (2, 1, 0))
                self.assertLess(f.rate, 1000)            # backed off after the 503
                n = len(calls)
                download_candles("XAUUSD", "2025-03-02", "2025-03-04", d, workers=1, fetcher=f)
                self.assertEqual(len(calls), n)          # resumed: nothing re-requested
            finally:
                dl.time.sleep = sleep
            self.assertEqual(candle_path(d, "XAUUSD", pd.Timestamp("2025-03-03")).stat().st_size, 0)
            self.assertEqual(len(load_candles(d, "XAUUSD", divisor=1)), 1)
            self.assertFalse(list(Path(d).rglob("*.part")))


class BracketTest(unittest.TestCase):
    def setUp(self):
        idx = pd.date_range("2025-01-02 10:00", periods=4, freq="s", tz="UTC")
        # bid path: down to 99 first, then up to 102 -> a long bracket at 100 (stop 99, target 101) is STOPPED
        self.ticks = pd.DataFrame(dict(bid=[100, 99, 101, 102.0], ask=[100.1, 99.1, 101.1, 102.1]), index=idx)
        self.bars = ticks_to_bars(self.ticks, "1min")

    def test_ticks_know_the_order(self):
        r, _ = resolve_on_ticks(self.ticks, self.ticks.index[0], +1, 100, 99, 101)
        self.assertEqual(r, -1.0)

    def test_bars_must_guess(self):
        args = (self.bars, self.bars.index[0], +1, 100, 99, 101)
        self.assertEqual(resolve_on_bars(*args, rule="optimistic"), (1.0, self.bars.index[0], True))
        self.assertEqual(resolve_on_bars(*args, rule="pessimistic")[0], -1.0)

    def test_short_side_and_unresolved(self):
        r, _ = resolve_on_ticks(self.ticks, self.ticks.index[0], -1, 100, 103, 99)   # ask touches 99.1, not 99
        self.assertTrue(np.isnan(r))
        r, _ = resolve_on_ticks(self.ticks, self.ticks.index[0], -1, 100, 103, 99.5)
        self.assertEqual(r, 0.5 / 3)


if __name__ == "__main__":
    unittest.main()
