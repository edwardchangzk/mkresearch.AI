"""Data job: prices, market context, news, earnings/fundamentals, prediction log, snapshot export.

Cloud use (GitHub Actions runs this every 30 minutes):
    python refresh_job.py --snapshot _data/snapshot --watchlist-file watchlist.txt --predict

Local use (Windows Task Scheduler), updates your local database only:
    python refresh_job.py             prices, market context, news
    python refresh_job.py --predict   also log today's predictions (after the US close)
"""
import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

import db
import ingest
import model
import snapshot
import sources
import universe


def read_watchlist_file(path) -> list[str]:
    lines = Path(path).read_text().splitlines()
    return [ln.split("#")[0].strip().upper() for ln in lines if ln.split("#")[0].strip()]


def sync_watchlist(path):
    wanted = read_watchlist_file(path)
    for t in db.get_watchlist():
        if t not in wanted:
            db.remove_from_watchlist(t)
    for t in wanted:
        db.add_to_watchlist(t)


INTRADAY_KEEP = {"1h": 365, "5m": 30}  # days of hourly and 5-minute bars kept in the snapshot


def refresh_intraday(tickers: list[str]):
    """Best effort: a failure here never stops the rest of the job."""
    ok = 0
    for t in tickers:
        for res, days in INTRADAY_KEEP.items():
            try:
                last = db.last_intraday(t, res)
                floor = pd.Timestamp.now() - pd.Timedelta(days=days)
                since = max(last - pd.Timedelta(days=3), floor) if last is not None else floor
                df = ingest.with_retries(ingest.fetch_intraday, t, res, since, attempts=2, delay=4)
                db.upsert_intraday(t, res, df)
                ok += 1
            except Exception as exc:
                print(f"intraday {t} {res}: failed ({type(exc).__name__})")
            time.sleep(0.5)
    db.prune_intraday(INTRADAY_KEEP)
    print(f"intraday: {ok}/{len(tickers) * len(INTRADAY_KEEP)} downloads ok")


def market_closed(last_bar: pd.Timestamp) -> bool:
    """True once the US session for `last_bar` is over, so a logged prediction never uses a half-finished day."""
    now = pd.Timestamp.now(tz="America/New_York")
    if last_bar.date() < now.date():
        return True
    return now.weekday() < 5 and now.hour * 60 + now.minute >= 16 * 60 + 30


def refresh_extras(snap: Path, tickers: list[str]):
    """Earnings dates and fundamentals change slowly: refresh each ticker at most once a day."""
    path = snap / "extras.json"
    extras = json.loads(path.read_text()) if path.exists() else {}
    for key in ("earnings", "fundamentals", "updated"):
        extras.setdefault(key, {})
    today = pd.Timestamp.now("UTC").strftime("%Y-%m-%d")
    for t in tickers:
        if extras["updated"].get(t) == today:
            continue
        ok = False
        try:
            past, upcoming = sources.fetch_earnings_dates(t)
            extras["earnings"][t] = {"past": [d.strftime("%Y-%m-%d") for d in past],
                                     "next": upcoming.strftime("%Y-%m-%d") if upcoming is not None else None}
            ok = True
        except Exception as exc:
            print(f"earnings {t}: failed ({type(exc).__name__})")
        try:
            extras["fundamentals"][t] = sources.fetch_fundamentals(t)
            ok = True
        except Exception as exc:
            print(f"fundamentals {t}: failed ({type(exc).__name__})")
        if ok:
            extras["updated"][t] = today
        time.sleep(1)
    path.write_text(json.dumps(extras))


def log_predictions(tickers: list[str]):
    context = {s: db.load_prices(s) for s in universe.CONTEXT}
    existing = db.load_predictions()
    have = set()
    if not existing.empty:
        have = set(zip(existing["ticker"], existing["horizon"], existing["target"],
                       existing["made_on"].dt.strftime("%Y-%m-%d")))
    for t in tickers:
        df = db.load_prices(t)
        if df.empty:
            continue
        last = df.index[-1]
        if not market_closed(last):
            print(f"{t}: session still open, not logging")
            continue
        for horizon in (5, 20, 60):
            if (t, horizon, "up", last.strftime("%Y-%m-%d")) in have:
                continue
            outlook = model.run(df, horizon, context, "up", compare=False)
            if outlook:
                db.log_prediction(t, horizon, "up", outlook.as_of.date(), outlook.prob_up, outlook.base_rate,
                                  outlook.verdict)
        print(f"{t}: predictions up to date")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--predict", action="store_true", help="log model predictions (skipped while the market is open)")
    parser.add_argument("--intraday", action="store_true", help="also store recent hourly and 5-minute bars")
    parser.add_argument("--snapshot", help="folder holding the snapshot files (restored first, rewritten at the end)")
    parser.add_argument("--watchlist-file", help="text file with one ticker per line")
    args = parser.parse_args()

    db.init_db()
    snap = Path(args.snapshot) if args.snapshot else None
    if snap and snapshot.load_into_db(str(snap)):
        print("restored previous snapshot")
    if args.watchlist_file:
        sync_watchlist(args.watchlist_file)
    tickers = db.get_watchlist()

    symbols = list(dict.fromkeys(tickers + list(universe.CONTEXT)))  # SPY can be in both lists
    failures = 0
    for symbol in symbols:
        try:
            ingest.with_retries(ingest.update_ticker, symbol)
        except Exception as exc:
            failures += 1
            print(f"prices {symbol}: failed ({type(exc).__name__})")
        time.sleep(0.5)
    if failures == len(symbols):
        sys.exit("Every price download failed (Yahoo may be blocking this server). Snapshot left unchanged.")

    for t in tickers:
        try:
            print(f"news {t}: {ingest.with_retries(sources.refresh_news, t, attempts=2, delay=4)} new")
        except Exception as exc:
            print(f"news {t}: failed ({type(exc).__name__})")
        time.sleep(0.5)

    if args.intraday:
        refresh_intraday(tickers)
    if snap:
        snap.mkdir(parents=True, exist_ok=True)
        refresh_extras(snap, tickers)
    if args.predict:
        log_predictions(tickers)
    if snap:
        meta = snapshot.export(snap)
        print("snapshot written:", meta)


if __name__ == "__main__":
    main()
