"""A deliberately simple, transparent headline sentiment score in [-1, 1].

Counts finance-flavoured positive and negative word stems. It is crude (no negation handling, no context),
which is why the app shows it only as a hint. A finance-trained model such as FinBERT is the upgrade path.
"""
import re

POSITIVE = ("beat", "surge", "rall", "upgrad", "record", "growth", "profit", "gain", "soar", "jump", "rise",
            "rose", "strong", "boost", "outperform", "raise", "bullish", "approv", "win", "expand", "exceed",
            "climb", "recover", "buyback", "breakthrough", "partnership")
NEGATIVE = ("miss", "plunge", "downgrad", "lawsuit", "probe", "cut", "slump", "fall", "fell", "drop", "recall",
            "layoff", "fraud", "weak", "loss", "decline", "sink", "crash", "bearish", "warn", "investigat",
            "sue", "fine", "delay", "tumble", "slide", "selloff", "sell-off", "fear", "halt", "ban", "tariff",
            "bankrupt", "default")

_WORD = re.compile(r"[a-z][a-z\-']+")


def score(text: str | None) -> float:
    if not text:
        return 0.0
    words = _WORD.findall(text.lower())
    pos = sum(any(w.startswith(p) for p in POSITIVE) for w in words)
    neg = sum(any(w.startswith(n) for n in NEGATIVE) for w in words)
    return 0.0 if pos + neg == 0 else (pos - neg) / (pos + neg)


def label(value: float | None) -> str:
    if value is None:
        return "neutral"
    return "positive" if value > 0.2 else "negative" if value < -0.2 else "neutral"
