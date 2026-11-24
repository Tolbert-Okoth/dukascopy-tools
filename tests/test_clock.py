import unittest

import numpy as np
import pandas as pd

from dukafetch import detect_clock_offset, nfp_times_utc


def synthetic_minutes(start="2023-01-01", end="2024-12-31", shift_h=0, seed=0):
    idx = pd.date_range(start, end, freq="1min"); idx = idx[idx.dayofweek < 5]
    r = np.random.default_rng(seed).normal(0, 1e-4, len(idx))
    for ev in nfp_times_utc(start, end):                       # volatility burst in the 5 minutes after each release
        m = (idx >= ev) & (idx < ev + pd.Timedelta(minutes=5)); r[m] *= 8
    return pd.Series(100 * np.exp(np.cumsum(r)), index=idx + pd.Timedelta(hours=shift_h))


class ClockTest(unittest.TestCase):
    def test_nfp_dates_are_first_fridays_in_utc(self):
        t = nfp_times_utc("2024-01-01", "2024-12-31")
        self.assertEqual(len(t), 12); self.assertTrue((t.dayofweek == 4).all()); self.assertTrue((t.day <= 7).all())
        self.assertEqual(str(t[0]), "2024-01-05 13:30:00")       # EST: 08:30 NY = 13:30 UTC
        self.assertEqual(str(t[6]), "2024-07-05 12:30:00")       # EDT: 08:30 NY = 12:30 UTC

    def test_detects_utc_and_shifted_files(self):
        ev = nfp_times_utc("2023-01-01", "2024-12-31")
        for shift in (0, 2, 7):
            best, tab = detect_clock_offset(synthetic_minutes(shift_h=shift), ev, offsets_hours=range(-3, 10))
            self.assertEqual(best, shift); self.assertGreater(tab.burst_ratio[shift], 3 * tab.drop(shift).burst_ratio.max())

    def test_tz_aware_index_accepted(self):
        p = synthetic_minutes("2024-01-01", "2024-06-30"); p.index = p.index.tz_localize("UTC")
        best, _ = detect_clock_offset(p, nfp_times_utc("2024-01-01", "2024-06-30"), offsets_hours=range(-2, 3))
        self.assertEqual(best, 0)


if __name__ == "__main__":
    unittest.main()
