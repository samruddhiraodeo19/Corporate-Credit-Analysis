"""
Builds the interactive credit dashboard (PLAN Phase 7, viewable form).

Usage:
    python src/build_dashboard.py

Produces output/dashboard.html -- a single self-contained file, no server and
no dependencies, that renders the same three pages the Power BI build guide
specifies:

    1. Portfolio Overview   grade/watchlist matrix + the leverage-vs-coverage
                            scatter that tells most of the story
    2. Company Deep Dive    eight-quarter trends, triggers, stress results
    3. Stress Test Matrix   company x scenario heatmap of covenant breaches

`build_powerbi.py` produces the model for Power BI Desktop, which is
Windows-only; this renders the same analysis anywhere a browser runs, so the
dashboard can actually be looked at and checked against the numbers.

Charting notes (the palette is the data-viz skill's validated default):
  * Severity is NEVER carried by colour alone. The status ramp fails the
    categorical separation checks by design -- green vs red measures dE 4.1
    under simulated deuteranopia -- so every severity-coded mark also carries a
    distinct shape and a direct text label, which is the documented mitigation.
  * The heatmap uses one blue hue light-to-dark for magnitude (never a rainbow)
    and marks covenant breaches with a separate status ring plus a value in
    every cell, so breach state and leverage size stay independently readable.
  * Trend panels are single-series, so they take slot 1 and need no legend --
    the panel title names the series.
"""
import json
import sys
from pathlib import Path

import pandas as pd

from config import (
    ALTMAN_ZPP_DISTRESS,
    DEBT_EBITDA_COVENANT,
    MIN_CURRENT_RATIO,
    MIN_INTEREST_COVERAGE,
)

OUTPUT_DIR = Path(__file__).parent.parent / "output"
DASHBOARD_PATH = OUTPUT_DIR / "dashboard.html"

TREND_PANELS = [
    ("debt_to_ebitda", "Debt / EBITDA", "x"),
    ("interest_coverage", "EBITDA / interest", "x"),
    ("operating_margin", "Operating margin", "%"),
    ("current_ratio", "Current ratio", "x"),
    ("fcf_ttm", "Free cash flow (TTM)", "$"),
    ("altman_z_double_prime", 'Altman Z"', ""),
]


def collect(summary, watchlist, triggers, stress, trends):
    merged = summary.merge(
        watchlist[["ticker", "watchlist_severity", "on_watchlist", "trigger_count"]],
        on="ticker", how="left")

    def value(row, key):
        raw = row.get(key)
        return None if pd.isna(raw) else float(raw)

    companies = []
    for _, row in merged.sort_values("debt_to_ebitda", ascending=False).iterrows():
        companies.append({
            "ticker": row["ticker"],
            "name": row["company_name"],
            "grade": row["credit_grade"],
            "band": row["pd_proxy_band"],
            "severity": row["watchlist_severity"],
            "period": str(pd.to_datetime(row["period_end_date"]).date()),
            "revenue": value(row, "revenue_ttm"),
            "ebitda": value(row, "ebitda_ttm"),
            "margin": value(row, "operating_margin"),
            "debt": value(row, "total_debt"),
            "netDebt": value(row, "net_debt"),
            "leverage": value(row, "debt_to_ebitda"),
            "coverage": value(row, "interest_coverage"),
            "fcfToDebt": value(row, "fcf_to_debt"),
            "currentRatio": value(row, "current_ratio"),
            "quickRatio": value(row, "quick_ratio"),
            "altman": value(row, "altman_z_double_prime"),
            "headroom": value(row, "covenant_headroom_turns"),
            "coverageNote": "net interest income - not meaningful"
            if pd.isna(row.get("interest_coverage")) else None,
        })

    trend_map = {}
    for (ticker, metric), group in trends.groupby(["ticker", "metric"]):
        group = group.sort_values("period_end_date").tail(8)
        trend_map.setdefault(ticker, {})[metric] = [
            {"period": str(pd.to_datetime(p).date()), "value": None if pd.isna(v) else float(v)}
            for p, v in zip(group["period_end_date"], group["value"])]

    stress_rows = []
    for _, row in stress.iterrows():
        stress_rows.append({
            "ticker": row["ticker"],
            "scenario": row["scenario"],
            "label": row["scenario_label"],
            "leverage": None if pd.isna(row["stressed_debt_to_ebitda"]) else float(row["stressed_debt_to_ebitda"]),
            "coverage": None if pd.isna(row["stressed_interest_coverage"]) else float(row["stressed_interest_coverage"]),
            "ebitda": None if pd.isna(row["stressed_ebitda"]) else float(row["stressed_ebitda"]),
            "breach": bool(row["breaches_leverage_covenant"]),
            "coverageBreach": bool(row["breaches_coverage_floor"]),
        })

    trigger_rows = [{"ticker": r["ticker"], "category": r["category"],
                     "severity": r["severity"], "reason": r["reason"]}
                    for _, r in triggers.iterrows()]

    scenario_order = list(dict.fromkeys(stress["scenario_label"]))
    flagged = int(merged["on_watchlist"].sum())
    portfolio_debt = merged["total_debt"].sum()
    portfolio_ebitda = merged["ebitda_ttm"].sum()

    return {
        "companies": companies,
        "trends": trend_map,
        "stress": stress_rows,
        "triggers": trigger_rows,
        "scenarios": scenario_order,
        "thresholds": {
            "covenant": DEBT_EBITDA_COVENANT,
            "coverage": MIN_INTEREST_COVERAGE,
            "currentRatio": MIN_CURRENT_RATIO,
            "altman": ALTMAN_ZPP_DISTRESS,
        },
        "headline": {
            "covered": len(companies),
            "flagged": flagged,
            "triggers": len(trigger_rows),
            # Debt-weighted, not an average of ratios: averaging multiples lets a
            # small debt-free name offset a large levered one.
            "portfolioLeverage": float(portfolio_debt / portfolio_ebitda)
            if portfolio_ebitda else None,
            "asOf": max(c["period"] for c in companies),
        },
    }


HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Corporate Credit Risk — Portfolio Dashboard</title>
<style>
  html, body { margin: 0; padding: 0; }
  body { background: #ffffff; }
  @media (prefers-color-scheme: dark) { body { background: #121211; } }
</style>
</head>
<body>
<div class="viz-root" id="app">
<style>
.viz-root {
  color-scheme: light;
  --surface-0: #ffffff;
  --surface-1: #fcfcfb;
  --surface-2: #f4f3f0;
  --border:    #e2e1dc;
  --grid:      #ebeae6;
  --text-primary:   #0b0b0b;
  --text-secondary: #52514e;
  --text-muted:     #78776f;
  --series-1: #2a78d6;
  --series-2: #eb6834;
  --series-3: #1baf7a;
  --good:     #0ca30c;
  --warning:  #fab219;
  --critical: #d03b3b;
  --seq-100: #cde2fb; --seq-200: #9ec5f4; --seq-300: #6da7ec;
  --seq-450: #2a78d6; --seq-550: #1c5cab; --seq-700: #0d366b;
  --shadow: 0 1px 2px rgba(11,11,11,.06), 0 1px 8px rgba(11,11,11,.04);
}
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])) .viz-root {
    color-scheme: dark;
    --surface-0: #121211; --surface-1: #1a1a19; --surface-2: #232322;
    --border: #34343200; --border: #343432; --grid: #2b2b2a;
    --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #92918a;
    --series-1: #3987e5; --series-2: #d95926; --series-3: #199e70;
    --seq-100: #0d366b; --seq-200: #104281; --seq-300: #184f95;
    --seq-450: #256abf; --seq-550: #3987e5; --seq-700: #86b6ef;
    --shadow: 0 1px 2px rgba(0,0,0,.4);
  }
}
:root[data-theme="dark"] .viz-root {
  color-scheme: dark;
  --surface-0: #121211; --surface-1: #1a1a19; --surface-2: #232322;
  --border: #343432; --grid: #2b2b2a;
  --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #92918a;
  --series-1: #3987e5; --series-2: #d95926; --series-3: #199e70;
  --seq-100: #0d366b; --seq-200: #104281; --seq-300: #184f95;
  --seq-450: #256abf; --seq-550: #3987e5; --seq-700: #86b6ef;
  --shadow: 0 1px 2px rgba(0,0,0,.4);
}

.viz-root {
  background: var(--surface-0);
  color: var(--text-primary);
  font: 14px/1.5 ui-sans-serif, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  padding: 28px 22px 64px;
  max-width: 1240px;
  margin: 0 auto;
}
.viz-root * { box-sizing: border-box; }
h1 { font-size: 22px; font-weight: 650; letter-spacing: -.01em; margin: 0 0 4px; }
h2 { font-size: 15px; font-weight: 620; margin: 0 0 2px; }
.sub { color: var(--text-secondary); font-size: 12.5px; margin: 0; }
.muted { color: var(--text-muted); font-size: 12px; }

/* --- tabs ------------------------------------------------------------- */
.tabs { display: flex; gap: 4px; margin: 20px 0 18px; border-bottom: 1px solid var(--border); flex-wrap: wrap; }
.tab {
  appearance: none; background: none; border: 0; border-bottom: 2px solid transparent;
  color: var(--text-secondary); font: inherit; font-size: 13.5px; font-weight: 550;
  padding: 9px 13px; cursor: pointer; margin-bottom: -1px;
}
.tab:hover { color: var(--text-primary); }
.tab[aria-selected="true"] { color: var(--text-primary); border-bottom-color: var(--series-1); }
.page[hidden] { display: none; }

/* --- cards & tiles ---------------------------------------------------- */
.card {
  background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px;
  padding: 16px 18px; box-shadow: var(--shadow); margin-bottom: 16px;
}
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 16px; }
.tile { background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px; padding: 13px 15px; box-shadow: var(--shadow); }
.tile .label { font-size: 11.5px; color: var(--text-secondary); text-transform: uppercase; letter-spacing: .04em; font-weight: 560; }
.tile .figure { font-size: 27px; font-weight: 640; letter-spacing: -.02em; margin-top: 5px; font-variant-numeric: tabular-nums; }
.tile .foot { font-size: 11.5px; color: var(--text-muted); margin-top: 2px; }

