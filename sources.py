"""Network sources beyond prices: news, earnings dates, fundamentals (all via yfinance, which is unofficial).

Every function can fail or return less than expected; the app treats all of them as best-effort.
"""
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

import db
import sentiment


def _to_utc_string(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        ts = pd.Timestamp(datetime.fromtimestamp(value, tz=timezone.utc))
    else:
        ts = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(ts):
        return None
    return ts.tz_convert("UTC").tz_localize(None).strftime("%Y-%m-%d %H:%M:%S")


def parse_news(items) -> list[dict]:
    """Handles both yfinance news formats (older flat dicts and the newer nested 'content' dicts)."""
    out = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if isinstance(content, dict):
            title = content.get("title")
            url = ((content.get("canonicalUrl") or {}).get("url")
                   or (content.get("clickThroughUrl") or {}).get("url"))
            published = _to_utc_string(content.get("pubDate") or content.get("displayTime"))
            publisher = (content.get("provider") or {}).get("displayName")
            summary = content.get("summary")
        else:
            title = item.get("title")
            url = item.get("link")
            published = _to_utc_string(item.get("providerPublishTime"))
            publisher = item.get("publisher")
            summary = item.get("summary")
        if not title or not url or not published:
            continue
        out.append({"title": title, "url": url, "published": published, "publisher": publisher,
                    "summary": summary})
    return out


def fetch_news(ticker: str) -> list[dict]:
    return parse_news(yf.Ticker(ticker).news)


def refresh_news(ticker: str) -> int:
    """Fetch headlines, score them, archive them. Returns the number of new headlines."""
    items = fetch_news(ticker)
    for item in items:
        item["sentiment"] = sentiment.score(f"{item['title']}. {item.get('summary') or ''}")
    return db.save_news(ticker, items)


def fetch_earnings_dates(ticker: str):
    """Returns (past_dates, next_date). Empty for ETFs, commodities and anything Yahoo has no calendar for."""
    frame = yf.Ticker(ticker).get_earnings_dates(limit=60)
    if frame is None or frame.empty:
        return [], None
    dates = pd.DatetimeIndex(frame.index).tz_localize(None).normalize().unique().sort_values()
    today = pd.Timestamp.now().normalize()
    past = [d for d in dates if d <= today]
    upcoming = [d for d in dates if d > today]
    return past, (min(upcoming) if upcoming else None)


FUNDAMENTAL_KEYS = ["longName", "sector", "industry", "marketCap", "trailingPE", "forwardPE", "priceToBook",
                    "profitMargins", "revenueGrowth", "beta"]


def fetch_fundamentals(ticker: str) -> dict:
    info = yf.Ticker(ticker).info or {}
    return {k: info.get(k) for k in FUNDAMENTAL_KEYS if info.get(k) is not None}
