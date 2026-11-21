"""Pure functions that turn a price DataFrame into the 'historical evidence' numbers."""
import numpy as np
import pandas as pd


def pct_change_since(df: pd.DataFrame, days: int):
    if df.empty:
        return np.nan
    cutoff = df.index[-1] - pd.Timedelta(days=days)
    past = df[df.index <= cutoff]
    if past.empty:
        return np.nan
    return df["adj_close"].iloc[-1] / past["adj_close"].iloc[-1] - 1


def pct_change_ytd(df: pd.DataFrame):
    if df.empty:
        return np.nan
    start = pd.Timestamp(year=df.index[-1].year, month=1, day=1)
    past = df[df.index < start]
    if past.empty:
        return np.nan
    return df["adj_close"].iloc[-1] / past["adj_close"].iloc[-1] - 1


def one_day_change(df: pd.DataFrame):
    if len(df) < 2:
        return np.nan
    return df["adj_close"].iloc[-1] / df["adj_close"].iloc[-2] - 1


def summary_table(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for ticker, df in frames.items():
        if df.empty:
            continue
        rows.append(
            {
                "Ticker": ticker,
                "Last close": df["close"].iloc[-1],
                "1D": one_day_change(df),
                "1W": pct_change_since(df, 7),
                "1M": pct_change_since(df, 30),
                "YTD": pct_change_ytd(df),
                "1Y": pct_change_since(df, 365),
            }
        )
    return pd.DataFrame(rows)


def window_evidence(window: pd.DataFrame, full: pd.DataFrame) -> dict:
    """Facts about the selected window. `full` is the whole history (for 52-week high)."""
    s = window["adj_close"]
    rets = s.pct_change().dropna()
    drawdown = s / s.cummax() - 1
    last_year = full[full.index > full.index[-1] - pd.Timedelta(days=365)]["adj_close"]
    return {
        "period_return": s.iloc[-1] / s.iloc[0] - 1,
        "window_high": (s.max(), s.idxmax()),
        "window_low": (s.min(), s.idxmin()),
        "max_drawdown": (drawdown.min(), drawdown.idxmin()),
        "up_day_share": (rets > 0).mean() if len(rets) else np.nan,
        "best_day": (rets.max(), rets.idxmax()) if len(rets) else (np.nan, None),
        "worst_day": (rets.min(), rets.idxmin()) if len(rets) else (np.nan, None),
        "from_52w_high": s.iloc[-1] / last_year.max() - 1,
        "daily_volatility": rets.std() if len(rets) else np.nan,
    }


def after_drop_study(full: pd.DataFrame, drop: float, horizon: int = 5) -> dict:
    """After days that fell by >= `drop` (e.g. 0.03), what did the next `horizon` days do?

    Descriptive only: events cluster in crashes, so samples overlap and are not independent.
    """
    s = full["adj_close"]
    daily = s.pct_change()
    forward = s.shift(-horizon) / s - 1
    mask = (daily <= -drop) & forward.notna()
    fwd = forward[mask]
    if fwd.empty:
        return {"n": 0}
    return {
        "n": int(len(fwd)),
        "median": float(fwd.median()),
        "mean": float(fwd.mean()),
        "share_positive": float((fwd > 0).mean()),
        "worst": float(fwd.min()),
        "best": float(fwd.max()),
        "unconditional_share_positive": float((forward.dropna() > 0).mean()),
    }


def alerts(frames: dict[str, pd.DataFrame], threshold: float) -> list[tuple[str, str, str]]:
    """Simple watchlist alerts: big one-day moves and 1-year highs/lows. Returns (direction, ticker, text)."""
    out = []
    for ticker, df in frames.items():
        if len(df) < 2:
            continue
        move = one_day_change(df)
        if abs(move) >= threshold:
            out.append(("up" if move > 0 else "down", ticker, f"{move:+.1%} today"))
        s = df["adj_close"].iloc[-252:]
        if len(s) >= 60:
            if s.iloc[-1] >= s.max():
                out.append(("up", ticker, "at a 1-year high"))
            elif s.iloc[-1] <= s.min():
                out.append(("down", ticker, "at a 1-year low"))
    return out