/* --- table ------------------------------------------------------------ */
.scroll { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { text-align: right; padding: 7px 9px; border-bottom: 1px solid var(--grid); white-space: nowrap; }
th { color: var(--text-secondary); font-weight: 560; font-size: 11.5px; text-transform: uppercase; letter-spacing: .03em; }
td:first-child, th:first-child, td.l, th.l { text-align: left; }
tbody tr:hover td { background: var(--surface-2); }
.num { font-variant-numeric: tabular-nums; }
.bad { color: var(--critical); font-weight: 600; }

/* Severity always pairs a colour with a shape glyph and a text label --
   the status ramp is not separable by colour alone under CVD. */
.chip { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; font-weight: 560; white-space: nowrap; }
.chip .glyph { font-size: 10px; line-height: 1; }
.sev-High { color: var(--critical); }
.sev-Medium { color: var(--warning); }
.sev-Low { color: var(--warning); }
.sev-Clear { color: var(--good); }
:root[data-theme="light"] .sev-Medium, :root[data-theme="light"] .sev-Low { color: #9a6a00; }
@media (prefers-color-scheme: light) { .sev-Medium, .sev-Low { color: #9a6a00; } }

/* --- charts ----------------------------------------------------------- */
.grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 14px; }
.panels { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 14px; }
svg { display: block; max-width: 100%; overflow: visible; }
.axis-line { stroke: var(--border); stroke-width: 1; }
.grid-line { stroke: var(--grid); stroke-width: 1; }
.ref-line { stroke: var(--critical); stroke-width: 1; stroke-dasharray: 4 3; opacity: .75; }
.tick { fill: var(--text-muted); font-size: 10.5px; }
.mark-label { fill: var(--text-secondary); font-size: 10.5px; font-weight: 560; }
.legend { display: flex; gap: 14px; flex-wrap: wrap; align-items: center; margin-top: 10px; font-size: 12px; color: var(--text-secondary); }
.legend .item { display: inline-flex; align-items: center; gap: 6px; }

/* --- controls --------------------------------------------------------- */
.controls { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-bottom: 14px; }
select, .toggle {
  appearance: none; background: var(--surface-1); color: var(--text-primary);
  border: 1px solid var(--border); border-radius: 7px; padding: 7px 11px;
  font: inherit; font-size: 13px; cursor: pointer;
}
.toggle[aria-pressed="true"] { background: var(--surface-2); border-color: var(--text-muted); }

/* --- tooltip ---------------------------------------------------------- */
#tip {
  position: fixed; pointer-events: none; opacity: 0; transition: opacity .09s;
  background: var(--surface-0); color: var(--text-primary);
  border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px;
  font-size: 12.5px; box-shadow: 0 4px 16px rgba(0,0,0,.16); z-index: 50; max-width: 280px;
}
#tip .t-title { font-weight: 620; margin-bottom: 3px; }
#tip .t-row { color: var(--text-secondary); display: flex; justify-content: space-between; gap: 14px; }
#tip .t-row b { color: var(--text-primary); font-weight: 560; font-variant-numeric: tabular-nums; }

.trigger { border-left: 2px solid var(--border); padding: 3px 0 3px 11px; margin-bottom: 9px; font-size: 12.5px; }
.trigger.Level { border-left-color: var(--critical); }
.trigger.Trend { border-left-color: var(--warning); }
.trigger.Stress { border-left-color: var(--series-1); }
.trigger .cat { font-size: 10.5px; text-transform: uppercase; letter-spacing: .05em; color: var(--text-muted); font-weight: 600; }
.note { font-size: 12px; color: var(--text-muted); margin-top: 9px; }
</style>

<h1>Corporate Credit Risk &mdash; Portfolio Dashboard</h1>
<p class="sub">US retail issuers &middot; SEC EDGAR XBRL filings &middot; latest filed quarter as of <span id="asof"></span>.
Covenant thresholds are stated assumptions, not negotiated terms.</p>

<div class="tabs" role="tablist">
  <button class="tab" role="tab" aria-selected="true" data-page="overview">Portfolio Overview</button>
  <button class="tab" role="tab" aria-selected="false" data-page="company">Company Deep Dive</button>
  <button class="tab" role="tab" aria-selected="false" data-page="stress">Stress Test Matrix</button>
</div>

<section class="page" id="page-overview">
  <div class="tiles" id="tiles"></div>
  <div class="card">
    <h2>Leverage vs. coverage</h2>
    <p class="sub">Each name plotted against the two tests that matter most. The lower-right
      quadrant &mdash; leverage above the assumed covenant, coverage below the floor &mdash; is the problem set.</p>
    <div id="scatter"></div>
    <div class="legend" id="scatter-legend"></div>
    <p class="note">Marks are labelled and shaped as well as coloured: the status palette is not
      separable by colour alone for readers with colour-vision deficiency.</p>
  </div>
  <div class="card">
    <h2>Portfolio detail</h2>
    <p class="sub">The table view of every figure plotted above.</p>
    <div class="scroll"><table id="portfolio"></table></div>
  </div>
</section>

<section class="page" id="page-company" hidden>
  <div class="controls">
    <label for="pick" class="muted">Company</label>
    <select id="pick"></select>
    <button class="toggle" id="trend-table" aria-pressed="false">Show trend as table</button>
  </div>
  <div class="tiles" id="company-tiles"></div>
  <div class="card">
    <h2>Eight-quarter trend</h2>
    <p class="sub">Trailing-twelve-month ratios by fiscal quarter. Dashed rules mark the assumed policy thresholds.</p>
    <div class="panels" id="panels"></div>
    <div class="scroll" id="trend-table-view" hidden></div>
  </div>
  <div class="grid2">
    <div class="card">
      <h2>Stress scenarios</h2>
      <p class="sub">Debt/EBITDA under each shock.</p>
      <div id="company-stress"></div>
    </div>
    <div class="card">
      <h2>Watchlist triggers</h2>
      <div id="company-triggers"></div>
    </div>
  </div>
</section>

<section class="page" id="page-stress" hidden>
  <div class="card">
    <h2>Stressed Debt / EBITDA</h2>
    <p class="sub">Company by scenario. Shading runs light to dark with leverage; a ring and bold
      figure mark a breach of the assumed covenant.</p>
    <div class="scroll" id="heatmap"></div>
    <div class="legend" id="heat-legend"></div>
  </div>
  <div class="card">
    <h2>Stressed EBITDA / interest coverage</h2>
    <p class="sub">The rate and inventory shocks leave EBITDA untouched, so they cannot move a
      leverage multiple &mdash; their effect is visible only here and in liquidity.</p>
    <div class="scroll" id="heatmap2"></div>
  </div>
</section>

<div id="tip" role="tooltip"></div>

<script>
const DATA = __DATA__;
const NS = "http://www.w3.org/2000/svg";
const T = DATA.thresholds;

/* Severity uses colour + shape + label together, never colour alone. */
const SEV = {
  High:   { color: "var(--critical)", glyph: "▲", shape: "triangle" },
  Medium: { color: "var(--warning)",  glyph: "◆", shape: "diamond" },
  Low:    { color: "var(--warning)",  glyph: "◆", shape: "diamond" },
  Clear:  { color: "var(--good)",     glyph: "●", shape: "circle" },
};

const fmtX = v => v == null ? "n/a" : v.toFixed(2) + "x";
const fmtPct = (v, d = 1) => v == null ? "n/a" : (v * 100).toFixed(d) + "%";
const fmtNum = (v, d = 2) => v == null ? "n/a" : v.toFixed(d);
const fmtMoney = v => {
  if (v == null) return "n/a";
  const a = Math.abs(v);
  if (a >= 1e9) return (v / 1e9).toFixed(1) + "bn";
  return (v / 1e6).toFixed(0) + "m";
};
/* A ratio computed off near-zero EBITDA runs to hundreds of turns (Wayfair's
   leverage was 202x two years ago). Left alone, one such point owns the axis
   and flattens every other name into the baseline. So the axis is capped just
   above the bulk of the data and outliers are pinned to the edge with a caret
   and their true value — clipped, but never silently hidden. */
const quantile = (sorted, q) => {
  if (!sorted.length) return 0;
  const pos = (sorted.length - 1) * q, lo = Math.floor(pos), hi = Math.ceil(pos);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
};
function cappedMax(values, floor) {
  const v = values.filter(n => n != null && isFinite(n)).sort((a, b) => a - b);
  if (!v.length) return floor;
  const max = v[v.length - 1];
  const cap = Math.max(floor, quantile(v, 0.75) * 1.6);
  return max > cap * 1.25 ? cap : max;
}

/* Trend panels get a different rule. A percentile cap fires on any strongly
   rising series -- it clipped Wayfair's operating margin at its CURRENT value
   because every earlier quarter was lower. What a credit reader needs to see
   is the recent level and the policy threshold, so the ceiling is anchored to
   those; only history far above both goes off-scale. */
function panelCeiling(values, ref) {
  const max = Math.max(...values);
  const last = values[values.length - 1];
  let cap = Math.abs(last) * 4;
  if (ref != null) cap = Math.max(cap, Math.abs(ref) * 3);
  return max > cap ? cap : max;
}
const el = (tag, attrs = {}, parent) => {
  const n = document.createElementNS(NS, tag);
  for (const k in attrs) n.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(n);
  return n;
};

/* ---------- tooltip ---------- */
const tip = document.getElementById("tip");
function showTip(evt, title, rows) {
  tip.innerHTML = `<div class="t-title">${title}</div>` +
    rows.map(([k, v]) => `<div class="t-row"><span>${k}</span><b>${v}</b></div>`).join("");
  tip.style.opacity = 1;
  moveTip(evt);
}
function moveTip(evt) {
  const pad = 14, r = tip.getBoundingClientRect();
  let x = evt.clientX + pad, y = evt.clientY + pad;
  if (x + r.width > innerWidth - 8) x = evt.clientX - r.width - pad;
  if (y + r.height > innerHeight - 8) y = evt.clientY - r.height - pad;
  tip.style.left = x + "px"; tip.style.top = y + "px";
}
const hideTip = () => { tip.style.opacity = 0; };
function bindTip(node, title, rows) {
  node.addEventListener("mouseenter", e => showTip(e, title, rows));
  node.addEventListener("mousemove", moveTip);
  node.addEventListener("mouseleave", hideTip);
}

/* ---------- headline tiles ---------- */
function renderTiles() {
  const h = DATA.headline;
  document.getElementById("asof").textContent = h.asOf;
  const grades = {};
  DATA.companies.forEach(c => grades[c.grade] = (grades[c.grade] || 0) + 1);
  const subIG = DATA.companies.filter(c => ["BB", "B", "CCC"].includes(c.grade)).length;
  const tiles = [
    ["Companies covered", h.covered, "latest filed quarter"],
    ["On watchlist", h.flagged, `${h.triggers} triggers fired`],
    ["Sub-investment grade", subIG, "internal scorecard grade"],
    ["Portfolio Debt/EBITDA", fmtX(h.portfolioLeverage), "debt-weighted, not an average of ratios"],
  ];
  document.getElementById("tiles").innerHTML = tiles.map(([l, f, s]) =>
    `<div class="tile"><div class="label">${l}</div><div class="figure">${f}</div><div class="foot">${s}</div></div>`
  ).join("");
}

/* ---------- scatter: leverage vs coverage ---------- */
function renderScatter() {
  const host = document.getElementById("scatter");
  host.innerHTML = "";
  const W = Math.min(host.clientWidth || 880, 880), H = 400;
  const m = { t: 14, r: 22, b: 44, l: 54 };
  const pts = DATA.companies.filter(c => c.leverage != null && c.coverage != null);
  const noCov = DATA.companies.filter(c => c.leverage != null && c.coverage == null);

  const maxX = Math.max(T.covenant * 1.35, ...pts.map(p => p.leverage)) * 1.08;
  const maxY = cappedMax(pts.map(p => p.coverage), T.coverage * 6) * 1.06;
  const offscale = pts.filter(p => p.coverage > maxY);
  const x = v => m.l + (v / maxX) * (W - m.l - m.r);
  const y = v => H - m.b - (Math.min(v, maxY) / maxY) * (H - m.t - m.b);

  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H,
                          role: "img", "aria-label": "Leverage versus interest coverage" }, host);

  for (let i = 0; i <= 4; i++) {
    const gv = (maxY / 4) * i;
    el("line", { x1: m.l, x2: W - m.r, y1: y(gv), y2: y(gv), class: "grid-line" }, svg);
    const t = el("text", { x: m.l - 8, y: y(gv) + 3.5, class: "tick", "text-anchor": "end" }, svg);
    t.textContent = gv.toFixed(0) + "x";
  }
  for (let i = 0; i <= 5; i++) {
    const gv = (maxX / 5) * i;
    const t = el("text", { x: x(gv), y: H - m.b + 16, class: "tick", "text-anchor": "middle" }, svg);
    t.textContent = gv.toFixed(1) + "x";
  }
  el("line", { x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b, class: "axis-line" }, svg);
  el("line", { x1: m.l, x2: m.l, y1: m.t, y2: H - m.b, class: "axis-line" }, svg);

  // Policy thresholds define the quadrants.
  el("line", { x1: x(T.covenant), x2: x(T.covenant), y1: m.t, y2: H - m.b, class: "ref-line" }, svg);
  el("line", { x1: m.l, x2: W - m.r, y1: y(T.coverage), y2: y(T.coverage), class: "ref-line" }, svg);
  let lab = el("text", { x: x(T.covenant) - 6, y: m.t + 11, class: "mark-label", "text-anchor": "end" }, svg);
  lab.textContent = `covenant ${T.covenant}x`;
  lab = el("text", { x: W - m.r, y: y(T.coverage) - 6, class: "mark-label", "text-anchor": "end" }, svg);
  lab.textContent = `coverage floor ${T.coverage}x`;

  const maxE = Math.max(...pts.map(p => p.ebitda || 0));
  pts.forEach(p => {
    const r = 7 + 13 * Math.sqrt((p.ebitda || 0) / maxE);
    const s = SEV[p.severity] || SEV.Clear;
    const cx = x(p.leverage), cy = y(p.coverage);
    let node;
    if (s.shape === "triangle") {
      node = el("polygon", { points: `${cx},${cy - r} ${cx + r},${cy + r * .78} ${cx - r},${cy + r * .78}` }, svg);
    } else if (s.shape === "diamond") {
      node = el("polygon", { points: `${cx},${cy - r} ${cx + r},${cy} ${cx},${cy + r} ${cx - r},${cy}` }, svg);
    } else {
      node = el("circle", { cx, cy, r }, svg);
    }
    node.setAttribute("fill", s.color);
    node.setAttribute("fill-opacity", ".82");
    // 2px surface ring so overlapping marks stay separable.
    node.setAttribute("stroke", "var(--surface-1)");
    node.setAttribute("stroke-width", "2");
    node.style.cursor = "pointer";
    bindTip(node, `${p.ticker} — ${p.name}`, [
      ["Grade", p.grade], ["Watchlist", p.severity],
      ["Debt/EBITDA", fmtX(p.leverage)], ["EBITDA/interest", fmtX(p.coverage)],
      ["EBITDA (TTM)", "$" + fmtMoney(p.ebitda)], ["Headroom", fmtNum(p.headroom) + " turns"]]);
    const clipped = p.coverage > maxY;
    // Flip the label under the mark when it would otherwise run off the top of
    // the plot and collide with the text above the chart.
    const above = cy - r - 5;
    const ly = above < m.t + 9 ? cy + r + 12 : above;
    const tx = el("text", { x: cx, y: ly, class: "mark-label", "text-anchor": "middle" }, svg);
    tx.textContent = clipped ? `${p.ticker} ${fmtX(p.coverage)} ↑` : p.ticker;
  });

  document.getElementById("scatter-legend").innerHTML =
    Object.entries({ High: "On watchlist — high", Medium: "On watchlist — medium", Clear: "No triggers" })
      .map(([k, label]) => `<span class="item"><span class="chip sev-${k}"><span class="glyph">${SEV[k].glyph}</span></span>${label}</span>`)
      .join("") +
    `<span class="item muted">Marker size = EBITDA (TTM)</span>` +
    (offscale.length ? `<span class="item muted">↑ above the axis, true value labelled: ${offscale.map(c => c.ticker).join(", ")}</span>` : "") +
    (noCov.length ? `<span class="item muted">Not plotted: ${noCov.map(c => c.ticker).join(", ")} — net interest income, coverage not meaningful</span>` : "");
}

