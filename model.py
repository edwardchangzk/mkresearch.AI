"""Walk-forward probability model with an honest scorecard.

Question answered: "what is the chance this stock closes higher (or beats the S&P 500) `horizon` trading days
from now?"

Why it is built this way:
- Features use only past data (no look-ahead).
- Every prediction in the scorecard comes from a model trained ONLY on data whose outcome was already known at
  that time (walk-forward, retrained monthly, with a `horizon`-day gap).
- The model is judged against a naive baseline ("always guess the direction that was most common in the
  training data"). Beating 50% means nothing for a stock that rises 58% of the time.
- Market-context features (S&P 500, VIX, yields, dollar) are decided in advance, not picked by test score. The
  scorecard also reports the same model WITHOUT them, so you can see whether they helped.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

BASE_FEATURES = ["ret_1d", "ret_5d", "ret_10d", "ret_21d", "ret_63d", "ret_126d", "vs_ma20", "vs_ma50",
                 "vs_ma200", "rsi14", "macd_hist", "vol_21d", "vol_ratio", "volume_z", "from_252d_high"]

FEATURE_LABELS = {
    "ret_1d": "1-day return", "ret_5d": "1-week return", "ret_10d": "2-week return",
    "ret_21d": "1-month return", "ret_63d": "3-month return", "ret_126d": "6-month return",
    "vs_ma20": "Price vs 20-day average", "vs_ma50": "Price vs 50-day average",
    "vs_ma200": "Price vs 200-day average", "rsi14": "RSI (14)", "macd_hist": "MACD momentum",
    "vol_21d": "Volatility (1 month)", "vol_ratio": "Volatility spike (1w vs 3m)",
    "volume_z": "Volume vs normal", "from_252d_high": "Distance from 1-year high",
    "mkt_ret_21d": "S&P 500 1-month return", "mkt_vs_ma200": "S&P 500 vs 200-day average",
    "rel_ret_63d": "3-month return vs S&P 500", "vix_level": "VIX level (fear gauge)",
    "vix_chg_5d": "VIX 1-week change", "yield_chg_21d": "10-yr yield 1-month change",
    "usd_ret_21d": "US dollar 1-month change",
}

MIN_TRAIN = 756   # ~3 years of trading days before the first out-of-sample prediction
STEP = 21         # retrain roughly monthly
WINDOW = 2520     # train on at most the last ~10 years


@dataclass
class Outlook:
    horizon: int
    target: str               # "up" or "beat" (beats the S&P 500)
    as_of: pd.Timestamp
    prob_up: float
    base_rate: float          # how often this happened over the horizon in the training data
    contributions: pd.Series  # what pushes today's probability up or down (log-odds units)
    accuracy: float
    baseline_accuracy: float
    auc: float
    brier: float
    brier_baseline: float
    n_scored: int
    n_effective: float
    up_rate: float            # out-of-sample share of periods where the target event happened
    verdict: str              # "edge" | "weak" | "none"
    calibration: pd.DataFrame
    history: pd.DataFrame     # resolved out-of-sample predictions (prob, base, y, fwd)
    used_context: bool
    context_compare: dict | None  # same model without market context, on the same rows


def _aligned(context, symbol, index):
    frame = (context or {}).get(symbol)
    if frame is None or frame.empty:
        return None
    return frame["adj_close"].reindex(index, method="ffill", limit=5)


def build_features(df: pd.DataFrame, context: dict | None = None) -> pd.DataFrame:
    s = df["adj_close"]
    r = s.pct_change()
    f = pd.DataFrame(index=df.index)
    for n in (1, 5, 10, 21, 63, 126):
        f[f"ret_{n}d"] = s.pct_change(n)
    for n in (20, 50, 200):
        f[f"vs_ma{n}"] = s / s.rolling(n).mean() - 1
    delta = s.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    f["rsi14"] = 100 - 100 / (1 + gain / loss)
    macd = s.ewm(span=12, adjust=False).mean() - s.ewm(span=26, adjust=False).mean()
    f["macd_hist"] = (macd - macd.ewm(span=9, adjust=False).mean()) / s
    f["vol_21d"] = r.rolling(21).std()
    f["vol_ratio"] = r.rolling(5).std() / r.rolling(63).std()
    vol = df["volume"].replace(0, np.nan)
    # Days with no reported volume (spot gold, FX, some old futures data) count as "normal volume".
    f["volume_z"] = np.log(vol / vol.rolling(20, min_periods=10).mean()).fillna(0.0)
    f["from_252d_high"] = s / s.rolling(252, min_periods=60).max() - 1

    spy = _aligned(context, "SPY", df.index)
    if spy is not None:
        f["mkt_ret_21d"] = spy.pct_change(21)
        f["mkt_vs_ma200"] = spy / spy.rolling(200).mean() - 1
        f["rel_ret_63d"] = f["ret_63d"] - spy.pct_change(63)
    vix = _aligned(context, "^VIX", df.index)
    if vix is not None:
        f["vix_level"] = np.log(vix.where(vix > 0))
        f["vix_chg_5d"] = vix.pct_change(5)
    tnx = _aligned(context, "^TNX", df.index)
    if tnx is not None:
        f["yield_chg_21d"] = tnx.diff(21)
    usd = _aligned(context, "DX-Y.NYB", df.index)
    if usd is not None:
        f["usd_ret_21d"] = usd.pct_change(21)
    return f.replace([np.inf, -np.inf], np.nan)


def _new_model():
    return make_pipeline(StandardScaler(), LogisticRegression(C=0.05, max_iter=1000))


def _walk_forward(X, y, horizon):
    """Out-of-sample probabilities. Returns a DataFrame (prob, base) or None if there is too little data."""
    pos = pd.Series(np.arange(len(X)), index=X.index)
    valid = X.notna().all(axis=1)
    valid_pos = pos[valid].to_numpy()
    if len(valid_pos) < MIN_TRAIN + 126:
        return None
    prob = pd.Series(np.nan, index=X.index)
    base = pd.Series(np.nan, index=X.index)
    for p0 in range(int(valid_pos[MIN_TRAIN]), len(X), STEP):
        # A training row j has a known label only once price j+horizon exists: j <= p0 - horizon.
        train = valid & y.notna() & (pos <= p0 - horizon) & (pos > p0 - horizon - WINDOW)
        test = valid & (pos >= p0) & (pos < p0 + STEP)
        y_tr = y[train]
        if not test.any() or y_tr.nunique() < 2 or len(y_tr) < MIN_TRAIN // 2:
            continue
        m = _new_model().fit(X[train], y_tr)
        prob[test] = m.predict_proba(X[test])[:, 1]
        base[test] = y_tr.mean()
    return pd.DataFrame({"prob": prob, "base": base})


def _metrics(scored: pd.DataFrame, horizon: int) -> dict:
    actual = scored["y"] == 1
    accuracy = float(((scored["prob"] > 0.5) == actual).mean())
    baseline_accuracy = float(((scored["base"] > 0.5) == actual).mean())
    return {
        "accuracy": accuracy,
        "baseline_accuracy": baseline_accuracy,
        "brier": float(((scored["prob"] - scored["y"]) ** 2).mean()),
        "brier_baseline": float(((scored["base"] - scored["y"]) ** 2).mean()),
        "auc": float(roc_auc_score(scored["y"], scored["prob"])),
        # Consecutive days share most of their outcome window, so the real number of independent
        # observations is roughly n / horizon. This is a rough screen, not a formal test.
        "n_effective": max(len(scored) / horizon, 1.0),
    }


def _verdict(m: dict) -> str:
    se = (0.25 / m["n_effective"]) ** 0.5
    edge = m["accuracy"] - m["baseline_accuracy"]
    if edge > 2 * se and m["brier"] < m["brier_baseline"] and m["auc"] > 0.5:
        return "edge"
    if edge > 0 and m["brier"] < m["brier_baseline"]:
        return "weak"
    return "none"


def run(df: pd.DataFrame, horizon: int, context: dict | None = None, target: str = "up",
        compare: bool = True) -> Outlook | None:
    """Returns None when there is not enough history (or context, for target='beat') for a scorecard."""
    df = df.dropna(subset=["adj_close"])
    s = df["adj_close"]
    fwd = s.shift(-horizon) / s - 1
    if target == "beat":
        spy = _aligned(context, "SPY", df.index)
        if spy is None:
            return None
        fwd = fwd - (spy.shift(-horizon) / spy - 1)
    y = (fwd > 0).astype(float).where(fwd.notna())

    X_all = build_features(df, context)
    use_context = any(c not in BASE_FEATURES for c in X_all.columns)
    wf = _walk_forward(X_all, y, horizon)
    if wf is None:
        return None
    res = wf.assign(y=y, fwd=fwd).dropna(subset=["prob"])
    scored = res.dropna(subset=["y"])
    if len(scored) < 100 or scored["y"].nunique() < 2:
        return None
    m = _metrics(scored, horizon)

    compare_info = None
    if compare and use_context:
        wf_base = _walk_forward(X_all[BASE_FEATURES], y, horizon)
        if wf_base is not None:
            alt = wf_base.assign(y=y).dropna(subset=["prob", "y"])
            common = scored.index.intersection(alt.index)
            if len(common) >= 100 and alt.loc[common, "y"].nunique() == 2:
                a, b = _metrics(scored.loc[common], horizon), _metrics(alt.loc[common], horizon)
                compare_info = {"with_auc": a["auc"], "without_auc": b["auc"], "with_acc": a["accuracy"],
                                "without_acc": b["accuracy"], "with_brier": a["brier"],
                                "without_brier": b["brier"], "n": len(common)}

    bins = [0, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 1.0]
    cal = (
        scored.assign(bin=pd.cut(scored["prob"], bins, include_lowest=True))
        .groupby("bin", observed=True)
        .agg(n=("y", "size"), predicted=("prob", "mean"), actual=("y", "mean"))
        .reset_index()
    )
    cal["range"] = [f"{round(iv.left * 100)}–{round(iv.right * 100)}%" for iv in cal["bin"]]

    # Today's prediction: train on everything whose outcome is already known.
    pos = pd.Series(np.arange(len(df)), index=df.index)
    valid = X_all.notna().all(axis=1)
    last_valid = X_all[valid].index[-1]
    last_pos = int(pos[last_valid])
    train = valid & y.notna() & (pos <= last_pos - horizon) & (pos > last_pos - horizon - WINDOW)
    final = _new_model().fit(X_all[train], y[train])
    x_now = X_all.loc[[last_valid]]
    prob_now = float(final.predict_proba(x_now)[0, 1])
    scaler = final.named_steps["standardscaler"]
    clf = final.named_steps["logisticregression"]
    contributions = pd.Series(clf.coef_[0] * scaler.transform(x_now)[0], index=X_all.columns)

    return Outlook(
        horizon=horizon, target=target, as_of=last_valid, prob_up=prob_now, base_rate=float(y[train].mean()),
        contributions=contributions, accuracy=m["accuracy"], baseline_accuracy=m["baseline_accuracy"],
        auc=m["auc"], brier=m["brier"], brier_baseline=m["brier_baseline"], n_scored=len(scored),
        n_effective=m["n_effective"], up_rate=float(scored["y"].mean()), verdict=_verdict(m),
        calibration=cal, history=scored, used_context=use_context, context_compare=compare_info,
    )
