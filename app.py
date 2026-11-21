"""MKResearch.AI dashboard. Run with:  python -m streamlit run app.py"""
import html
import time

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

import backtest
import chart
import chatbot
import config
import db
import events
import ingest
import model
import sentiment
import snapshot
import sources
import stats
import style
import tracking
import universe

st.set_page_config(page_title="MKResearch.AI", page_icon="📈", layout="wide")
style.inject()
db.init_db()

# Cloud mode: the site only READS a snapshot published by the scheduled GitHub job.
snap_meta, cloud_error = None, None
if config.CLOUD:
    boot = None
    if snapshot.current_meta() is None:  # cold start: nothing to show until the first download finishes
        boot = st.empty()
        boot.markdown(style.loader("Loading market data…"), unsafe_allow_html=True)
    changed, snap_meta, cloud_error = snapshot.sync(config.SNAPSHOT_URL, config.SNAPSHOT_TOKEN)
    if boot is not None:
        boot.empty()
    if changed:
        st.cache_data.clear()

UP, DOWN, AMBER, BLUE = style.UP, style.DOWN, style.AMBER, style.BLUE
RANGES = {"1M": 30, "3M": 91, "6M": 182, "1Y": 365, "5Y": 1825, "Max": None}
RANK_COLUMNS = ["1D", "1W", "1M", "YTD", "1Y"]
HORIZON_NAMES = {5: "1 week", 20: "1 month", 60: "3 months"}
TARGET_NAMES = {"up": "Goes up", "beat": "Beats S&P 500"}
REFRESH_SECONDS = 1800  # news and prices refresh every 30 minutes while the page is open
PLOT = dict(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Plus Jakarta Sans, sans-serif", color="#cbd5e1"), margin=dict(l=10, r=10, t=30, b=10))


# ---------- cached loaders ----------
@st.cache_data(ttl=300)
def load(ticker: str) -> pd.DataFrame:
    return db.load_prices(ticker)


@st.cache_data(ttl=300, show_spinner=False)
def load_intraday(ticker: str) -> dict:
    if config.CLOUD:  # hosted site: bars come from the snapshot, never from live Yahoo calls
        return {key: db.load_intraday(ticker, key) for key in ("1h", "5m")}
    out = {}
    for key in ingest.INTRADAY:
        try:
            out[key] = ingest.fetch_intraday(ticker, key)
        except Exception:
            out[key] = pd.DataFrame()
    return out


def load_context() -> dict:
    return {sym: db.load_prices(sym) for sym in universe.CONTEXT}


@st.cache_data(show_spinner=False)
def run_outlook(ticker: str, horizon: int, target: str, as_of: str, ctx_asof: str, compare: bool = True):
    # as_of / ctx_asof only exist to invalidate the cache when new data arrives
    return model.run(db.load_prices(ticker), horizon, context=load_context(), target=target, compare=compare)


@st.cache_data(ttl=REFRESH_SECONDS - 300, show_spinner=False)
def refresh_news(ticker: str) -> dict:
    try:
        new = sources.refresh_news(ticker)
    except Exception:
        new = -1
    return {"new": new, "at": pd.Timestamp.now().strftime("%H:%M")}


@st.cache_data(ttl=REFRESH_SECONDS - 300, show_spinner=False)
def load_extras() -> dict:
    try:
        return snapshot.read_json(config.SNAPSHOT_URL, "extras.json", config.SNAPSHOT_TOKEN) or {}
    except Exception:
        return {}


@st.cache_data(ttl=86400, show_spinner=False)
def _live_earnings(ticker: str):
    try:
        return sources.fetch_earnings_dates(ticker)
    except Exception:
        return [], None


@st.cache_data(ttl=43200, show_spinner=False)
def _live_fundamentals(ticker: str) -> dict:
    try:
        return sources.fetch_fundamentals(ticker)
    except Exception:
        return {}


def earnings_dates(ticker: str):
    if config.CLOUD:
        entry = load_extras().get("earnings", {}).get(ticker)
        if not entry:
            return [], None
        return [pd.Timestamp(d) for d in entry["past"]], (pd.Timestamp(entry["next"]) if entry.get("next") else None)
    return _live_earnings(ticker)


def fundamentals(ticker: str) -> dict:
    if config.CLOUD:
        return load_extras().get("fundamentals", {}).get(ticker, {})
    return _live_fundamentals(ticker)


# ---------- helpers ----------
def fmt_pct(v):
    return "–" if pd.isna(v) else f"{v:+.2%}"


def fmt_pt(pair):
    value, date = pair
    return f"{value:+.2%} on {date:%Y-%m-%d}" if date is not None else "–"


def fmt_big(v):
    for unit, size in (("T", 1e12), ("B", 1e9), ("M", 1e6)):
        if abs(v) >= size:
            return f"${v / size:,.2f}{unit}"
    return f"${v:,.0f}"


def cls(v):
    return "" if pd.isna(v) else ("up" if v >= 0 else "down")


def kpi_card(label, value):
    return f'<div class="card"><div class="klabel">{label}</div><div class="kvalue {cls(value)}">{fmt_pct(value)}</div></div>'


def outlook_card(o, horizon, target):
    title = f"{HORIZON_NAMES[horizon]} outlook"
    if o is None:
        why = "needs S&P 500 data and about 4+ years of history" if target == "beat" else "needs roughly 4+ years of history"
        return f'<div class="card outlook"><div class="klabel">{title}</div><div class="ksub">Not enough data to train and test a model ({why}).</div></div>'
    event = "closing higher" if o.target == "up" else "beating the S&P 500"
    tilt = (o.prob_up - o.base_rate) * 100
    reliable = o.verdict != "none"
    arrow, color = ("●", "") if abs(tilt) < 1 else (("▲", "up") if tilt > 0 else ("▼", "down"))
    if not reliable:
        color = ""  # the tilt is within noise, so no green/red
    pill = {"edge": ("Edge detected", "up"), "weak": ("Edge unproven", "warn"), "none": ("No proven edge", "muted")}[o.verdict]
    note = "" if reliable else " The tilt is within noise, so read the number as the normal rate."
    return (
        f'<div class="card outlook"><div class="klabel">{title} · chance of {event}</div>'
        f'<div class="big {color}">{arrow} {o.prob_up:.0%}</div>'
        f'<span class="pill {pill[1]}">{pill[0]}</span> <span class="pill muted">{tilt:+.0f} pts vs normal {o.base_rate:.0%}</span>'
        f'<div class="ksub">Out-of-sample the model was right {o.accuracy:.0%} vs {o.baseline_accuracy:.0%} for a naive guess.{note}</div></div>'
    )


def age_text(ts, now):
    minutes = (now - ts).total_seconds() / 60
    if minutes < 60:
        return f"{max(int(minutes), 1)}m ago"
    if minutes < 48 * 60:
        return f"{int(minutes // 60)}h ago"
    return f"{int(minutes // 1440)}d ago"


# ---------- auto-refresh fragments (only run while the page is open) ----------
@st.fragment(run_every=REFRESH_SECONDS)
def auto_refresh():
    now = time.time()
    last = st.session_state.get("last_auto")
    if last is None:
        st.session_state.last_auto = now
        return
    if now - last >= REFRESH_SECONDS - 100:
        ingest.update_all()
        ingest.update_context()
        st.cache_data.clear()
        st.session_state.last_auto = now
        st.rerun()


@st.fragment(run_every=REFRESH_SECONDS)
def cloud_refresh():
    changed, _, _ = snapshot.sync(config.SNAPSHOT_URL, config.SNAPSHOT_TOKEN)
    if changed:
        st.cache_data.clear()
        st.rerun()


@st.fragment(run_every=REFRESH_SECONDS)
def news_panel(ticker, full):
    info = {"new": 0} if config.CLOUD else refresh_news(ticker)  # refresh FIRST, then read the archive
    news = db.load_news(ticker, limit=80)
    if config.CLOUD:
        meta = snapshot.current_meta() or {}
        st.caption(f"Headlines are archived by the scheduled data job (about every 30 minutes) · snapshot "
                   f"{meta.get('generated_at', '–')} UTC · {len(news)} headlines archived for {ticker}")
    else:
        st.caption(f"Updated {info['at']} · refreshes every 30 minutes while this page is open · "
                   f"{len(news)} headlines archived for {ticker}")
    if info["new"] < 0:
        st.warning("Could not reach the news feed just now. Showing what is already archived.")
    if news.empty:
        st.info("No headlines archived yet. Indices, futures and some ETFs have few or none.")
        return
    now = pd.Timestamp.now("UTC").tz_localize(None)
    cols = st.columns(3)
    for col, (label, hours) in zip(cols[:2], (("Last 24 hours", 24), ("Last 7 days", 168))):
        window = news[news["published"] >= now - pd.Timedelta(hours=hours)]
        mood = sentiment.label(window["sentiment"].mean()) if len(window) else "–"
        col.metric(label, f"{len(window)} headlines", f"tone: {mood}", delta_color="off")
    cols[2].caption("Tone is a crude word count (positive vs negative words), shown as a hint only. "
                    "The prediction model does not use news yet.")
    for n, row in enumerate(news.head(12).itertuples()):
        st.markdown(
            f'<div class="news" style="--i:{n}"><span class="dot {sentiment.label(row.sentiment)}"></span>'
            f'<a href="{html.escape(row.url)}" target="_blank">{html.escape(row.title)}</a>'
            f'<div class="meta">{html.escape(row.publisher or "")} · {age_text(row.published, now)}</div></div>',
            unsafe_allow_html=True)

    st.markdown("**Biggest recent moves and the headlines around them**")
    recent = full["adj_close"].pct_change().iloc[-60:].dropna()
    big = recent.reindex(recent.abs().sort_values(ascending=False).index)[:5].sort_index(ascending=False)
    for day, move in big.items():
        near = news[(news["published"] >= day - pd.Timedelta(days=1)) & (news["published"] < day + pd.Timedelta(days=1))]
        heads = " · ".join(html.escape(t) for t in near["title"].head(2)) if len(near) else \
            "no archived headlines (Yahoo only serves recent news; the archive grows while the app or refresh job runs)"
        st.markdown(f'<div class="news"><b class="{cls(move)}">{move:+.2%}</b> on {day:%b %d}'
                    f'<div class="meta">{heads}</div></div>', unsafe_allow_html=True)


# ---------- chat widget: round button bottom-right, panel slides up and back down ----------
SUGGESTIONS = ["What does 'No proven edge' mean?", "How do I add gold?", "What is RSI?"]
WELCOME = ("Hi, I'm the MKResearch.AI assistant. I can explain trading basics and show you around the site. "
           "I can't give personal buy or sell advice.")


@st.fragment
def chat_widget(ctx):
    st.session_state.setdefault("chat_open", False)
    st.session_state.setdefault("chat_msgs", [{"role": "assistant", "content": WELCOME}])
    is_open = st.session_state.chat_open
    st.markdown(style.CHAT_OPEN if is_open else style.CHAT_CLOSED, unsafe_allow_html=True)

    def toggle():
        st.session_state.chat_open = not st.session_state.chat_open

    def close():
        st.session_state.chat_open = False

    def ask(text):
        st.session_state.chat_msgs.append({"role": "user", "content": text})

    with st.container(key="chat_fab"):
        st.button("✕" if is_open else "💬", key="chat_toggle", on_click=toggle)

    with st.container(key="chat_panel"):
        head, down = st.columns([5, 1])
        head.markdown('<div class="chat-title">MKResearch Assistant</div>'
                      '<div class="chat-sub">Trading basics · help using the site</div>', unsafe_allow_html=True)
        with down.container(key="chat_close"):
            st.button("⌄", key="chat_close_btn", on_click=close, help="Close")
        box = st.container(height=320)
        msgs = st.session_state.chat_msgs
        if len(msgs) == 1:
            for q in SUGGESTIONS:
                st.button(q, key=f"sugg_{q}", on_click=ask, args=(q,), use_container_width=True)
        with st.form("chat_form", clear_on_submit=True, border=False):
            c1, c2 = st.columns([5, 1])
            text = c1.text_input("Message", placeholder="Ask about trading or the site...", label_visibility="collapsed")
            sent = c2.form_submit_button("➤")
        if sent and text.strip():
            ask(text.strip())
        if msgs[-1]["role"] == "user":
            if sum(m["role"] == "user" for m in msgs) > chatbot.MAX_USER_MESSAGES:
                reply = "You have reached the message limit for this session. Refresh the page to start again."
            else:
                with box, st.spinner("Thinking..."):
                    reply = chatbot.answer(msgs, ctx)
            msgs.append({"role": "assistant", "content": reply})
        with box:
            for m in msgs:
                st.chat_message(m["role"]).markdown(m["content"])


# ---------- first run: download anything missing ----------
if not config.CLOUD and any(db.last_date(t) is None for t in db.get_watchlist()):
    with st.spinner("Downloading price history..."):
        for t in db.get_watchlist():
            if db.last_date(t) is None:
                try:
                    ingest.update_ticker(t)
                except Exception as exc:
                    st.warning(f"Could not download {t}: {exc}")
        st.cache_data.clear()
if not config.CLOUD and not st.session_state.get("ctx_tried") and any(db.last_date(s) is None for s in universe.CONTEXT):
    st.session_state.ctx_tried = True
    with st.spinner("Downloading market context (S&P 500, VIX, yields, dollar)..."):
        ingest.update_context()
        st.cache_data.clear()

frames = {t: load(t) for t in db.get_watchlist()}
frames = {t: df for t, df in frames.items() if not df.empty}
if "selected" not in st.session_state or st.session_state.selected not in frames:
    st.session_state.selected = next(iter(frames), None)
table = stats.summary_table(frames) if frames else pd.DataFrame()


# ---------- sidebar ----------
def select(ticker):
    st.session_state.selected = ticker


def add_ticker():
    sym = st.session_state.get("new_ticker", "").strip().upper()
    if not sym:
        return
    try:
        rows = ingest.update_ticker(sym)
    except Exception:
        rows = 0
    if rows == 0:
        st.session_state.flash = f"No data found for {sym}."
    else:
        db.add_to_watchlist(sym)
        st.cache_data.clear()
        st.session_state.selected = sym
        st.session_state.flash = None
    st.session_state.new_ticker = ""


def add_many(tickers):
    failed = []
    with st.spinner(f"Downloading history for {len(tickers)} tickers..."):
        for t in tickers:
            try:
                rows = ingest.update_ticker(t)
            except Exception:
                rows = 0
            if rows:
                db.add_to_watchlist(t)
            else:
                failed.append(t)
    st.cache_data.clear()
    st.session_state.flash = ("Could not download: " + ", ".join(failed)) if failed else None
    st.rerun()


def watch_button(rec, rank):
    v = rec[rank]
    color, arrow = ("green", "▲") if v >= 0 else ("red", "▼")
    label = f"**{rec['Ticker']}** · {rec['Last close']:,.2f} · :{color}[{arrow} {abs(v):.2%}]"
    st.button(label, key=f"pick_{rec['Ticker']}", on_click=select, args=(rec["Ticker"],), use_container_width=True,
              type="primary" if rec["Ticker"] == st.session_state.selected else "secondary")


with st.sidebar:
    st.markdown('<div class="brand"><span>◆</span> MKResearch<span>.AI</span></div>', unsafe_allow_html=True)
    if not table.empty:
        query = st.text_input("Search watchlist", placeholder="Search tickers or names", key="wl_query",
                              label_visibility="collapsed").strip().upper()
        shown = table
        if query:
            keep = table["Ticker"].str.upper().str.contains(query, regex=False) | table["Ticker"].map(
                lambda t: query in universe.NAMES.get(t, "").upper())
            shown = table[keep]
        rank = st.radio("Rank by", RANK_COLUMNS, horizontal=True, key="rank")
        ranked = shown.dropna(subset=[rank]).sort_values(rank, ascending=False)
        gaining, falling = ranked[ranked[rank] >= 0], ranked[ranked[rank] < 0]
        st.markdown(f'<div class="sec up">▲ Gaining · {len(gaining)}</div>', unsafe_allow_html=True)
        for rec in gaining.to_dict("records"):
            watch_button(rec, rank)
        st.markdown(f'<div class="sec down">▼ Falling · {len(falling)}</div>', unsafe_allow_html=True)
        for rec in falling.to_dict("records"):
            watch_button(rec, rank)
        no_data = shown[shown[rank].isna()]
        if not no_data.empty:
            st.caption("Not enough history for this period: " + ", ".join(no_data["Ticker"]))

    if config.CLOUD:
        st.caption("The watchlist is set in watchlist.txt in the project's GitHub repository and updated by the scheduled data job.")
    else:
        with st.expander("Manage watchlist"):
            st.text_input("Add ticker", key="new_ticker", placeholder="e.g. TSLA", on_change=add_ticker)
            st.button("Add", on_click=add_ticker, disabled=not st.session_state.get("new_ticker", "").strip())
            if st.session_state.get("flash"):
                st.error(st.session_state.flash)
            if frames:
                to_remove = st.selectbox("Remove ticker", ["—"] + list(frames))
                if to_remove != "—" and st.button(f"Remove {to_remove}"):
                    db.remove_from_watchlist(to_remove)
                    st.rerun()
            st.markdown("**Popular tickers**")
            available = [t for t in universe.ALL if t not in frames]
            picks = st.multiselect("Pick from popular", available, format_func=universe.label)
            if st.button("Add selected", disabled=not picks):
                add_many(picks)
            starter = [t for t in universe.STARTER if t not in frames]
            if st.button("Add starter pack (stocks, ETFs, gold)", disabled=not starter):
                add_many(starter)

    with st.expander("🔔 Alerts"):
        threshold = st.slider("Daily move of at least (%)", 1.0, 10.0, 3.0, 0.5, key="alert_threshold") / 100
        found = stats.alerts(frames, threshold)
        if not found:
            st.caption("Nothing unusual right now.")
        for direction, t, text in found:
            st.markdown(f"{'🟢' if direction == 'up' else '🔴'} **{t}** {text}")

    show_ma50 = st.checkbox("50-bar average", value=True)
    show_ma200 = st.checkbox("200-bar average", value=True)
    if config.CLOUD:
        cloud_refresh()
    else:
        if st.toggle("Auto-refresh every 30 min", value=True, key="auto_refresh_on"):
            auto_refresh()
        if st.button("↻ Refresh prices now", use_container_width=True):
            with st.spinner("Updating..."):
                ingest.update_all()
                ingest.update_context()
                st.cache_data.clear()
            st.rerun()

if not frames:
    if config.CLOUD:
        st.error("Could not load the data snapshot. " + (cloud_error or "Run the refresh-data workflow on GitHub first."))
    else:
        st.info("The watchlist is empty. Add a ticker in the sidebar.")
    chat_widget({})
    st.stop()

# ---------- main ----------
ticker = st.session_state.selected
full = frames[ticker]
latest = full.iloc[-1]
change_1d = stats.one_day_change(full)
dollar_1d = latest["close"] - full["close"].iloc[-2] if len(full) > 1 else float("nan")

asof_text = f"Latest bar {full.index[-1]:%b %d, %Y} · Yahoo Finance, may be delayed"
if config.CLOUD and snap_meta:
    snap_age = pd.Timestamp.now("UTC") - pd.Timestamp(snap_meta["generated_at"])
    hours = snap_age.total_seconds() / 3600
    asof_text += f" · data snapshot {hours:.0f}h ago" if hours >= 1 else f" · data snapshot {int(snap_age.total_seconds() // 60)}m ago"
    if hours > 26:
        st.warning("The data job has not updated the snapshot in over a day, so prices and predictions may be stale.")

st.markdown(
    f'<div class="hero"><span class="tk">{ticker}</span><span class="asof">{universe.NAMES.get(ticker, "")}</span>'
    f'<span class="px">{latest["close"]:,.2f}</span>'
    f'<span class="pill {cls(change_1d)}">{dollar_1d:+,.2f} ({fmt_pct(change_1d)}) today</span>'
    f'<span class="asof">{asof_text}</span></div>',
    unsafe_allow_html=True,
)

ctl1, ctl2, ctl3 = st.columns([1.2, 1, 1])
with ctl1:
    timeframe = st.radio("Range", list(RANGES), index=3, horizontal=True)
with ctl2:
    horizon = st.radio("Outlook horizon", list(HORIZON_NAMES), index=1, horizontal=True, format_func=HORIZON_NAMES.get)
with ctl3:
    is_spy = ticker == "SPY"
    target = st.radio("Predict", list(TARGET_NAMES), horizontal=True, format_func=TARGET_NAMES.get,
                      disabled=is_spy, help="'Beats S&P 500' removes the market's general upward drift.")
    if is_spy:
        target = "up"
days = RANGES[timeframe]

spy_last = db.last_date("SPY")
ctx_asof = str(spy_last.date()) if spy_last is not None else ""
cols = st.columns([1, 1, 1, 1, 2.2])
for col, (label, value) in zip(cols[:4], [("1 week", stats.pct_change_since(full, 7)),
                                          ("1 month", stats.pct_change_since(full, 30)),
                                          ("Year to date", stats.pct_change_ytd(full)),
                                          ("1 year", stats.pct_change_since(full, 365))]):
    col.markdown(kpi_card(label, value), unsafe_allow_html=True)
outlook_slot = cols[4].empty()  # shimmering placeholder while the model trains; instant when cached
outlook_slot.markdown(style.skeleton(150, "Training the model…"), unsafe_allow_html=True)
outlook = run_outlook(ticker, horizon, target, str(full.index[-1].date()), ctx_asof)
if outlook is not None and not config.CLOUD:  # local runs log too; in cloud the data job does
    db.log_prediction(ticker, horizon, target, outlook.as_of.date(), outlook.prob_up, outlook.base_rate, outlook.verdict)
outlook_slot.markdown(outlook_card(outlook, horizon, target), unsafe_allow_html=True)
st.write("")

window = full if days is None else full[full.index >= full.index[-1] - pd.Timedelta(days=days)]
tab_chart, tab_pred, tab_score, tab_news, tab_fund, tab_hist, tab_compare, tab_screen = st.tabs(
    ["Chart", "Prediction", "Scoreboard", "News & events", "Fundamentals", "Price history", "Compare", "Screener"])

with tab_chart:
    chart_slot = st.empty()
    chart_slot.markdown(style.skeleton(420, "Loading chart data…"), unsafe_allow_html=True)
    intraday = load_intraday(ticker)
    chart_slot.empty()
    components.html(chart.build_html(ticker, full, intraday, days, show_ma50, show_ma200, height=600), height=610)
    limits = ("about 30 days of 5-minute and 1 year of hourly bars (no 1-minute bars on this site)" if config.CLOUD else
              "about 7 days of 1-minute, 60 days of 5-minute and 2 years of hourly data")
    st.caption("Scroll to zoom: zooming out switches to weekly and monthly bars, zooming in switches to hourly "
               f"and 5-minute bars. Drag to pan; Reset restores the starting view. Intraday history is limited: {limits}.")

with tab_pred:
    if outlook is None:
        st.info("Not enough data for a trustworthy test. The model needs about 4+ years of daily history "
                "(3 years to train before its first out-of-sample prediction, plus time to be scored)"
                + (", and S&P 500 data for the 'Beats S&P 500' setting." if target == "beat" else "."))
    else:
        o = outlook
        event = "closing higher" if o.target == "up" else "beating the S&P 500"
        headline = {
            "edge": "Out-of-sample, the model beat the naive baseline by more than luck easily explains. "
                    "Encouraging, but this is a rough statistical screen, not a guarantee.",
            "weak": "The model is slightly ahead of the naive baseline, but not by enough to rule out luck. "
                    "Treat the probability as a weak hint at most.",
            "none": "The model did no better than a naive guess. Treat the probability as roughly this stock's "
                    "normal rate, not as a forecast.",
        }[o.verdict]
        st.markdown(f"**{ticker}, {HORIZON_NAMES[o.horizon]} ahead: {o.prob_up:.0%} chance of {event}** "
                    f"(its normal rate is {o.base_rate:.0%}). {headline}")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Model accuracy", f"{o.accuracy:.1%}", f"{(o.accuracy - o.baseline_accuracy) * 100:+.1f} pts vs baseline",
                  help="Share of out-of-sample predictions where the model's call was right.")
        m2.metric("Naive baseline", f"{o.baseline_accuracy:.1%}",
                  help="Always guess the outcome that was most common in the training data.")
        m3.metric("AUC (0.5 = no skill)", f"{o.auc:.3f}",
                  help="How well the probabilities rank the good outcomes above the bad ones.")
        m4.metric("Calibration error (Brier)", f"{o.brier:.4f}", f"{o.brier - o.brier_baseline:+.4f} vs baseline",
                  delta_color="inverse", help="Lower is better. Negative means the model beat the baseline.")
        st.caption(f"{o.n_scored:,} out-of-sample predictions, about {o.n_effective:,.0f} independent after overlap. "
                   f"The event happened in {o.up_rate:.0%} of those periods.")

        cc = o.context_compare
        if cc:
            gain = cc["with_auc"] - cc["without_auc"]
            verdict_ctx = ("It helped." if gain > 0.01 and cc["with_brier"] < cc["without_brier"] else
                           "It made things worse." if gain < -0.01 and cc["with_brier"] > cc["without_brier"] else
                           "It made little difference.")
            st.markdown(f"**Did market context help?** With S&P 500, VIX, yield and dollar features: AUC "
                        f"{cc['with_auc']:.3f}, accuracy {cc['with_acc']:.1%}. Without them: AUC {cc['without_auc']:.3f}, "
                        f"accuracy {cc['without_acc']:.1%} ({cc['n']:,} shared predictions). {verdict_ctx}")

        left, right = st.columns(2)
        with left:
            st.markdown("**When the model said X%, how often did it happen?**")
            cal = o.calibration
            fig = go.Figure()
            fig.add_bar(x=cal["range"], y=cal["actual"], name="Actually happened", marker_color=BLUE,
                        text=[f"n={n}" for n in cal["n"]], textposition="outside")
            fig.add_scatter(x=cal["range"], y=cal["predicted"], mode="lines+markers",
                            name="Model's average guess", line=dict(color=AMBER, dash="dot"))
            fig.add_hline(y=o.up_rate, line_dash="dash", line_color="#94a3b8",
                          annotation_text="overall rate", annotation_position="bottom right")
            fig.update_yaxes(tickformat=".0%", range=[0, 1.1])
            fig.update_layout(**PLOT, height=340, legend=dict(orientation="h", y=-0.2))
            st.plotly_chart(fig, use_container_width=True)
            st.caption("A useful model's blue bars climb from left to right. Flat bars mean its confidence carries no information.")
        with right:
            st.markdown("**What is pushing today's number**")
            top = o.contributions.reindex(o.contributions.abs().sort_values(ascending=False).index)[:8][::-1]
            fig2 = go.Figure(go.Bar(x=top.values, y=[model.FEATURE_LABELS[k] for k in top.index], orientation="h",
                                    marker_color=[UP if v >= 0 else DOWN for v in top.values]))
            fig2.update_layout(**PLOT, height=340, xaxis_title="← lowers chance · raises chance →")
            st.plotly_chart(fig2, use_container_width=True)
            st.caption("Each indicator's contribution to the model's log-odds, relative to an average day.")

        st.markdown("**Its most recent scored calls (backtested)**")
        recent = o.history.tail(15).iloc[::-1]
        said_yes = recent["prob"] > 0.5
        st.dataframe(pd.DataFrame({
            "Date": recent.index.strftime("%Y-%m-%d"),
            "Chance": recent["prob"].map("{:.0%}".format),
            "Model said": np.where(said_yes, "Yes", "No"),
            f"Actual {HORIZON_NAMES[o.horizon]} {'return' if o.target == 'up' else 'excess return'}":
                recent["fwd"].map("{:+.2%}".format),
            "Right?": np.where(said_yes == (recent["y"] == 1), "✓", "✗"),
        }), hide_index=True, use_container_width=True)
        st.download_button("⬇ Download out-of-sample predictions (CSV)", o.history.to_csv(),
                           file_name=f"{ticker}_{o.target}_{o.horizon}d_predictions.csv", mime="text/csv")

        st.markdown("**Live track record** (predictions this app logged going forward; nothing can be backfilled)")
        track = tracking.score_log(ticker)
        done = track[track["resolved"]] if len(track) else track
        st.caption(f"{len(track)} predictions logged for {ticker}; {len(done)} have reached their horizon.")
        if len(done):
            hit = (done["correct"] == "✓").mean()
            st.metric("Live hit rate", f"{hit:.0%}", f"{len(done)} resolved", delta_color="off")
            st.dataframe(done.head(10)[["made_on", "horizon", "target", "prob", "realized", "correct"]]
                         .assign(made_on=lambda d: d["made_on"].dt.strftime("%Y-%m-%d"),
                                 prob=lambda d: d["prob"].map("{:.0%}".format),
                                 realized=lambda d: d["realized"].map("{:+.2%}".format)),
                         hide_index=True, use_container_width=True)
        else:
            st.caption("Results appear once logged predictions reach their horizon (days to weeks). Keep the app "
                       "open, or schedule refresh_job.py --predict, so each day gets logged.")

        if o.target == "up":
            st.markdown("**Paper test: hold the stock only when the model leans above its normal rate**")
            cost = st.slider("Trading cost per switch (basis points)", 0, 25, 5, key="bt_cost")
            bt = backtest.paper_trade(full, o, cost)
            if bt is None:
                st.caption("Not enough out-of-sample history for a paper test.")
            else:
                figb = go.Figure()
                for name in bt["equity"].columns:
                    figb.add_scatter(x=bt["equity"].index, y=bt["equity"][name], name=name,
                                     line=dict(width=2.4 if name == "Model rule" else 1.6))
                figb.update_layout(**PLOT, height=320, legend=dict(orientation="h"), yaxis_title="Growth of 1.0")
                st.plotly_chart(figb, use_container_width=True)
                st.dataframe(pd.DataFrame({
                    "": ["Model rule", "Buy and hold"],
                    "Total return": [f"{bt['model']['total']:+.0%}", f"{bt['hold']['total']:+.0%}"],
                    "Per year": [f"{bt['model']['annual']:+.1%}", f"{bt['hold']['annual']:+.1%}"],
                    "Max drawdown": [f"{bt['model']['max_drawdown']:.0%}", f"{bt['hold']['max_drawdown']:.0%}"],
                    "Sharpe": [f"{bt['model']['sharpe']:.2f}", f"{bt['hold']['sharpe']:.2f}"],
                }), hide_index=True, use_container_width=True)
                st.caption(f"Over {bt['years']:.1f} out-of-sample years the rule was invested {bt['time_in_market']:.0%} of "
                           f"the time with {bt['trades']} position changes. The rule was fixed in advance, so nothing "
                           "is tuned on this period. Cash earns 0%, and a single stock's result can still be luck.")

        with st.expander("How this works, and what it cannot tell you"):
            st.markdown(
                "- **Model:** logistic regression on 15 technical indicators plus 7 market-context features (S&P 500 "
                "trend, VIX, 10-year yield, dollar). Context features were chosen in advance, not by test score.\n"
                "- **Honest testing:** every scored prediction comes from a model trained only on outcomes already known "
                "at that time, retrained monthly, with a gap equal to the horizon. No peeking at the future.\n"
                "- **Baseline:** beating 50% means little for a stock that rises most of the time, so the model is compared "
                "with always guessing the usual outcome.\n"
                "- **News:** headlines are archived with a crude tone score, but the model does not use them yet. Testing "
                "whether they help needs months of archived history.\n"
                "- **Limits:** a good score on one stock can be luck. If you scan many tickers and keep the best one, "
                "expect some false winners. Research aid only, not financial advice."
            )

