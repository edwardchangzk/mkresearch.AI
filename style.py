"""Look and feel: fonts, colours, cards. Purely cosmetic; safe to tweak."""
import streamlit as st

UP, DOWN, AMBER, BLUE = "#34d399", "#fb7185", "#fbbf24", "#60a5fa"

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');
:root { --card: rgba(255,255,255,0.035); --line: rgba(255,255,255,0.07); --muted: #8b97ad;
        --up: #34d399; --down: #fb7185; --amber: #fbbf24; --blue: #60a5fa; }

.stApp {
  background:
    radial-gradient(1100px 560px at 8% -8%, rgba(52,211,153,.11), transparent 60%),
    radial-gradient(900px 520px at 100% 0%, rgba(96,165,250,.11), transparent 55%),
    #0b0f19;
}
/* Fonts: listed selectors only (a blanket * would break Streamlit's icon font) */
html, body, .stApp, .stApp p, .stApp label, .stApp li, .stApp h1, .stApp h2, .stApp h3, .stApp h4,
.stApp button, .stApp input, .stApp textarea, [data-testid="stMarkdownContainer"],
[data-testid="stMetricLabel"], [data-testid="stMetricValue"], [data-testid="stCaptionContainer"] {
  font-family: 'Plus Jakarta Sans', system-ui, -apple-system, 'Segoe UI', sans-serif;
}
[data-testid="stMetricValue"], .mono { font-family: 'JetBrains Mono', ui-monospace, Consolas, monospace; }
header[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 1.4rem; max-width: 1500px; }

/* Sidebar */
[data-testid="stSidebar"] { background: linear-gradient(180deg, #0e1424, #0a0e18); border-right: 1px solid var(--line); }
.brand { font-weight: 800; font-size: 1.15rem; letter-spacing: -.01em; margin: 2px 0 12px; }
.brand span { color: var(--up); }
.sec { font-size: .72rem; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; margin: 14px 0 6px; }
.sec.up { color: var(--up); } .sec.down { color: var(--down); } .sec.muted { color: var(--muted); }
[data-testid="stSidebar"] .stButton > button {
  width: 100%; justify-content: flex-start; text-align: left; background: var(--card);
  border: 1px solid var(--line); border-radius: 12px; padding: .5rem .8rem; transition: .15s;
}
[data-testid="stSidebar"] .stButton > button p { text-align: left; width: 100%; margin: 0; white-space: nowrap; }
[data-testid="stSidebar"] .stButton > button:hover { border-color: rgba(96,165,250,.55); background: rgba(96,165,250,.08); }
[data-testid="stSidebar"] .stButton > button[kind="primary"],
[data-testid="stSidebar"] button[data-testid="stBaseButton-primary"] {
  background: linear-gradient(135deg, rgba(52,211,153,.20), rgba(96,165,250,.20)); border-color: rgba(52,211,153,.6);
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] { gap: 6px; border-bottom: 1px solid var(--line); }
.stTabs [data-baseweb="tab"] { height: 44px; padding: 0 16px; color: var(--muted); font-weight: 600; }
.stTabs [aria-selected="true"] { color: #fff; }

/* Hero + cards */
.hero { display: flex; align-items: baseline; gap: 18px; flex-wrap: wrap; margin: 2px 0 16px; }
.hero .tk { font-size: 2.7rem; font-weight: 800; letter-spacing: -.03em; line-height: 1;
            background: linear-gradient(90deg, #ffffff, #9fb3d9); -webkit-background-clip: text; background-clip: text; color: transparent; }
.hero .px { font-family: 'JetBrains Mono', monospace; font-size: 2rem; font-weight: 500; }
.hero .asof { color: var(--muted); font-size: .8rem; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 16px; padding: 14px 16px; height: 100%; box-sizing: border-box; }
.klabel { color: var(--muted); font-size: .7rem; letter-spacing: .09em; text-transform: uppercase; font-weight: 700; }
.kvalue { font-family: 'JetBrains Mono', monospace; font-size: 1.5rem; font-weight: 600; margin-top: 6px; }
.ksub { color: var(--muted); font-size: .76rem; margin-top: 6px; line-height: 1.45; }
.up { color: var(--up); } .down { color: var(--down); }
.pill { display: inline-block; padding: 3px 11px; border-radius: 999px; font-size: .74rem; font-weight: 700; }
.pill.up { background: rgba(52,211,153,.14); } .pill.down { background: rgba(251,113,133,.14); }
.pill.warn { background: rgba(251,191,36,.14); color: var(--amber); }
.pill.muted { background: rgba(148,163,184,.14); color: #cbd5e1; }
.outlook .big { font-family: 'JetBrains Mono', monospace; font-size: 2.1rem; font-weight: 600; margin: 4px 0 2px; }

/* News list */
.news { padding: 10px 2px; border-bottom: 1px solid var(--line); }
.news a { color: #e5e7eb; text-decoration: none; font-weight: 600; }
.news a:hover { color: var(--blue); }
.news .meta { color: var(--muted); font-size: .76rem; margin-top: 3px; }
.dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 8px; background: #64748b; }
.dot.positive { background: var(--up); } .dot.negative { background: var(--down); }

/* Chat widget: a round button fixed bottom-right that slides a panel up; the chevron slides it back down */
.st-key-chat_fab { position: fixed; right: 24px; bottom: 24px; z-index: 1000002; width: auto !important; }
.st-key-chat_fab button { width: 58px; height: 58px; min-height: 58px; border-radius: 50%; padding: 0; border: none;
  background: linear-gradient(135deg, #34d399, #60a5fa); box-shadow: 0 10px 30px rgba(52,211,153,.35);
  transition: transform .2s ease, box-shadow .2s ease; }
.st-key-chat_fab button p { font-size: 1.45rem; margin: 0; color: #08111f; }
.st-key-chat_fab button:hover { transform: scale(1.08); box-shadow: 0 14px 36px rgba(96,165,250,.45); }
.st-key-chat_panel { position: fixed; right: 24px; bottom: 98px; width: 390px; max-width: calc(100vw - 32px);
  z-index: 1000001; background: #0f1524; border: 1px solid rgba(255,255,255,.1); border-radius: 20px;
  padding: 14px 14px 10px; box-shadow: 0 24px 60px rgba(0,0,0,.55); }
.st-key-chat_panel .chat-title { font-weight: 800; font-size: 1rem; }
.st-key-chat_panel .chat-sub { color: var(--muted); font-size: .72rem; }
.st-key-chat_close button { border-radius: 10px; padding: 0 8px; min-height: 34px; background: var(--card); border: 1px solid var(--line); }

/* ================= Motion ================= */
/* Rule of thumb: ancestors of the fixed chat widget only ever get OPACITY animations (a transform on an ancestor
   would break position: fixed). Transform animations are limited to leaf elements such as cards and charts. */
@keyframes fadeUp   { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: none; } }
@keyframes fadeIn   { from { opacity: 0; } to { opacity: 1; } }
@keyframes slideIn  { from { opacity: 0; transform: translateX(-16px); } to { opacity: 1; transform: none; } }
@keyframes wipe     { from { clip-path: inset(0 100% 0 0); } to { clip-path: inset(0 0 0 0); } }
@keyframes orbA     { 0% { transform: translate3d(0,0,0) scale(1); } 50% { transform: translate3d(7vw,6vh,0) scale(1.12); } 100% { transform: translate3d(0,0,0) scale(1); } }
@keyframes orbB     { 0% { transform: translate3d(0,0,0) scale(1.05); } 50% { transform: translate3d(-8vw,-5vh,0) scale(.94); } 100% { transform: translate3d(0,0,0) scale(1.05); } }
@keyframes shimmer  { 0% { background-position: 100% 50%; } 100% { background-position: 0 50%; } }
@keyframes bars     { 0%, 100% { height: 6px; opacity: .55; } 50% { height: 22px; opacity: 1; } }
@keyframes pulseGlow { 0%, 100% { box-shadow: 0 10px 30px rgba(52,211,153,.30); } 50% { box-shadow: 0 10px 44px rgba(96,165,250,.55); } }

/* Animated background: two slow-drifting colour orbs behind everything */
.stApp { isolation: isolate; }
.stApp::before, .stApp::after { content: ""; position: fixed; z-index: -1; pointer-events: none; border-radius: 50%; will-change: transform; }
.stApp::before { width: 62vw; height: 62vw; left: -14vw; top: -22vw;
  background: radial-gradient(closest-side, rgba(52,211,153,.17), transparent); animation: orbA 26s ease-in-out infinite; }
.stApp::after  { width: 56vw; height: 56vw; right: -16vw; top: 10vh;
  background: radial-gradient(closest-side, rgba(96,165,250,.16), transparent); animation: orbB 32s ease-in-out infinite; }

/* Content entrance */
.hero, .card, .news { animation: fadeUp .55s cubic-bezier(.22,1,.36,1) backwards; }
.news { animation-delay: calc(var(--i, 0) * 45ms); }
[data-testid="stColumn"]:nth-child(2) .card { animation-delay: .06s; }
[data-testid="stColumn"]:nth-child(3) .card { animation-delay: .12s; }
[data-testid="stColumn"]:nth-child(4) .card { animation-delay: .18s; }
[data-testid="stColumn"]:nth-child(5) .card { animation-delay: .24s; }
[data-testid="stMetric"] { animation: fadeUp .5s cubic-bezier(.22,1,.36,1) backwards; }
[data-testid="stPlotlyChart"] { animation: wipe 1.1s cubic-bezier(.22,1,.36,1) backwards; }
[data-testid="stDataFrame"] { animation: fadeIn .6s ease backwards; }
[data-baseweb="tab-panel"] { animation: fadeUp .45s cubic-bezier(.22,1,.36,1) backwards; }
.stTabs [data-baseweb="tab"] { transition: color .2s ease; }
.stTabs [data-baseweb="tab-highlight"] { transition: all .35s cubic-bezier(.22,1,.36,1); }
[data-testid="stSidebar"] .stButton { animation: slideIn .45s cubic-bezier(.22,1,.36,1) backwards; }
[data-testid="stSidebar"] .stButton:nth-of-type(1) { animation-delay: 28ms; }
[data-testid="stSidebar"] .stButton:nth-of-type(2) { animation-delay: 56ms; }
[data-testid="stSidebar"] .stButton:nth-of-type(3) { animation-delay: 84ms; }
[data-testid="stSidebar"] .stButton:nth-of-type(4) { animation-delay: 112ms; }
[data-testid="stSidebar"] .stButton:nth-of-type(5) { animation-delay: 140ms; }
[data-testid="stSidebar"] .stButton:nth-of-type(6) { animation-delay: 168ms; }
[data-testid="stSidebar"] .stButton:nth-of-type(7) { animation-delay: 196ms; }
[data-testid="stSidebar"] .stButton:nth-of-type(8) { animation-delay: 224ms; }
[data-testid="stSidebar"] .stButton:nth-of-type(9) { animation-delay: 252ms; }
[data-testid="stSidebar"] .stButton:nth-of-type(10) { animation-delay: 280ms; }
[data-testid="stSidebar"] .stButton:nth-of-type(11) { animation-delay: 308ms; }
[data-testid="stSidebar"] .stButton:nth-of-type(12) { animation-delay: 336ms; }
[data-testid="stSidebar"] .stButton:nth-of-type(13) { animation-delay: 364ms; }
[data-testid="stSidebar"] .stButton:nth-of-type(14) { animation-delay: 392ms; }
[data-testid="stSidebar"] .stButton:nth-of-type(15) { animation-delay: 420ms; }
[data-testid="stSidebar"] .stButton:nth-of-type(16) { animation-delay: 448ms; }
[data-testid="stSidebar"] .stButton:nth-of-type(17) { animation-delay: 476ms; }
[data-testid="stSidebar"] .stButton:nth-of-type(18) { animation-delay: 504ms; }
[data-testid="stSidebar"] .stButton:nth-of-type(19) { animation-delay: 532ms; }
[data-testid="stSidebar"] .stButton:nth-of-type(20) { animation-delay: 560ms; }
[data-testid="stSidebar"] .stButton:nth-of-type(21) { animation-delay: 588ms; }
[data-testid="stSidebar"] .stButton:nth-of-type(22) { animation-delay: 616ms; }
.card { transition: transform .25s ease, border-color .25s ease, background .25s ease; }
.card:hover { transform: translateY(-3px); border-color: rgba(96,165,250,.35); background: rgba(255,255,255,.055); }
.news { transition: background .2s ease; } .news:hover { background: rgba(255,255,255,.03); }
.st-key-chat_fab button { animation: pulseGlow 3.2s ease-in-out infinite; }

/* Loading states: bouncing bars + shimmering skeleton blocks */
.loader { display: flex; align-items: center; gap: 14px; padding: 18px 20px; border: 1px solid var(--line);
  border-radius: 16px; background: var(--card); color: var(--muted); font-weight: 600; animation: fadeIn .3s ease; }
.loader .bars { display: flex; gap: 4px; align-items: flex-end; height: 22px; }
.loader .bars i { display: block; width: 4px; height: 6px; border-radius: 2px; background: linear-gradient(var(--up), var(--blue)); animation: bars 1s ease-in-out infinite; }
.loader .bars i:nth-child(2) { animation-delay: .12s; } .loader .bars i:nth-child(3) { animation-delay: .24s; }
.loader .bars i:nth-child(4) { animation-delay: .36s; } .loader .bars i:nth-child(5) { animation-delay: .48s; }
.skeleton { border-radius: 16px; border: 1px solid var(--line);
  background: linear-gradient(90deg, rgba(255,255,255,.035) 25%, rgba(255,255,255,.09) 37%, rgba(255,255,255,.035) 63%);
  background-size: 400% 100%; animation: shimmer 1.5s ease infinite; }
.skeleton .loader { background: transparent; border: none; }

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; }
}
</style>
"""


def inject():
    st.markdown(CSS, unsafe_allow_html=True)


CHAT_OPEN = """<style>
.st-key-chat_panel { transform: translateY(0); opacity: 1; visibility: visible; pointer-events: auto;
  transition: transform .42s cubic-bezier(.22,1,.36,1), opacity .3s ease, visibility 0s; }
</style>"""
CHAT_CLOSED = """<style>
.st-key-chat_panel { transform: translateY(calc(100% + 140px)); opacity: 0; visibility: hidden; pointer-events: none;
  transition: transform .42s cubic-bezier(.22,1,.36,1), opacity .3s ease, visibility 0s linear .42s; }
</style>"""


def loader(message: str) -> str:
    return f'<div class="loader"><div class="bars"><i></i><i></i><i></i><i></i><i></i></div><span>{message}</span></div>'


def skeleton(height: int, message: str = "") -> str:
    inner = loader(message) if message else ""
    return f'<div class="skeleton" style="height:{int(height)}px">{inner}</div>'