/* ---------- portfolio table (also the chart's table view) ---------- */
function renderTable() {
  const cols = [
    ["Ticker", c => c.ticker, "l"], ["Company", c => c.name, "l"],
    ["Grade", c => c.grade, "l"], ["Watchlist", c => chip(c.severity), "l"],
    ["Revenue TTM", c => "$" + fmtMoney(c.revenue)], ["EBITDA TTM", c => "$" + fmtMoney(c.ebitda)],
    ["Op margin", c => fmtPct(c.margin)], ["Total debt", c => "$" + fmtMoney(c.debt)],
    ["Debt/EBITDA", c => flag(c.leverage, c.leverage != null && c.leverage > T.covenant, fmtX)],
    ["EBITDA/int", c => c.coverage == null ? '<span class="muted">n/m</span>'
      : flag(c.coverage, c.coverage < T.coverage, fmtX)],
    ["FCF/debt", c => fmtPct(c.fcfToDebt)],
    ["Current", c => flag(c.currentRatio, c.currentRatio != null && c.currentRatio < T.currentRatio, fmtX)],
    ["Altman Z″", c => flag(c.altman, c.altman != null && c.altman < T.altman, v => fmtNum(v))],
    ["Headroom", c => fmtNum(c.headroom)],
  ];
  const chipHtml = s => chip(s);
  const t = document.getElementById("portfolio");
  t.innerHTML = "<thead><tr>" + cols.map(([h, , cls]) =>
      `<th class="${cls || ''}">${h}</th>`).join("") + "</tr></thead><tbody>" +
    DATA.companies.map(c => "<tr>" + cols.map(([, fn, cls]) =>
      `<td class="${cls || 'num'}">${fn(c)}</td>`).join("") + "</tr>").join("") + "</tbody>";
}
const chip = s => `<span class="chip sev-${s}"><span class="glyph">${(SEV[s] || SEV.Clear).glyph}</span>${s}</span>`;
const flag = (v, bad, fmt) => `<span class="${bad ? 'bad' : ''}">${fmt(v)}</span>`;

