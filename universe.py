"""Popular tickers (Yahoo Finance symbols) offered under 'Manage watchlist'."""

CATEGORIES = {
    "Mega-cap tech": {
        "AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "NVIDIA", "GOOGL": "Alphabet (Google)",
        "AMZN": "Amazon", "META": "Meta Platforms", "TSLA": "Tesla", "AVGO": "Broadcom",
    },
    "Popular growth": {
        "NFLX": "Netflix", "AMD": "Advanced Micro Devices", "PLTR": "Palantir", "ORCL": "Oracle",
    },
    "Finance": {
        "JPM": "JPMorgan Chase", "V": "Visa", "MA": "Mastercard", "BRK-B": "Berkshire Hathaway B",
        "GS": "Goldman Sachs",
    },
    "Consumer & health": {
        "WMT": "Walmart", "COST": "Costco", "KO": "Coca-Cola", "DIS": "Disney",
        "UNH": "UnitedHealth", "LLY": "Eli Lilly", "JNJ": "Johnson & Johnson", "PG": "Procter & Gamble",
    },
    "Energy & industrial": {
        "XOM": "Exxon Mobil", "CVX": "Chevron", "BA": "Boeing", "CAT": "Caterpillar",
    },
    "ETFs": {
        "SPY": "S&P 500 ETF", "QQQ": "Nasdaq-100 ETF", "DIA": "Dow Jones ETF",
        "IWM": "Russell 2000 ETF", "VTI": "Total US Market ETF",
    },
    "Gold & commodities": {
        "GC=F": "Gold futures (COMEX, USD/oz)", "GLD": "SPDR Gold Shares ETF", "SLV": "iShares Silver Trust",
    },
}

NAMES = {t: name for group in CATEGORIES.values() for t, name in group.items()}
ALL = list(NAMES)
STARTER = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "JPM", "WMT", "XOM",
           "GC=F", "GLD"]


def label(ticker: str) -> str:
    return f"{ticker} · {NAMES.get(ticker, ticker)}"


# Market context used by the model (stored in the prices table but not shown in the watchlist).
CONTEXT = {"SPY": "S&P 500", "^VIX": "VIX (fear gauge)", "^TNX": "10-year Treasury yield", "DX-Y.NYB": "US dollar index"}
