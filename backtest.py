"""Paper test: what if you had held the stock only when the model leaned above its normal rate?

Uses ONLY the walk-forward out-of-sample probabilities, with a rule fixed in advance (hold when the model's
probability is above the stock's normal rate), so there is nothing tuned on the test period.
"""
import numpy as np
import pandas as pd


def paper_trade(df: pd.DataFrame, outlook, cost_bps: float = 5.0) -> dict | None:
    h = outlook.history
    nxt = df["adj_close"].pct_change().shift(-1).rename("nxt")
    d = h[["prob", "base"]].join(nxt).dropna()
    if len(d) < 250:
        return None
    pos = (d["prob"] > d["base"]).astype(float)
    turnover = pos.diff().abs()
    turnover.iloc[0] = pos.iloc[0]
    strategy = pos * d["nxt"] - turnover * cost_bps / 10_000
    hold = d["nxt"]
    equity = pd.DataFrame({"Model rule": (1 + strategy).cumprod(), "Buy and hold": (1 + hold).cumprod()})

    def stats(r: pd.Series, eq: pd.Series) -> dict:
        years = len(r) / 252
        return {
            "total": float(eq.iloc[-1] - 1),
            "annual": float(eq.iloc[-1] ** (1 / years) - 1) if years > 0 else np.nan,
            "max_drawdown": float((eq / eq.cummax() - 1).min()),
            "sharpe": float(r.mean() / r.std() * np.sqrt(252)) if r.std() > 0 else np.nan,
        }

    return {
        "equity": equity,
        "model": stats(strategy, equity["Model rule"]),
        "hold": stats(hold, equity["Buy and hold"]),
        "time_in_market": float(pos.mean()),
        "trades": int(turnover.sum()),
        "years": len(d) / 252,
    }
