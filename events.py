"""Event study: how does a stock typically react around earnings?"""
import pandas as pd


def earnings_reactions(daily: pd.DataFrame, dates) -> dict:
    """For each past earnings date, measure the 2-day move from the close BEFORE the report date to the close
    AFTER it. Using both sides makes the result correct whether the company reports before or after the bell."""
    s = daily["adj_close"].dropna()
    idx = s.index
    rows = []
    for d in dates:
        pos = int(idx.searchsorted(d))
        if pos < 1 or pos + 1 >= len(idx) or (idx[pos] - d).days > 4:
            continue
        pre, report_day, post = s.iloc[pos - 1], s.iloc[pos], s.iloc[pos + 1]
        rows.append({"date": d, "move": post / pre - 1, "report_day_move": report_day / pre - 1})
    table = pd.DataFrame(rows)
    if table.empty:
        return {"n": 0, "table": table}
    normal = float(s.pct_change(2).abs().median())
    return {
        "n": len(table),
        "table": table.sort_values("date", ascending=False),
        "median_abs_move": float(table["move"].abs().median()),
        "normal_abs_move": normal,
        "share_positive": float((table["move"] > 0).mean()),
        "biggest_up": float(table["move"].max()),
        "biggest_down": float(table["move"].min()),
    }