with tab_news:
    news_panel(ticker, full)
    st.markdown("### Earnings")
    past, upcoming = earnings_dates(ticker)
    if not past and upcoming is None:
        st.info("No earnings dates available (ETFs, indices and commodities do not report earnings).")
    else:
        if upcoming is not None:
            st.markdown(f"**Next earnings:** {upcoming:%A, %b %d, %Y}")
        study = events.earnings_reactions(full, past)
        if study["n"] < 3:
            st.caption("Too few past earnings dates to measure a typical reaction.")
        else:
            e1, e2, e3, e4 = st.columns(4)
            e1.metric("Typical move (2-day)", f"±{study['median_abs_move']:.1%}",
                      f"{study['median_abs_move'] / study['normal_abs_move']:.1f}× a normal 2-day move", delta_color="off")
            e2.metric("Rose after earnings", f"{study['share_positive']:.0%}", f"{study['n']} reports", delta_color="off")
            e3.metric("Biggest jump", fmt_pct(study["biggest_up"]))
            e4.metric("Biggest drop", fmt_pct(study["biggest_down"]))
            tbl = study["table"].head(8)
            st.dataframe(pd.DataFrame({"Report date": tbl["date"].dt.strftime("%Y-%m-%d"),
                                       "Move (close before → close after)": tbl["move"].map("{:+.2%}".format)}),
                         hide_index=True, use_container_width=True)
            st.caption("The 2-day window spans the report whether the company reports before or after the market "
                       "closes. Descriptive history, not a forecast.")