/* ---------- company page ---------- */
function renderCompany(ticker) {
  const c = DATA.companies.find(x => x.ticker === ticker);
  document.getElementById("company-tiles").innerHTML = [
    ["Internal grade", c.grade, c.band],
    ["Debt / EBITDA", fmtX(c.leverage), `covenant ${T.covenant}x`],
    ["EBITDA / interest", c.coverage == null ? "n/m" : fmtX(c.coverage), c.coverageNote || `floor ${T.coverage}x`],
    ["Covenant headroom", fmtNum(c.headroom), "turns"],
    ['Altman Z″', fmtNum(c.altman), `distress below ${T.altman}`],
  ].map(([l, f, s]) => `<div class="tile"><div class="label">${l}</div><div class="figure">${f}</div><div class="foot">${s}</div></div>`).join("");

  renderPanels(ticker);
  renderTrendTable(ticker);
  renderCompanyStress(ticker);

  const rows = DATA.triggers.filter(t => t.ticker === ticker);
  document.getElementById("company-triggers").innerHTML = rows.length
    ? rows.map(r => `<div class="trigger ${r.category}"><div class="cat">${r.category} &middot; ${r.severity}</div>${r.reason}</div>`).join("")
    : `<p class="sub">No triggers. Inside every credit-policy test, with no early-warning test firing.</p>`;
}

