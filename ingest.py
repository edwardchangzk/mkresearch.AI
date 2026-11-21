"""Fetch prices from Yahoo Finance (via yfinance) and store them in SQLite.

Run `python ingest.py` to refresh every ticker on the watchlist (also usable from cron).
yfinance is unofficial: fine for learning, but it can break or rate-limit without notice.
"""
import time

import pandas as pd
import yfinance as yf

import db

COLUMNS = {
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Adj Close": "adj_close",
    "Volume": "volume",
}


def fetch_history(ticker: str, start: pd.Timestamp | None = None) -> pd.DataFrame:
    kwargs = {"auto_adjust": False, "actions": False}
    if start is not None:
        kwargs["start"] = start.strftime("%Y-%m-%d")
    else:
        kwargs["period"] = "max"
    raw = yf.Ticker(ticker).history(**kwargs)
    if raw.empty:
        return raw

    if "Adj Close" not in raw.columns:  # some instruments have no adjusted close
        raw["Adj Close"] = raw["Close"]
    df = raw[list(COLUMNS)].rename(columns=COLUMNS)
    df.index = pd.DatetimeIndex(df.index).tz_localize(None).normalize()
    df = df[~df.index.duplicated(keep="last")]
    return df.dropna(subset=["close"])


# Yahoo only keeps short intraday histories: ~7 days of 1-minute, ~60 days of 5-minute,
# ~2 years of 1-hour bars. Anything finer than daily is therefore fetched on demand.
INTRADAY = {
    "1m": ("1m", {"period": "7d"}),
    "5m": ("5m", {"period": "60d"}),
    "1h": ("1h", {"days": 720}),
}


def fetch_intraday(ticker: str, key: str, since=None) -> pd.DataFrame:
    """Intraday bars in exchange-local wall-clock time (timezone info removed).
    `since` (optional) limits the download to recent bars; it must be inside Yahoo's lookback window."""
    interval, spec = INTRADAY[key]
    if since is not None:
        kwargs = {"start": pd.Timestamp(since).strftime("%Y-%m-%d")}
    elif "days" in spec:
        start = (pd.Timestamp.now() - pd.Timedelta(days=spec["days"])).strftime("%Y-%m-%d")
        kwargs = {"start": start}
    else:
        kwargs = dict(spec)
    raw = yf.Ticker(ticker).history(interval=interval, auto_adjust=False, actions=False, **kwargs)
    if raw.empty:
        return raw
    df = raw[["Open", "High", "Low", "Close", "Volume"]].rename(columns=str.lower)
    df.index = pd.DatetimeIndex(df.index).tz_localize(None)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df.dropna(subset=["close"])


def update_ticker(ticker: str) -> int:
    """Download new rows for one ticker. Returns number of rows written."""
    last = db.last_date(ticker)
    # Re-fetch a week of overlap so late corrections from the provider overwrite old rows.
    start = last - pd.Timedelta(days=7) if last is not None else None
    df = fetch_history(ticker, start)
    return db.upsert_prices(ticker, df)


def update_context() -> dict[str, int]:
    """Refresh the market-context series (S&P 500, VIX, yields, dollar) used as model features."""
    import universe

    results = {}
    for symbol in universe.CONTEXT:
        try:
            results[symbol] = update_ticker(symbol)
        except Exception as exc:
            print(f"{symbol}: failed ({exc})")
            results[symbol] = -1
    return results


def update_all() -> dict[str, int]:
    results = {}
    for ticker in db.get_watchlist():
        try:
            results[ticker] = update_ticker(ticker)
        except Exception as exc:  # keep going if one ticker fails
            print(f"{ticker}: failed ({exc})")
            results[ticker] = -1
    return results


if __name__ == "__main__":
    db.init_db()
    for t, n in update_all().items():
        print(f"{t}: {n} rows")


def with_retries(fn, *args, attempts: int = 3, delay: float = 8.0):
    """Yahoo sometimes refuses requests from shared servers for a few seconds or minutes; back off and retry."""
    for i in range(attempts):
        try:
            return fn(*args)
        except Exception:
            if i == attempts - 1:
                raise
            time.sleep(delay * (i + 1))