with tab_fund:
    info = fundamentals(ticker)
    if not info:
        st.info("No fundamentals available for this symbol (ETFs and commodities usually have none).")
    else:
        st.markdown(f"**{info.get('longName', ticker)}** · {info.get('sector', '–')} · {info.get('industry', '–')}")
        f1, f2, f3, f4 = st.columns(4)
        f1.metric("Market cap", fmt_big(info["marketCap"]) if "marketCap" in info else "–")
        f2.metric("P/E (trailing)", f"{info['trailingPE']:.1f}" if "trailingPE" in info else "–",
                  help="Price divided by the last 12 months of earnings per share.")
        f3.metric("P/E (forward)", f"{info['forwardPE']:.1f}" if "forwardPE" in info else "–",
                  help="Price divided by analysts' expected earnings per share.")
        f4.metric("Price / book", f"{info['priceToBook']:.1f}" if "priceToBook" in info else "–")
        f5, f6, f7, _ = st.columns(4)
        f5.metric("Profit margin", f"{info['profitMargins']:.1%}" if "profitMargins" in info else "–")
        f6.metric("Revenue growth", f"{info['revenueGrowth']:.1%}" if "revenueGrowth" in info else "–",
                  help="Year-over-year, most recent quarter.")
        f7.metric("Beta", f"{info['beta']:.2f}" if "beta" in info else "–", help="1.0 moves with the market.")
        st.caption("Fundamentals come from Yahoo Finance and can be stale or missing. Compare within the same "
                   "industry: a 'high' P/E for a bank can be normal for software.")

