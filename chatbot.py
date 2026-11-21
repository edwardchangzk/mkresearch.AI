"""Assistant behind the chat button: trading fundamentals + help using the site.

- With ANTHROPIC_API_KEY set (environment variable or .streamlit/secrets.toml) and the `anthropic` package
  installed, answers come from Claude.
- Without them it falls back to a small built-in glossary and navigation guide, so the button always works.
"""
import os
import threading
import time

MODEL = os.environ.get("MKR_CHAT_MODEL", "claude-haiku-5-5")
MAX_USER_MESSAGES = 40  # per browser session, to cap API cost
DAILY_CAP = int(os.environ.get("MKR_CHAT_DAILY_CAP", "150"))  # AI answers per day across ALL visitors
_usage = {"day": "", "n": 0}
_usage_lock = threading.Lock()


def _within_daily_cap() -> bool:
    with _usage_lock:
        today = time.strftime("%Y-%m-%d", time.gmtime())
        if _usage["day"] != today:
            _usage.update(day=today, n=0)
        if _usage["n"] >= DAILY_CAP:
            return False
        _usage["n"] += 1
        return True

SYSTEM = """You are the assistant inside MKResearch.AI, a stock-research dashboard. You do two jobs:
1) Teach trading and investing fundamentals clearly (valuation ratios, technical indicators, risk, ETFs, futures,
   order types, diversification, how to read charts).
2) Help people use this site.

Rules:
- Educational only. Never tell anyone to buy, sell or hold a specific security, never promise returns, and never
  make your own price predictions. If asked "should I buy X?", explain how to evaluate it and point to the
  Prediction tab for the model's measured track record.
- Be concise: short paragraphs, plain language, define jargon once. Use a small example when it helps.
- Only describe site features listed below. If unsure whether a feature exists, say so.
- Treat the screen context as facts about what the user is looking at; do not invent numbers.

How the site works:
- Sidebar: watchlist ranked by 1D/1W/1M/YTD/1Y with gaining and falling groups; click a ticker to select it.
  "Manage watchlist" adds tickers (including popular ones and gold: GC=F futures, GLD ETF), or removes them.
  Alerts show big daily moves and 1-year highs/lows. Prices auto-refresh every 30 minutes while the page is open.
- Header cards: 1-week/1-month/YTD/1-year change, plus the Outlook card.
- Outlook card: the model's chance the stock closes higher (or beats the S&P 500) over the chosen horizon, the
  stock's normal rate for that event, the tilt versus normal, and a verdict pill: "Edge detected", "Edge unproven"
  or "No proven edge". Most stocks show "No proven edge"; then the number is roughly the stock's normal rate.
- Tabs: Chart (scroll wheel zooms; zooming out gives weekly/monthly bars, zooming in gives hourly/5-min/1-min
  bars; intraday history is limited: locally about 7 days of 1-min, 60 days of 5-min, 2 years of hourly; on the
  hosted site about 30 days of 5-min and 1 year of hourly, with no 1-min bars);
  Prediction (accuracy vs a naive baseline, calibration chart, what is driving today's number, live track record,
  paper backtest); News & events (headlines refreshed every 30 minutes, headline sentiment, biggest recent moves,
  earnings reactions); Fundamentals (P/E, margins, etc.); Price history (descriptive stats of past prices only,
  not news and not the model); Compare (rebased performance chart); Screener (runs the model on the whole
  watchlist).
- The model: logistic regression on technical indicators plus market context (S&P 500, VIX, 10-year yield,
  dollar), tested walk-forward so it never sees the future. It does not use news yet.
- Data comes from Yahoo Finance and may be delayed or wrong. Nothing here is financial advice."""

