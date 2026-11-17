"""Polite, resumable downloader for Dukascopy's public historical datafeed.

Layout written to `out_dir` (raw files are never modified after download):
    <SYMBOL>/ticks/<YYYY>/<MM>-<DD>_<HH>h.bi5
    <SYMBOL>/<SIDE>_m1/<YYYY>/<MM>-<DD>.bi5
Hours or days without data are stored as 0-byte files, so a re-run skips them.

Be polite: the feed throttles aggressive clients (429/503). The defaults use 2 workers, an adaptive delay that halves
the request rate on throttling, and atomic .part -> final renames so an interrupted run never leaves a corrupt file.
Check Dukascopy's terms of use before redistributing any data.
"""
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

BASE = "http://datafeed.dukascopy.com/datafeed/{sym}/{y:04d}/{m0:02d}/{d:02d}/"   # month is ZERO-based in the URL
USER_AGENT = "dukafetch/0.1 (+https://github.com)"


def tick_url(symbol, hour):
    return BASE.format(sym=symbol.upper(), y=hour.year, m0=hour.month - 1, d=hour.day) + f"{hour.hour:02d}h_ticks.bi5"


def candle_url(symbol, day, side="BID"):
    return BASE.format(sym=symbol.upper(), y=day.year, m0=day.month - 1, d=day.day) + f"{side.upper()}_candles_min_1.bi5"


def tick_path(out_dir, symbol, hour):
    return Path(out_dir) / symbol.upper() / "ticks" / f"{hour.year:04d}" / f"{hour.month:02d}-{hour.day:02d}_{hour.hour:02d}h.bi5"


def candle_path(out_dir, symbol, day, side="BID"):
    return Path(out_dir) / symbol.upper() / f"{side.upper()}_m1" / f"{day.year:04d}" / f"{day.month:02d}-{day.day:02d}.bi5"


class Fetcher:
    def __init__(self, rate=1.0, max_rate=2.0, retries=10, timeout=(20, 120), session_factory=None):
        import requests

        self._requests = requests
        self.rate, self.max_rate, self.retries, self.timeout = rate, max_rate, retries, timeout
        self.lock = threading.Lock()
        self.local = threading.local()
        self.session_factory = session_factory or requests.Session
        self.stats = dict(new=0, empty=0, bytes=0, failed=0)

    def _session(self):
        if not hasattr(self.local, "s"):
            self.local.s = self.session_factory()
            self.local.s.headers["User-Agent"] = USER_AGENT
        return self.local.s

    def get(self, url):
        for k in range(self.retries):
            time.sleep(1.0 / self.rate)
            try:
                r = self._session().get(url, timeout=self.timeout)
            except self._requests.exceptions.RequestException:
                time.sleep(5 * (k + 1))
                continue
            if r.status_code == 404:
                return b""
            if r.status_code in (408, 429) or r.status_code >= 500:
                with self.lock:
                    self.rate = max(0.1, self.rate / 2)     # back off for everyone
                time.sleep(min(60, 10 * (k + 1)))
                continue
            r.raise_for_status()
            with self.lock:
                self.rate = min(self.max_rate, self.rate * 1.02)   # creep back up slowly
            return r.content
        raise RuntimeError(f"giving up on {url}")

    def save(self, url, dst):
        dst = Path(dst)
        if dst.exists():
            return False
        try:
            data = self.get(url)
        except Exception as e:  # noqa: BLE001 - one failed file must not stop the batch
            with self.lock:
                self.stats["failed"] += 1
            print("FAIL", url, e, flush=True)
            return False
        dst.parent.mkdir(parents=True, exist_ok=True)
        part = dst.with_name(dst.name + f".{os.getpid()}.{threading.get_ident()}.part")   # unique per worker
        part.write_bytes(data)
        os.replace(part, dst)
        with self.lock:
            self.stats["new"] += 1
            self.stats["empty"] += len(data) == 0
            self.stats["bytes"] += len(data)
        return True


def _run(jobs, fetcher, workers):
    if workers > 3:
        raise ValueError("please keep workers <= 3: the feed throttles harder clients")
    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(lambda j: fetcher.save(*j), jobs))
    return fetcher.stats


def download_ticks(symbol, start, end, out_dir="data", workers=2, skip_saturday=True, fetcher=None):
    """Hourly tick files for [start, end), newest first (the most recent data is usually what you need first)."""
    hours = pd.date_range(pd.Timestamp(start), pd.Timestamp(end) - pd.Timedelta(hours=1), freq="h")
    if skip_saturday:
        hours = [h for h in hours if h.dayofweek != 5]
    jobs = [(tick_url(symbol, h), tick_path(out_dir, symbol, h)) for h in reversed(list(hours))]
    return _run(jobs, fetcher or Fetcher(), workers)


def download_candles(symbol, start, end, out_dir="data", sides=("BID",), workers=2, fetcher=None):
    """Daily 1-minute candle files for [start, end); one file per day and side (BID / ASK)."""
    days = [d for d in pd.date_range(pd.Timestamp(start), pd.Timestamp(end) - pd.Timedelta(days=1), freq="D") if d.dayofweek != 5]
    jobs = [(candle_url(symbol, d, s), candle_path(out_dir, symbol, d, s)) for d in reversed(days) for s in sides]
    return _run(jobs, fetcher or Fetcher(), workers)