with tab_hist:
    st.caption("Statistics computed from this stock's past prices only. This is not news and it is not what drives "
               "the prediction (see the Prediction tab for that).")
    if len(window) < 2:
        st.warning("Not enough data in this range.")
    else:
        ev = stats.window_evidence(window, full)
        st.subheader(f"{ticker}: what happened over the last {timeframe}")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Period return", fmt_pct(ev["period_return"]))
        c2.metric("From 52-week high", fmt_pct(ev["from_52w_high"]))
        c3.metric("Max drawdown", fmt_pct(ev["max_drawdown"][0]))
        c4.metric("Up days", f"{ev['up_day_share']:.0%}")
        st.write(
            f"- **High** {ev['window_high'][0]:,.2f} on {ev['window_high'][1]:%Y-%m-%d}; "
            f"**low** {ev['window_low'][0]:,.2f} on {ev['window_low'][1]:%Y-%m-%d}\n"
            f"- **Best day** {fmt_pt(ev['best_day'])}; **worst day** {fmt_pt(ev['worst_day'])}\n"
            f"- **Max drawdown** bottomed on {ev['max_drawdown'][1]:%Y-%m-%d}\n"
            f"- **Typical daily swing** (std dev): {ev['daily_volatility']:.2%}"
        )
        st.subheader("After big one-day drops, what happened next?")
        drop = st.slider("Drop of at least (%)", 1.0, 10.0, 3.0, 0.5) / 100
        look = st.select_slider("Look ahead (trading days)", [1, 5, 10, 20, 60], value=5)
        study = stats.after_drop_study(full, drop, look)
        if study["n"] == 0:
            st.info("No days in this stock's history fell that much.")
        else:
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Occurrences", study["n"])
            m2.metric("Median next return", fmt_pct(study["median"]))
            m3.metric("Rose afterwards", f"{study['share_positive']:.0%}")
            m4.metric("Normal rate (any day)", f"{study['unconditional_share_positive']:.0%}")
            st.caption("Descriptive history, not a forecast. Drops cluster in crashes, so these samples overlap, "
                       "and small counts (under ~30) are mostly noise.")
    st.download_button("⬇ Download prices (CSV)", full.to_csv(), file_name=f"{ticker}_prices.csv", mime="text/csv")