const PANELS = __PANELS__;

function renderPanels(ticker) {
  const host = document.getElementById("panels");
  host.innerHTML = "";
  const series = DATA.trends[ticker] || {};
  PANELS.forEach(([key, title, unit]) => {
    const data = (series[key] || []).filter(d => d.value != null);
    const box = document.createElement("div");
    box.innerHTML = `<div style="font-size:12.5px;font-weight:600;margin-bottom:2px">${title}</div>`;
    host.appendChild(box);
    if (data.length < 2) {
      box.innerHTML += `<p class="muted">Not enough history.</p>`;
      return;
    }
    const W = 300, H = 132, m = { t: 12, r: 12, b: 22, l: 46 };
    const vals = data.map(d => d.value);
    const ref = key === "debt_to_ebitda" ? T.covenant
      : key === "interest_coverage" ? T.coverage
      : key === "current_ratio" ? T.currentRatio
      : key === "altman_z_double_prime" ? T.altman : null;
    let lo = Math.min(...vals), hi = panelCeiling(vals, ref);
    if (ref != null) { lo = Math.min(lo, ref); hi = Math.max(hi, ref); }
    if (lo === hi) { lo -= 1; hi += 1; }
    const pad = (hi - lo) * .16; lo -= pad; hi += pad;
    if (unit !== "$" && lo > 0) lo = Math.min(lo, 0);
    const clippedCount = vals.filter(v => v > hi).length;
    const x = i => m.l + (i / (data.length - 1)) * (W - m.l - m.r);
    const y = v => H - m.b - ((Math.min(v, hi) - lo) / (hi - lo)) * (H - m.t - m.b);
    const fmt = v => unit === "%" ? fmtPct(v, 1) : unit === "$" ? "$" + fmtMoney(v) : fmtNum(v) + (unit === "x" ? "x" : "");

    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, width: "100%", height: H,
                            preserveAspectRatio: "xMidYMid meet", role: "img", "aria-label": title }, box);
    [lo, (lo + hi) / 2, hi].forEach(gv => {
      el("line", { x1: m.l, x2: W - m.r, y1: y(gv), y2: y(gv), class: "grid-line" }, svg);
      const t = el("text", { x: m.l - 6, y: y(gv) + 3.5, class: "tick", "text-anchor": "end" }, svg);
      t.textContent = fmt(gv);
    });
    if (ref != null) {
      el("line", { x1: m.l, x2: W - m.r, y1: y(ref), y2: y(ref), class: "ref-line" }, svg);
    }
    el("line", { x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b, class: "axis-line" }, svg);

    const d = data.map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p.value)}`).join(" ");
    el("path", { d, fill: "none", stroke: "var(--series-1)", "stroke-width": 2,
                 "stroke-linejoin": "round", "stroke-linecap": "round" }, svg);

    // Mark any point pinned to the ceiling, and say so beneath the panel.
    data.forEach((p, i) => {
      if (p.value <= hi) return;
      const cx = x(i);
      el("polygon", { points: `${cx},${y(hi) - 7} ${cx + 5},${y(hi) + 1} ${cx - 5},${y(hi) + 1}`,
                      fill: "var(--series-1)", stroke: "var(--surface-1)", "stroke-width": 1.5 }, svg);
    });
    if (clippedCount) {
      const note = document.createElement("p");
      note.className = "muted";
      note.style.margin = "2px 0 0";
      note.textContent = `${clippedCount} earlier quarter${clippedCount > 1 ? "s" : ""} above the axis `
        + `(peak ${fmt(Math.max(...vals))}) — see the table view.`;
      box.appendChild(note);
    }

    // Direct-label the endpoint only; the axis and tooltip carry the rest.
    const last = data[data.length - 1];
    const lx = x(data.length - 1), ly = y(last.value);
    const dot = el("circle", { cx: lx, cy: ly, r: 4.5, fill: "var(--series-1)",
                               stroke: "var(--surface-1)", "stroke-width": 2 }, svg);
    const tl = el("text", { x: lx, y: ly - 9, class: "mark-label", "text-anchor": "end" }, svg);
    tl.textContent = fmt(last.value);

    [data[0], last].forEach((p, i) => {
      const t = el("text", { x: i ? W - m.r : m.l, y: H - m.b + 15, class: "tick",
                             "text-anchor": i ? "end" : "start" }, svg);
      t.textContent = p.period.slice(0, 7);
    });

    // Crosshair + tooltip across the series.
    const hit = el("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b,
                             fill: "transparent" }, svg);
    const cross = el("line", { y1: m.t, y2: H - m.b, class: "grid-line", opacity: 0,
                               stroke: "var(--text-muted)" }, svg);
    hit.addEventListener("mousemove", e => {
      const box2 = svg.getBoundingClientRect();
      const px = (e.clientX - box2.left) / box2.width * W;
      let idx = Math.round((px - m.l) / ((W - m.l - m.r) / (data.length - 1)));
      idx = Math.max(0, Math.min(data.length - 1, idx));
      cross.setAttribute("x1", x(idx)); cross.setAttribute("x2", x(idx));
      cross.setAttribute("opacity", .55);
      showTip(e, title, [["Quarter", data[idx].period], ["Value", fmt(data[idx].value)]]);
    });
    hit.addEventListener("mouseleave", () => { cross.setAttribute("opacity", 0); hideTip(); });
  });
}

function renderTrendTable(ticker) {
  const series = DATA.trends[ticker] || {};
  const periods = [...new Set(Object.values(series).flat().map(d => d.period))].sort();
  const host = document.getElementById("trend-table-view");
  host.innerHTML = "<table><thead><tr><th class='l'>Metric</th>" +
    periods.map(p => `<th>${p}</th>`).join("") + "</tr></thead><tbody>" +
    PANELS.map(([key, title, unit]) => {
      const byPeriod = Object.fromEntries((series[key] || []).map(d => [d.period, d.value]));
      const fmt = v => v == null ? "—" : unit === "%" ? fmtPct(v) : unit === "$" ? "$" + fmtMoney(v)
        : fmtNum(v) + (unit === "x" ? "x" : "");
      return `<tr><td class="l">${title}</td>` +
        periods.map(p => `<td class="num">${fmt(byPeriod[p])}</td>`).join("") + "</tr>";
    }).join("") + "</tbody></table>";
}

function renderCompanyStress(ticker) {
  const host = document.getElementById("company-stress");
  host.innerHTML = "";
  const rows = DATA.stress.filter(s => s.ticker === ticker && s.leverage != null);
  if (!rows.length) { host.innerHTML = `<p class="muted">No leverage multiple — this name carries no debt.</p>`; return; }
  const W = 460, rowH = 30, H = rows.length * rowH + 34, m = { t: 6, r: 58, b: 24, l: 172 };
  const maxV = Math.max(T.covenant * 1.15, ...rows.map(r => r.leverage));
  const x = v => m.l + (v / maxV) * (W - m.l - m.r);
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, width: "100%", height: H,
                          preserveAspectRatio: "xMidYMid meet", role: "img",
                          "aria-label": "Stressed Debt/EBITDA by scenario" }, host);
  rows.forEach((r, i) => {
    const yy = m.t + i * rowH;
    const lab = el("text", { x: m.l - 9, y: yy + 15, class: "tick", "text-anchor": "end" }, svg);
    lab.textContent = r.label;
    const w = Math.max(2, x(r.leverage) - m.l);
    // 4px rounded data-end, anchored to the baseline.
    const bar = el("rect", { x: m.l, y: yy + 5, width: w, height: 15, rx: 4,
                             fill: r.breach ? "var(--critical)" : "var(--series-1)",
                             "fill-opacity": r.breach ? ".9" : ".82" }, svg);
    bindTip(bar, r.label, [["Debt/EBITDA", fmtX(r.leverage)],
      ["EBITDA/interest", fmtX(r.coverage)], ["Stressed EBITDA", "$" + fmtMoney(r.ebitda)],
      ["Covenant", r.breach ? "Breach" : "Compliant"]]);
    const v = el("text", { x: m.l + w + 7, y: yy + 17, class: "mark-label" }, svg);
    v.textContent = fmtX(r.leverage);
  });
  el("line", { x1: x(T.covenant), x2: x(T.covenant), y1: m.t, y2: H - m.b + 4, class: "ref-line" }, svg);
  const rl = el("text", { x: x(T.covenant), y: H - m.b + 16, class: "mark-label", "text-anchor": "middle" }, svg);
  rl.textContent = `covenant ${T.covenant}x`;
}

/* ---------- heatmaps ---------- */
const SEQ = ["var(--seq-100)", "var(--seq-200)", "var(--seq-300)", "var(--seq-450)", "var(--seq-550)", "var(--seq-700)"];
/* Square-root scaling, capped. A linear ramp against a 31x outlier drops
   almost every real name into the first one or two steps, so the shading
   stops discriminating exactly where the portfolio actually sits. */
function heatColor(v, max) {
  if (v == null) return "var(--surface-2)";
  const t = Math.sqrt(Math.max(0, Math.min(v, max)) / max);
  return SEQ[Math.min(SEQ.length - 1, Math.floor(t * SEQ.length))];
}
function renderHeatmap(hostId, field, isBreach, fmt, legendId) {
  const host = document.getElementById(hostId);
  const tickers = DATA.companies.map(c => c.ticker);
  const scenarios = DATA.scenarios;
  const vals = DATA.stress.map(s => s[field]).filter(v => v != null);
  const max = cappedMax(vals, T.covenant * 1.5);

  let html = "<table><thead><tr><th class='l'>Ticker</th>" +
    scenarios.map(s => `<th>${s}</th>`).join("") + "</tr></thead><tbody>";
  tickers.forEach(tk => {
    html += `<tr><td class="l"><b>${tk}</b></td>`;
    scenarios.forEach(sc => {
      const r = DATA.stress.find(s => s.ticker === tk && s.label === sc);
      const v = r ? r[field] : null;
      const breach = r ? isBreach(r) : false;
      const shade = heatColor(v, max);
      const deep = v != null && Math.sqrt(Math.min(v, max) / max) > .5;
      html += `<td class="num heat" data-t="${tk}" data-s="${sc}" style="background:${shade};`
        + `${deep ? "color:#fff;" : ""}${breach ? "outline:2px solid var(--critical);outline-offset:-2px;font-weight:700;" : ""}">`
        + `${v == null ? "n/m" : fmt(v)}${breach ? " ▲" : ""}</td>`;
    });
    html += "</tr>";
  });
  host.innerHTML = html + "</tbody></table>";

  host.querySelectorAll("td.heat").forEach(cell => {
    const r = DATA.stress.find(s => s.ticker === cell.dataset.t && s.label === cell.dataset.s);
    if (!r) return;
    bindTip(cell, `${r.ticker} — ${r.label}`, [
      ["Debt/EBITDA", fmtX(r.leverage)], ["EBITDA/interest", fmtX(r.coverage)],
      ["Stressed EBITDA", "$" + fmtMoney(r.ebitda)],
      ["Covenant", r.breach ? "Breach" : "Compliant"]]);
  });

  if (legendId) {
    document.getElementById(legendId).innerHTML =
      `<span class="item">Leverage</span>` +
      SEQ.map((c, i) => `<span style="width:26px;height:12px;background:${c};display:inline-block;border-radius:2px"
        title="${(max * Math.pow(i / SEQ.length, 2)).toFixed(1)}x+"></span>`).join("") +
      `<span class="item muted">low &rarr; high</span>` +
      `<span class="item" style="margin-left:10px"><span style="width:12px;height:12px;outline:2px solid var(--critical);outline-offset:-2px;display:inline-block"></span>&#9650; breach of ${T.covenant}x assumed covenant</span>`;
  }
}