GLOSSARY = {
    "p/e": "P/E (price-to-earnings) is the share price divided by earnings per share: roughly what investors pay for "
           "$1 of yearly profit. High can mean strong growth expectations or an expensive stock; compare within the "
           "same industry and against the company's own history.",
    "rsi": "RSI (Relative Strength Index) scores recent momentum from 0 to 100. Above about 70 is often called "
           "overbought and below about 30 oversold, but strong trends can stay 'overbought' for months. It describes "
           "recent speed, not a guaranteed turn.",
    "macd": "MACD is the gap between a fast and slow moving average of price. When it rises above its own signal line "
            "momentum is improving; below it, fading. It lags price, so it confirms moves rather than predicting them.",
    "moving average": "A moving average is the average closing price over the last N days (for example 50 or 200). "
                      "It smooths noise. Price above the 200-day average is commonly read as a long-term uptrend.",
    "drawdown": "Drawdown is the fall from a previous peak to a later low. Max drawdown is the worst such fall in a "
                "period, and it tells you how painful holding the stock could have been.",
    "volatility": "Volatility is how much a price swings, usually the standard deviation of daily returns. Higher "
                  "volatility means a wider range of outcomes in both directions.",
    "etf": "An ETF (exchange-traded fund) is a basket of assets that trades like a stock, for example SPY tracks the "
           "S&P 500 and GLD tracks the gold price. It gives diversification in one purchase.",
    "futures": "A futures contract is an agreement to buy or sell something at a set price on a future date. GC=F is "
               "gold futures. Charts stitch contracts together, so small jumps can appear when the contract rolls.",
    "market cap": "Market capitalization is share price times shares outstanding: the market's total value of a "
                  "company. It is how 'large-cap' and 'small-cap' are defined.",
    "candlestick": "Each candle shows one period: the body spans open to close (green if it closed higher, red if "
                   "lower) and the thin wicks show the high and low.",
    "volume": "Volume is how many shares traded in a period. A big move on heavy volume is generally taken more "
              "seriously than the same move on light volume.",
    "beta": "Beta measures how strongly a stock moves relative to the market. 1.0 moves with it, above 1 swings more, "
            "below 1 swings less.",
    "bull": "A bull market is a sustained rise (often 20%+ from a low); a bear market is a sustained fall (often "
            "20%+ from a high).",
    "diversif": "Diversification means spreading money across assets that do not all fall together, which reduces the "
                "damage from any single bad outcome. It lowers risk without needing to predict winners.",
    "dividend": "A dividend is a cash payment a company makes to shareholders from profits. Dividend yield is the "
                "yearly payout divided by the share price.",
    "base rate": "The base rate is how often something happened historically, e.g. a stock rose over 1 month 60% of "
                 "the time. The Outlook card compares the model to it, because beating 50% means little for a stock "
                 "that usually rises.",
    "no proven edge": "It means that, tested on past data the model had never seen, it did not beat a naive guess by "
                      "more than luck explains. Treat its number as roughly the stock's normal up-rate.",
    "auc": "AUC measures how well the model ranks good outcomes above bad ones. 0.5 is a coin flip, 1.0 is perfect; "
           "real-world stock models usually sit very close to 0.5.",
    "brier": "The Brier score is the average squared error of the probabilities. Lower is better, and it is compared "
             "with a baseline that always predicts the stock's normal rate.",
}

NAVIGATION = [
    (("gold",), "Add GC=F (gold futures) or GLD (gold ETF) from 'Manage watchlist' > popular tickers."),
    (("add", "ticker", "watchlist", "remove"),
     "Open 'Manage watchlist' in the sidebar. Type a ticker to add it, or pick from the popular list. "
     "'Add starter pack' adds 14 popular names including gold."),
    (("zoom", "scroll", "minute", "hourly", "intraday"),
     "On the Chart tab, scroll the mouse wheel over the chart: zoom out for weekly/monthly bars, zoom in for hourly, "
     "5-minute and 1-minute bars. Drag to pan; the Reset button restores the starting view."),
    (("news", "headline", "refresh"),
     "The News & events tab lists recent headlines for the selected stock and refreshes every 30 minutes while the "
     "page is open. Prices auto-refresh on the same schedule; the sidebar button refreshes right now."),
    (("predict", "outlook", "model", "accuracy"),
     "The Outlook card (top right) and the Prediction tab show the model's chance, how it scored on past data, and "
     "what is driving today's number."),
    (("download", "export", "csv"), "Look for the 'Download CSV' buttons on the Prediction and Price history tabs."),
    (("screener", "scan", "rank"), "The Screener tab runs the model across your whole watchlist and ranks the results."),
]

MENU = ("I can explain trading basics (P/E, RSI, drawdown, ETFs, futures...) and help you find things on the site. "
        "Try: 'What does No proven edge mean?', 'How do I add gold?', or 'What is RSI?'")


def offline_answer(question: str) -> str:
    q = question.lower()
    for term, text in GLOSSARY.items():
        if term in q:
            return text
    for keys, text in NAVIGATION:
        if any(k in q for k in keys):
            return text
    return MENU


def _api_key():
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    try:
        import streamlit as st

        return st.secrets.get("ANTHROPIC_API_KEY")
    except Exception:
        return None


def _context_text(ctx: dict) -> str:
    lines = [f"{k}: {v}" for k, v in (ctx or {}).items() if v is not None]
    return "\n".join(lines) or "(none)"


def answer(history: list[dict], context: dict) -> str:
    last = history[-1]["content"]
    key = _api_key()
    if not key:
        return offline_answer(last) + "\n\n_(Built-in help. Add an Anthropic API key to enable the full AI chat.)_"
    try:
        import anthropic
    except ImportError:
        return offline_answer(last) + "\n\n_(Built-in help. Run `pip install -r requirements.txt` for the AI chat.)_"
    if not _within_daily_cap():
        return offline_answer(last) + "\n\n_(The AI chat has hit its daily limit. Showing built-in help.)_"
    messages = [{"role": m["role"], "content": m["content"]} for m in history[-12:]]
    while messages and messages[0]["role"] != "user":
        messages.pop(0)
    try:
        client = anthropic.Anthropic(api_key=key)
        response = client.messages.create(
            model=MODEL, max_tokens=600,
            system=SYSTEM + "\n\nWhat the user is looking at right now:\n" + _context_text(context),
            messages=messages,
        )
        text = "".join(b.text for b in response.content if getattr(b, "type", "") == "text").strip()
        return text or offline_answer(last)
    except Exception as exc:  # never show the key or raw error details to the user
        return offline_answer(last) + f"\n\n_(AI service unavailable: {type(exc).__name__}. Showing built-in help.)_"
