"""SQLite storage: prices, watchlist, news archive, prediction log. All SQL lives here."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).parent / "data" / "market.db"
DEFAULT_WATCHLIST = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "TSLA", "GC=F", "GLD"]


@contextmanager
def get_conn():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS prices (
                ticker    TEXT NOT NULL,
                date      TEXT NOT NULL,
                open      REAL,
                high      REAL,
                low       REAL,
                close     REAL,
                adj_close REAL,
                volume    REAL,
                PRIMARY KEY (ticker, date)
            );
            CREATE TABLE IF NOT EXISTS watchlist (
                ticker   TEXT PRIMARY KEY,
                added_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS news (
                ticker     TEXT NOT NULL,
                url        TEXT NOT NULL,
                published  TEXT,
                title      TEXT,
                publisher  TEXT,
                summary    TEXT,
                sentiment  REAL,
                fetched_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (ticker, url)
            );
            CREATE TABLE IF NOT EXISTS intraday (
                ticker TEXT NOT NULL,
                res    TEXT NOT NULL,
                ts     TEXT NOT NULL,
                open   REAL,
                high   REAL,
                low    REAL,
                close  REAL,
                volume REAL,
                PRIMARY KEY (ticker, res, ts)
            );
            CREATE TABLE IF NOT EXISTS predictions (
                ticker     TEXT NOT NULL,
                horizon    INTEGER NOT NULL,
                target     TEXT NOT NULL,
                made_on    TEXT NOT NULL,
                prob       REAL,
                base_rate  REAL,
                verdict    TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (ticker, horizon, target, made_on)
            );
            """
        )
        n = conn.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0]
        if n == 0:
            conn.executemany(
                "INSERT INTO watchlist (ticker) VALUES (?)",
                [(t,) for t in DEFAULT_WATCHLIST],
            )


def get_watchlist() -> list[str]:
    with get_conn() as conn:
        rows = conn.execute("SELECT ticker FROM watchlist ORDER BY added_at, ticker").fetchall()
    return [r[0] for r in rows]


def add_to_watchlist(ticker: str):
    with get_conn() as conn:
        conn.execute("INSERT OR IGNORE INTO watchlist (ticker) VALUES (?)", (ticker,))


def remove_from_watchlist(ticker: str):
    # Price history is kept on purpose, so re-adding the ticker later is instant.
    with get_conn() as conn:
        conn.execute("DELETE FROM watchlist WHERE ticker = ?", (ticker,))


def last_date(ticker: str):
    with get_conn() as conn:
        row = conn.execute("SELECT MAX(date) FROM prices WHERE ticker = ?", (ticker,)).fetchone()
    return pd.Timestamp(row[0]) if row and row[0] else None


def upsert_prices(ticker: str, df: pd.DataFrame) -> int:
    """df: DatetimeIndex + columns open, high, low, close, adj_close, volume."""
    if df.empty:
        return 0
    rows = [
        (ticker, idx.strftime("%Y-%m-%d"), r.open, r.high, r.low, r.close, r.adj_close, r.volume)
        for idx, r in df.iterrows()
    ]
    with get_conn() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO prices "
            "(ticker, date, open, high, low, close, adj_close, volume) VALUES (?,?,?,?,?,?,?,?)",
            rows,
        )
    return len(rows)


def load_prices(ticker: str) -> pd.DataFrame:
    with get_conn() as conn:
        df = pd.read_sql_query(
            "SELECT date, open, high, low, close, adj_close, volume "
            "FROM prices WHERE ticker = ? ORDER BY date",
            conn,
            params=(ticker,),
            parse_dates=["date"],
        )
    return df.set_index("date")


# ---------- news archive ----------
def save_news(ticker: str, rows: list[dict]) -> int:
    """Insert headlines not seen before. Returns the number of NEW rows."""
    if not rows:
        return 0
    with get_conn() as conn:
        before = conn.total_changes
        conn.executemany(
            "INSERT OR IGNORE INTO news (ticker, url, published, title, publisher, summary, sentiment) "
            "VALUES (?,?,?,?,?,?,?)",
            [(ticker, r["url"], r["published"], r["title"], r.get("publisher"), r.get("summary"),
              r.get("sentiment")) for r in rows],
        )
        return conn.total_changes - before


def load_news(ticker: str, since: str | None = None, limit: int = 100) -> pd.DataFrame:
    query = "SELECT published, title, publisher, url, summary, sentiment FROM news WHERE ticker = ?"
    params: list = [ticker]
    if since:
        query += " AND published >= ?"
        params.append(since)
    query += " ORDER BY published DESC LIMIT ?"
    params.append(limit)
    with get_conn() as conn:
        return pd.read_sql_query(query, conn, params=params, parse_dates=["published"])


# ---------- prediction log (builds a real forward track record) ----------
def log_prediction(ticker, horizon, target, made_on, prob, base_rate, verdict):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO predictions (ticker, horizon, target, made_on, prob, base_rate, verdict) "
            "VALUES (?,?,?,?,?,?,?)",
            (ticker, int(horizon), target, str(made_on), float(prob), float(base_rate), verdict),
        )


def load_predictions(ticker: str | None = None) -> pd.DataFrame:
    query = "SELECT ticker, horizon, target, made_on, prob, base_rate, verdict FROM predictions"
    params: list = []
    if ticker:
        query += " WHERE ticker = ?"
        params.append(ticker)
    query += " ORDER BY made_on DESC"
    with get_conn() as conn:
        return pd.read_sql_query(query, conn, params=params, parse_dates=["made_on"])


# ---------- intraday bars (hourly / 5-minute), stored so the hosted site never needs live Yahoo calls ----------
def upsert_intraday(ticker: str, res: str, df: pd.DataFrame) -> int:
    """df: DatetimeIndex (exchange-local wall clock) + open, high, low, close, volume."""
    if df is None or df.empty:
        return 0
    rows = [
        (ticker, res, idx.strftime("%Y-%m-%d %H:%M:%S"), r.open, r.high, r.low, r.close, r.volume)
        for idx, r in df.iterrows()
    ]
    with get_conn() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO intraday (ticker, res, ts, open, high, low, close, volume) VALUES (?,?,?,?,?,?,?,?)",
            rows,
        )
    return len(rows)


def last_intraday(ticker: str, res: str):
    with get_conn() as conn:
        row = conn.execute("SELECT MAX(ts) FROM intraday WHERE ticker = ? AND res = ?", (ticker, res)).fetchone()
    return pd.Timestamp(row[0]) if row and row[0] else None


def load_intraday(ticker: str, res: str) -> pd.DataFrame:
    with get_conn() as conn:
        df = pd.read_sql_query(
            "SELECT ts, open, high, low, close, volume FROM intraday WHERE ticker = ? AND res = ? ORDER BY ts",
            conn, params=(ticker, res), parse_dates=["ts"])
    return df.set_index("ts")


def prune_intraday(keep_days: dict) -> None:
    """keep_days: {"1h": 365, "5m": 30}. Also drops tickers that left the watchlist."""
    with get_conn() as conn:
        for res, days in keep_days.items():
            cutoff = (pd.Timestamp.now() - pd.Timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute("DELETE FROM intraday WHERE res = ? AND ts < ?", (res, cutoff))
        conn.execute("DELETE FROM intraday WHERE ticker NOT IN (SELECT ticker FROM watchlist)")