/* ---------- wiring ---------- */
document.querySelectorAll(".tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(t => t.setAttribute("aria-selected", String(t === tab)));
    document.querySelectorAll(".page").forEach(p => p.hidden = p.id !== "page-" + tab.dataset.page);
    if (tab.dataset.page === "overview") renderScatter();
  });
});
const pick = document.getElementById("pick");
pick.innerHTML = DATA.companies.map(c => `<option value="${c.ticker}">${c.ticker} — ${c.name}</option>`).join("");
pick.addEventListener("change", () => renderCompany(pick.value));
const toggle = document.getElementById("trend-table");
toggle.addEventListener("click", () => {
  const on = toggle.getAttribute("aria-pressed") !== "true";
  toggle.setAttribute("aria-pressed", String(on));
  document.getElementById("panels").hidden = on;
  document.getElementById("trend-table-view").hidden = !on;
  toggle.textContent = on ? "Show trend as charts" : "Show trend as table";
});

renderTiles();
renderTable();
renderScatter();
renderCompany(DATA.companies[0].ticker);
renderHeatmap("heatmap", "leverage", r => r.breach, fmtX, "heat-legend");
renderHeatmap("heatmap2", "coverage", r => r.coverageBreach, fmtX, null);
addEventListener("resize", () => { renderScatter(); });
</script>
</div>
</body>
</html>
"""


def main() -> int:
    required = ["metrics_summary.csv", "watchlist.csv", "watchlist_triggers.csv",
                "stress_test_results.csv", "trends.csv"]
    missing = [f for f in required if not (OUTPUT_DIR / f).exists()]
    if missing:
        print(f"Missing {', '.join(missing)}. Run the pipeline first.")
        return 1

    payload = collect(
        pd.read_csv(OUTPUT_DIR / "metrics_summary.csv", parse_dates=["period_end_date"]),
        pd.read_csv(OUTPUT_DIR / "watchlist.csv"),
        pd.read_csv(OUTPUT_DIR / "watchlist_triggers.csv"),
        pd.read_csv(OUTPUT_DIR / "stress_test_results.csv"),
        pd.read_csv(OUTPUT_DIR / "trends.csv", parse_dates=["period_end_date"]),
    )

    html = (HTML_TEMPLATE
            .replace("__DATA__", json.dumps(payload, separators=(",", ":")))
            .replace("__PANELS__", json.dumps(TREND_PANELS)))
    DASHBOARD_PATH.write_text(html)

    size_kb = DASHBOARD_PATH.stat().st_size / 1024
    print(f"Built {DASHBOARD_PATH} ({size_kb:,.0f} KB, self-contained)")
    print(f"  {payload['headline']['covered']} companies, "
          f"{payload['headline']['flagged']} on watchlist, "
          f"{len(payload['stress'])} stress results, "
          f"{len(payload['triggers'])} triggers")
    print("  Pages: Portfolio Overview, Company Deep Dive, Stress Test Matrix")
    return 0


if __name__ == "__main__":
    sys.exit(main())
