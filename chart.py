"""Scroll-to-zoom candlestick chart that swaps bar size as you zoom.

Streamlit's built-in Plotly chart cannot tell Python that the user zoomed, so this renders
TradingView's open-source Lightweight Charts inside an iframe and does the zoom logic in
JavaScript. All bar sizes are shipped to the browser up front; zooming just swaps datasets.

Needs internet access in the browser (loads the chart library from unpkg and fonts from Google).
"""
import json

import pandas as pd

UP, DOWN = "#34d399", "#fb7185"
EPOCH = pd.Timestamp("1970-01-01")


def aggregate(daily: pd.DataFrame, key: str) -> pd.DataFrame:
    """Daily bars -> weekly ('1wk', stamped Monday) or monthly ('1mo', stamped 1st)."""
    if key == "1wk":
        grouped = daily.resample("W-MON", label="left", closed="left")
    else:
        grouped = daily.resample("MS")
    out = grouped.agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
    return out.dropna(subset=["close"])


def to_bars(df: pd.DataFrame | None) -> list:
    """[[unix_seconds, open, high, low, close, volume], ...] (times are exchange-local wall clock)."""
    if df is None or df.empty:
        return []
    df = df.dropna(subset=["open", "high", "low", "close"])
    seconds = ((df.index - EPOCH) // pd.Timedelta(seconds=1)).tolist()
    return [
        [int(t), o, h, l, c, int(v)]
        for t, o, h, l, c, v in zip(
            seconds,
            df["open"].round(4).tolist(),
            df["high"].round(4).tolist(),
            df["low"].round(4).tolist(),
            df["close"].round(4).tolist(),
            df["volume"].fillna(0).tolist(),
        )
    ]


def build_html(ticker, daily, intraday, initial_days, ma50=True, ma200=True, height=560) -> str:
    data = {
        "1m": to_bars(intraday.get("1m")),
        "5m": to_bars(intraday.get("5m")),
        "1h": to_bars(intraday.get("1h")),
        "1d": to_bars(daily[["open", "high", "low", "close", "volume"]]),
        "1wk": to_bars(aggregate(daily, "1wk")),
        "1mo": to_bars(aggregate(daily, "1mo")),
    }
    payload = {
        "ticker": ticker, "initialDays": initial_days, "ma50": ma50, "ma200": ma200,
        "up": UP, "down": DOWN, "upA": "rgba(52,211,153,0.32)", "downA": "rgba(251,113,133,0.32)",
        "data": data,
    }
    return (
        TEMPLATE.replace("__PAYLOAD__", json.dumps(payload, separators=(",", ":")))
        .replace("__HEIGHT__", str(int(height)))
    )


TEMPLATE = r"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  html,body{margin:0;padding:0;background:transparent;font-family:'Plus Jakarta Sans',system-ui,sans-serif;}
  #wrap{position:relative;width:100%;height:__HEIGHT__px;border-radius:16px;overflow:hidden;
        background:linear-gradient(180deg,#101728 0%,#0b111d 100%);border:1px solid rgba(255,255,255,.07);box-sizing:border-box;}
  #chart{position:absolute;inset:0;}
  #legend{position:absolute;left:16px;top:12px;z-index:5;color:#aeb9cc;font-size:12px;line-height:1.55;pointer-events:none;}
  #legend .tk{font-weight:700;font-size:16px;color:#fff;margin-right:8px;}
  #legend .res{background:rgba(96,165,250,.16);color:#93c5fd;border-radius:999px;padding:2px 9px;font-weight:700;font-size:11px;}
  #legend .mono{font-family:'JetBrains Mono',ui-monospace,monospace;}
  #legend .note{color:#fbbf24;margin-left:8px;}
  #reset{position:absolute;right:84px;top:10px;z-index:6;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12);color:#cbd5e1;border-radius:8px;font-size:11px;padding:4px 10px;cursor:pointer;font-family:inherit;}
  #reset:hover{background:rgba(255,255,255,.13);}
  @keyframes wipe{from{clip-path:inset(0 100% 0 0);}to{clip-path:inset(0 0 0 0);}}
  @keyframes fadeIn{from{opacity:0;}to{opacity:1;}}
  @keyframes swap{0%{opacity:.4;}100%{opacity:1;}}
  #chart{animation:wipe 1s cubic-bezier(.22,1,.36,1) backwards;}
  #legend{animation:fadeIn .8s ease .3s backwards;}
  #wrap.swap{animation:swap .3s ease-out;}
  @media (prefers-reduced-motion: reduce){*{animation:none !important;}}
  #hint{position:absolute;right:16px;bottom:8px;z-index:5;color:#64708a;font-size:11px;pointer-events:none;}
  #err{color:#fca5a5;padding:24px;font-size:14px;}
</style>
<script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
</head><body>
<div id="wrap"><div id="legend"></div><button id="reset" title="Back to the starting zoom">↺ Reset</button><div id="chart"></div><div id="hint">scroll to zoom · drag to pan</div></div>
<script>
(function () {
  const P = __PAYLOAD__;
  const wrap = document.getElementById('wrap');
  if (typeof LightweightCharts === 'undefined') {
    wrap.innerHTML = '<div id="err">The chart library could not be loaded. This chart needs internet access (unpkg.com).</div>';
    return;
  }

  const DAY = 86400;
  // maxSpan = widest visible time range (seconds) at which this bar size is used.
  const RES = [
    {key:'1m',  label:'1-minute bars', maxSpan:1.5*DAY,    barSec:60,       intraday:true},
    {key:'5m',  label:'5-minute bars', maxSpan:6*DAY,      barSec:300,      intraday:true},
    {key:'1h',  label:'Hourly bars',   maxSpan:45*DAY,     barSec:3600,     intraday:true},
    {key:'1d',  label:'Daily bars',    maxSpan:3*365*DAY,  barSec:DAY,      intraday:false},
    {key:'1wk', label:'Weekly bars',   maxSpan:12*365*DAY, barSec:7*DAY,    intraday:false},
    {key:'1mo', label:'Monthly bars',  maxSpan:Infinity,    barSec:31*DAY,   intraday:false},
  ];
  RES.forEach(r => { r.raw = P.data[r.key] || []; r.cache = null; });
  const DAILY = 3;
  if (!RES[DAILY].raw.length) { wrap.innerHTML = '<div id="err">No price data.</div>'; return; }

  function sma(raw, n) {
    const out = []; let sum = 0;
    for (let i = 0; i < raw.length; i++) {
      sum += raw[i][4];
      if (i >= n) sum -= raw[i - n][4];
      if (i >= n - 1) out.push({time: raw[i][0], value: sum / n});
    }
    return out;
  }
  function prepare(r) {
    if (r.cache) return r.cache;
    r.cache = {
      candles: r.raw.map(b => ({time:b[0], open:b[1], high:b[2], low:b[3], close:b[4]})),
      volume:  r.raw.map(b => ({time:b[0], value:b[5], color: b[4] >= b[1] ? P.upA : P.downA})),
      ma50: sma(r.raw, 50), ma200: sma(r.raw, 200),
    };
    return r.cache;
  }

  let cur = DAILY, limited = false;
  const fmt = n => n.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
  function fmtTime(t) {
    // Times are exchange-local wall clock stored as if UTC, so always format with timeZone 'UTC'.
    const d = new Date(t * 1000);
    const date = d.toLocaleDateString('en-US', {timeZone:'UTC', year:'numeric', month:'short', day:'numeric'});
    if (!RES[cur] || !RES[cur].intraday) return date;
    return date + ' ' + d.toLocaleTimeString('en-US', {timeZone:'UTC', hour:'2-digit', minute:'2-digit', hour12:false});
  }

  const chart = LightweightCharts.createChart(document.getElementById('chart'), {
    autoSize: true,
    layout: {background:{type:'solid', color:'transparent'}, textColor:'#8b97ad',
             fontFamily:"'JetBrains Mono', ui-monospace, monospace", fontSize: 11},
    grid: {vertLines:{color:'rgba(255,255,255,0.035)'}, horzLines:{color:'rgba(255,255,255,0.035)'}},
    rightPriceScale: {borderVisible:false, scaleMargins:{top:0.14, bottom:0.25}},
    timeScale: {borderVisible:false, timeVisible:false, secondsVisible:false, fixLeftEdge:true, rightOffset:3},
    crosshair: {mode: LightweightCharts.CrosshairMode.Normal,
                vertLine:{color:'rgba(148,163,184,.45)', labelBackgroundColor:'#1e293b'},
                horzLine:{color:'rgba(148,163,184,.45)', labelBackgroundColor:'#1e293b'}},
    localization: {timeFormatter: fmtTime},
  });
  const candle = chart.addCandlestickSeries({upColor:P.up, downColor:P.down, borderVisible:false,
                                             wickUpColor:P.up, wickDownColor:P.down});
  const volume = chart.addHistogramSeries({priceFormat:{type:'volume'}, priceScaleId:'',
                                           lastValueVisible:false, priceLineVisible:false});
  chart.priceScale('').applyOptions({scaleMargins:{top:0.8, bottom:0}});
  const lineOpts = c => ({color:c, lineWidth:1, priceLineVisible:false, lastValueVisible:false, crosshairMarkerVisible:false});
  const ma50 = chart.addLineSeries(lineOpts('#fbbf24'));
  const ma200 = chart.addLineSeries(lineOpts('#a78bfa'));

  const legend = document.getElementById('legend');
  function updateLegend(param) {
    const c = prepare(RES[cur]).candles;
    let bar = null;
    if (param && param.time && param.seriesData) bar = param.seriesData.get(candle);
    if (!bar) bar = c[c.length - 1];
    if (!bar) return;
    const up = bar.close >= bar.open, col = up ? P.up : P.down;
    const note = limited ? '<span class="note">Finer bars aren\u2019t available this far back (Yahoo keeps ~7d of 1-min, ~60d of 5-min, ~2y of hourly)</span>' : '';
    legend.innerHTML =
      '<span class="tk">' + P.ticker + '</span><span class="res">' + RES[cur].label + '</span>' + note + '<br>' +
      '<span class="mono">O ' + fmt(bar.open) + '  H ' + fmt(bar.high) + '  L ' + fmt(bar.low) +
      '  C <span style="color:' + col + '">' + fmt(bar.close) + '</span></span>';
  }
  chart.subscribeCrosshairMove(updateLegend);

  function covers(r, from) { return r.raw.length > 0 && from >= r.raw[0][0] - 2 * r.barSec; }

  // Pick a bar size for the visible range. Hysteresis (5%) stops flip-flopping at a boundary.
  function pick(from, to) {
    const span = to - from;
    let i = cur;
    while (i < RES.length - 1 && span > RES[i].maxSpan * 1.05) i++;
    while (i > 0 && span < RES[i - 1].maxSpan * 0.95) i--;
    const wanted = i;
    while (i < RES.length - 1 && !covers(RES[i], from)) i++;   // no data that far back: go coarser
    return {idx: i, wanted: wanted};
  }

  function apply(i, range) {
    cur = i;
    const r = RES[i], c = prepare(r);
    chart.applyOptions({timeScale: {timeVisible: r.intraday}});
    candle.setData(c.candles);
    volume.setData(c.volume);
    ma50.setData(P.ma50 ? c.ma50 : []);
    ma200.setData(P.ma200 ? c.ma200 : []);
    if (range) { try { chart.timeScale().setVisibleRange(range); } catch (e) {} }
  }

  function pulse() {  // brief fade when the bar size changes, so the data swap is not a hard cut
    if (!wrap.classList) return;
    wrap.classList.remove('swap'); void wrap.offsetWidth; wrap.classList.add('swap');
  }

  let timer = null;
  function evaluate() {
    const vr = chart.timeScale().getVisibleRange();
    if (!vr) return;
    const p = pick(vr.from, vr.to);
    limited = p.idx > p.wanted && RES[p.wanted].intraday;
    if (p.idx !== cur) {
      const prev = RES[cur];
      // Going finer: stretch the right edge so the last coarse bar's whole period stays in view.
      const to = p.idx < cur ? vr.to + prev.barSec : vr.to;
      apply(p.idx, {from: vr.from, to: to});
      pulse();
    }
    updateLegend(null);
  }
  chart.timeScale().subscribeVisibleTimeRangeChange(() => {
    clearTimeout(timer);
    timer = setTimeout(evaluate, 120);
  });

  // Initial view (also used by the Reset button)
  function initialView() {
    const daily = RES[DAILY].raw;
    const firstT = daily[0][0], lastT = daily[daily.length - 1][0] + DAY;
    const from = P.initialDays ? Math.max(firstT, lastT - P.initialDays * DAY) : firstT;
    const start = pick(from, lastT);
    limited = start.idx > start.wanted && RES[start.wanted].intraday;
    apply(start.idx, {from: from, to: lastT});
    updateLegend(null);
  }
  document.getElementById('reset').addEventListener('click', initialView);
  initialView();
})();
</script></body></html>
"""
