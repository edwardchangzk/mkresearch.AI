"""The data snapshot: a few CSV/JSON files that act as the database in cloud deployments.

    GitHub Action (data job)  ->  export() writes the files, pushed to the `data` branch
    Streamlit app             ->  sync() downloads them into its local (disposable) SQLite

`base` can be a URL (https://raw.githubusercontent.com/...) or a local folder, which keeps tests simple.
"""
import io
import json
import threading
import time
from pathlib import Path

import pandas as pd
import requests

import db
import universe

PRICE_YEARS = 15  # older history is not needed by the model and keeps the files small


# ---------- reading ----------
def _read_bytes(base, name, token=None):
    base = str(base)
    if base.startswith(("http://", "https://")):
        headers = {"Authorization": f"token {token}"} if token else {}
        response = requests.get(f"{base.rstrip('/')}/{name}", headers=headers, timeout=30)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.content
    path = Path(base) / name
    return path.read_bytes() if path.exists() else None


def read_json(base, name, token=None):
    raw = _read_bytes(base, name, token)
    return json.loads(raw) if raw else None


def _read_csv(base, name, token=None, **kwargs):
    raw = _read_bytes(base, name, token)
    return pd.read_csv(io.BytesIO(raw), **kwargs) if raw else None


def load_into_db(base, token=None) -> bool:
    """Replace the local tables with the snapshot's contents. Returns False if the snapshot has no prices."""
    prices = _read_csv(base, "prices.csv", token, dtype={"ticker": str, "date": str})
    if prices is None or prices.empty:
        return False
    text = {"ticker": str, "url": str, "published": str, "title": str, "publisher": str, "summary": str,
            "fetched_at": str, "made_on": str, "target": str, "verdict": str, "created_at": str, "added_at": str}
    tables = {
        "prices": prices,
        "news": _read_csv(base, "news.csv", token, dtype=text),
        "predictions": _read_csv(base, "predictions.csv", token, dtype=text),
        "watchlist": _read_csv(base, "watchlist.csv", token, dtype=text),
        "intraday": _read_csv(base, "intraday.csv", token, dtype={"ticker": str, "res": str, "ts": str}),
    }
    db.init_db()
    with db.get_conn() as conn:
        for name, frame in tables.items():
            if frame is None or (frame.empty and name != "news"):
                continue
            conn.execute(f"DELETE FROM {name}")
            if not frame.empty:
                frame.to_sql(name, conn, if_exists="append", index=False)
    return True


# ---------- writing (used by the data job) ----------
def export(directory) -> dict:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    cutoff = (pd.Timestamp.now() - pd.DateOffset(years=PRICE_YEARS)).strftime("%Y-%m-%d")
    context = list(universe.CONTEXT)
    marks = ",".join("?" * len(context))
    with db.get_conn() as conn:
        prices = pd.read_sql_query(
            "SELECT ticker, date, open, high, low, close, adj_close, volume FROM prices WHERE date >= ? "
            f"AND (ticker IN (SELECT ticker FROM watchlist) OR ticker IN ({marks})) ORDER BY ticker, date",
            conn, params=[cutoff, *context])
        queries = {
            "news.csv": "SELECT ticker, url, published, title, publisher, summary, sentiment, fetched_at "
                        "FROM news WHERE ticker IN (SELECT ticker FROM watchlist) ORDER BY published",
            "predictions.csv": "SELECT ticker, horizon, target, made_on, prob, base_rate, verdict, created_at "
                               "FROM predictions ORDER BY made_on, ticker",
            "watchlist.csv": "SELECT ticker, added_at FROM watchlist ORDER BY added_at, ticker",
        }
        others = {name: pd.read_sql_query(q, conn) for name, q in queries.items()}
        intraday = pd.read_sql_query(
            "SELECT ticker, res, ts, open, high, low, close, volume FROM intraday "
            "WHERE ticker IN (SELECT ticker FROM watchlist) ORDER BY ticker, res, ts", conn)
    prices[["open", "high", "low", "close", "adj_close"]] = prices[["open", "high", "low", "close", "adj_close"]].round(4)
    prices["volume"] = prices["volume"].fillna(0).round().astype("int64")
    prices.to_csv(directory / "prices.csv", index=False)
    intraday[["open", "high", "low", "close"]] = intraday[["open", "high", "low", "close"]].round(4)
    intraday["volume"] = intraday["volume"].fillna(0).round().astype("int64")
    intraday.to_csv(directory / "intraday.csv", index=False)
    counts = {"prices.csv": len(prices), "intraday.csv": len(intraday)}
    for name, frame in others.items():
        frame.to_csv(directory / name, index=False)
        counts[name] = len(frame)
    meta = {"generated_at": pd.Timestamp.now("UTC").strftime("%Y-%m-%dT%H:%M:%SZ"), "rows": counts}
    (directory / "meta.json").write_text(json.dumps(meta))
    return meta


# ---------- syncing (used by the app) ----------
_lock = threading.Lock()
_state = {"checked": 0.0, "generated_at": None, "meta": None, "retry_after": 0.0}


def current_meta():
    return _state["meta"]


def sync(base, token=None, max_age=1500):
    """Pull the newest snapshot into the local SQLite (at most once per `max_age` seconds, process-wide).
    Returns (changed, meta, error)."""
    with _lock:
        now = time.time()
        if _state["meta"] and now - _state["checked"] < max_age:
            return False, _state["meta"], None
        if now < _state["retry_after"]:
            return False, _state["meta"], "snapshot temporarily unavailable"
        try:
            meta = read_json(base, "meta.json", token)
            if meta is None:
                raise FileNotFoundError("meta.json not found (has the data job run yet?)")
            if meta.get("generated_at") == _state["generated_at"]:
                _state["checked"] = now
                return False, meta, None
            if not load_into_db(base, token):
                raise ValueError("snapshot contains no prices")
            _state.update(checked=now, generated_at=meta["generated_at"], meta=meta)
            return True, meta, None
        except Exception as exc:
            _state["retry_after"] = now + 60  # do not hammer a failing source on every page load
            return False, _state["meta"], f"{type(exc).__name__}: {exc}"
