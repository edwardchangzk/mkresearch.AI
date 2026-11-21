"""Score the app's own logged predictions once enough time has passed (the real forward track record)."""
import pandas as pd

import db


def score_log(ticker: str | None = None) -> pd.DataFrame:
    log = db.load_predictions(ticker)
    if log.empty:
        return log.assign(realized=pd.Series(dtype=float), resolved=pd.Series(dtype=bool),
                          correct=pd.Series(dtype=object), naive_correct=pd.Series(dtype=float))
    prices: dict[str, pd.Series] = {}

    def series(sym):
        if sym not in prices:
            prices[sym] = db.load_prices(sym)["adj_close"]
        return prices[sym]

    realized, resolved = [], []
    for r in log.itertuples():
        s = series(r.ticker)
        pos = int(s.index.searchsorted(r.made_on))
        value = None
        if pos + r.horizon < len(s) and s.index[pos] == r.made_on:
            value = s.iloc[pos + r.horizon] / s.iloc[pos] - 1
            if r.target == "beat":
                spy = series("SPY")
                p2 = int(spy.index.searchsorted(r.made_on))
                if p2 + r.horizon < len(spy) and spy.index[p2] == r.made_on:
                    value -= spy.iloc[p2 + r.horizon] / spy.iloc[p2] - 1
                else:
                    value = None
        realized.append(value)
        resolved.append(value is not None)
    log = log.assign(realized=realized, resolved=resolved)
    log["correct"] = [("✓" if (r.prob > 0.5) == (r.realized > 0) else "✗") if r.resolved else "…"
                      for r in log.itertuples()]
    # What "always guess this stock's usual direction" would have scored on the same predictions.
    log["naive_correct"] = [float((r.base_rate > 0.5) == (r.realized > 0)) if r.resolved else float("nan")
                            for r in log.itertuples()]
    return log


def summarize(done: pd.DataFrame):
    """Hit rates of the model versus the naive guess, overall and by horizon / verdict / ticker."""
    if done is None or done.empty:
        return None
    d = done.assign(hit=(done["correct"] == "✓").astype(float))
    def by(column):
        return d.groupby(column).agg(n=("hit", "size"), model=("hit", "mean"), naive=("naive_correct", "mean"))
    return {"n": len(d), "model": float(d["hit"].mean()), "naive": float(d["naive_correct"].mean()),
            "by_horizon": by("horizon"), "by_verdict": by("verdict"), "by_ticker": by("ticker")}