with tab_compare:
    st.subheader(f"Performance rebased to 100 ({timeframe})")
    default = [t for t in dict.fromkeys([ticker, "SPY", "QQQ", "GC=F"]) if t in frames]
    chosen = st.multiselect("Compare", list(frames), default=default)
    fig3 = go.Figure()
    for t in chosen:
        df = frames[t]
        w = df if days is None else df[df.index >= df.index[-1] - pd.Timedelta(days=days)]
        if len(w) > 1:
            fig3.add_trace(go.Scatter(x=w.index, y=w["adj_close"] / w["adj_close"].iloc[0] * 100, name=t,
                                      line=dict(width=3 if t == ticker else 1.6)))
    fig3.update_layout(**PLOT, height=500, legend=dict(orientation="h"))
    st.plotly_chart(fig3, use_container_width=True)

with tab_screen:
    st.caption(f"Runs the model on every watchlist stock for the {HORIZON_NAMES[horizon]} horizon (target: goes up). "
               "Ranking many stocks and trusting the top one invites false winners, so check each row's verdict.")
    if st.button("Run screener", key="run_screen"):
        rows, bar = [], st.progress(0.0)
        for i, (t, df) in enumerate(frames.items()):
            o_t = run_outlook(t, horizon, "up", str(df.index[-1].date()), ctx_asof, False)
            if o_t is not None:
                rows.append({"Ticker": t, "Chance": o_t.prob_up, "Normal": o_t.base_rate,
                             "Tilt": (o_t.prob_up - o_t.base_rate) * 100, "Verdict": o_t.verdict,
                             "AUC": o_t.auc, "Edge": (o_t.accuracy - o_t.baseline_accuracy) * 100})
            bar.progress((i + 1) / len(frames))
        bar.empty()
        st.session_state.screen = (horizon, pd.DataFrame(rows))
    screen = st.session_state.get("screen")
    if screen is not None:
        h_done, res = screen
        if res.empty:
            st.info("No stock had enough history for a scorecard.")
        else:
            res = res.sort_values("Tilt", ascending=False)
            names = {"edge": "Edge detected", "weak": "Edge unproven", "none": "No proven edge"}
            st.dataframe(pd.DataFrame({
                "Ticker": res["Ticker"], "Chance of rising": res["Chance"].map("{:.0%}".format),
                "Normal rate": res["Normal"].map("{:.0%}".format), "Tilt (pts)": res["Tilt"].map("{:+.0f}".format),
                "Verdict": res["Verdict"].map(names), "AUC": res["AUC"].map("{:.3f}".format),
                "Accuracy vs naive (pts)": res["Edge"].map("{:+.1f}".format)}),
                hide_index=True, use_container_width=True)
            st.caption(f"Results for the {HORIZON_NAMES[h_done]} horizon. Sorted by tilt versus each stock's own normal rate.")

with tab_score:
    st.markdown("**Is the model reliable? This grades predictions that were logged _before_ their outcomes were known.**")
    log_all = tracking.score_log(None)
    done_all = log_all[log_all["resolved"]] if len(log_all) else log_all
    n_tickers = log_all["ticker"].nunique() if len(log_all) else 0
    st.caption(f"{len(log_all)} predictions logged across {n_tickers} tickers; {len(done_all)} have reached their horizon. "
               "Each prediction is graded against what the stock actually did, and against a naive guess "
               "(always guessing the stock's usual direction).")
    summ = tracking.summarize(done_all)
    if summ is None:
        st.info("No graded predictions yet. 1-week predictions are graded about a week after they are logged. "
                "Expect to need several months of results before drawing any conclusion.")
    else:
        s1, s2, s3 = st.columns(3)
        s1.metric("Model hit rate", f"{summ['model']:.1%}", f"{(summ['model'] - summ['naive']) * 100:+.1f} pts vs naive")
        s2.metric("Naive hit rate", f"{summ['naive']:.1%}")
        s3.metric("Graded predictions", f"{summ['n']:,}")
        for title, key in (("By horizon (trading days)", "by_horizon"), ("By model verdict", "by_verdict"),
                           ("By ticker", "by_ticker")):
            tbl = summ[key].reset_index()
            st.markdown(f"**{title}**")
            st.dataframe(pd.DataFrame({tbl.columns[0]: tbl.iloc[:, 0].astype(str), "Graded": tbl["n"],
                                       "Model": tbl["model"].map("{:.0%}".format),
                                       "Naive": tbl["naive"].map("{:.0%}".format)}),
                         hide_index=True, use_container_width=True)
        st.caption("Read with care: predictions for different stocks move together with the market, and consecutive "
                   "days share most of their outcome window, so the number of truly independent results is far "
                   "smaller than the count above. A gap of a few points over a few weeks is noise.")

st.caption("Research tool only. Nothing here is financial advice.")

chat_widget({
    "Selected ticker": f"{ticker} {universe.NAMES.get(ticker, '')}".strip(),
    "Last close": f"{latest['close']:,.2f} ({fmt_pct(change_1d)} today)",
    "Chart range": timeframe,
    "Outlook": (f"{outlook.prob_up:.0%} chance of {'closing higher' if outlook.target == 'up' else 'beating the S&P 500'} "
                f"in {HORIZON_NAMES[horizon]}; normal rate {outlook.base_rate:.0%}; verdict {outlook.verdict}; "
                f"model accuracy {outlook.accuracy:.0%} vs {outlook.baseline_accuracy:.0%} naive") if outlook else "not available",
})
