# Corporate Credit-Risk Underwriting & Early-Warning System

A credit analysis pipeline that pulls real financial data from SEC EDGAR for a
portfolio of US retail issuers, builds a clean quarterly panel, computes a
credit metric suite, runs seven stress scenarios, applies level/trend/stress
watchlist triggers, and produces an Excel underwriting model, an interactive
dashboard, a Power BI dataset and a generated credit memo per flagged name.

### ▶ [**View the live dashboard**](https://samruddhiraodeo19.github.io/Corporate-Credit-Analysis/)

Three pages — portfolio overview with a leverage-vs-coverage scatter,
per-company eight-quarter trends, and a stress-scenario breach matrix. No
install, no sign-in; it runs entirely in the browser.

Everything is driven from filings — no manual data entry, no hardcoded
financials. One command rebuilds every deliverable from the SEC API in about
three seconds.

```bash
python src/run_pipeline.py --refresh
```

---

## Latest run

12 US retail issuers, quarter ended 2026-05-02 (Wayfair 2026-06-30).

| Ticker | Company | Grade | Debt/EBITDA | EBITDA/int | FCF/debt | Altman Z″ | Watchlist |
|---|---|---|---|---|---|---|---|
| ROST | Ross Stores | AA | 0.30x | n/m¹ | 259% | 4.12 | — |
| ANF | Abercrombie & Fitch | AA | 0.00x² | n/m¹ | n/m² | 6.39 | — |
| GAP | Gap Inc. | AA | 0.83x | 19.60x | 75% | 3.40 | — |
| DKS | Dick's Sporting Goods | AA | 1.10x | 24.76x | 21% | 3.10 | **Medium** |
| TJX | TJX Companies | A | 0.32x | n/m¹ | 191% | 3.02 | **Medium** |
| M | Macy's | A | 1.26x | 20.35x | 59% | 3.16 | — |
| BBY | Best Buy | A | 0.50x | 51.17x | 137% | 1.97 | — |
| BURL | Burlington Stores | BBB | 1.46x | 18.27x | 20% | 1.82 | — |
| KSS | Kohl's | BBB | 1.06x | 4.76x | 76% | 1.66 | — |
| TGT | Target | BBB | 1.94x | 17.76x | 20% | 1.36 | **Medium** |
| BBWI | Bath & Body Works | BB | 2.58x | 5.12x | 25% | 1.20 | **Medium** |
| W | Wayfair | B | 5.68x | 3.39x | 20% | −6.70 | **High** |

¹ Earns net interest income — no interest burden to cover. Scored as strongest,
not as missing data.
² No funded debt. Leverage is 0.00x and FCF/debt is undefined for a good reason.

**5 of 12 names flagged, 11 triggers.** The two most interesting are not the
obvious ones:

- **DKS** grades AA and breaches nothing, but operating margin fell **495bps**
  and coverage **34%** year on year as the Foot Locker acquisition consolidated
  — revenue up $13.8bn → $19.2bn while EBIT fell. This is exactly what the
  early-warning layer exists to catch: a strong credit moving quickly in the
  wrong direction, well before any covenant is threatened.
- **TJX** grades A with 0.32x leverage, flagged only because **35% of its debt
  matures within 12 months** — a refinancing-calendar risk that no leverage or
  coverage ratio would surface.

---

## Deliverables

| Output | What it is |
|---|---|
| **[Live dashboard](https://samruddhiraodeo19.github.io/Corporate-Credit-Analysis/)** | Interactive 3-page dashboard, deployed on GitHub Pages. Source: [`output/dashboard.html`](output/dashboard.html) — a single self-contained file that also opens straight from a clone |
| [`output/credit_underwriting_model.xlsx`](output/credit_underwriting_model.xlsx) | Excel model: summary/watchlist, company detail, stress matrices, assumptions, extraction audit |
| [`output/memos/`](output/memos) | A two-page credit memo per flagged name, generated from the model's own numbers |
| [`output/powerbi/`](output/powerbi) | Star-schema model, 35 DAX measures and a build guide for Power BI Desktop |
| [`output/watchlist.csv`](output/watchlist.csv) | Every flagged name with the specific trigger and the number behind it |
| [`output/metrics_summary.csv`](output/metrics_summary.csv) | Latest quarter per company, all metrics plus data provenance |

## Documentation

| Document | Covers |
|---|---|
| [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) | Metric definitions, the scorecard, stress scenarios, watchlist triggers |
| [`docs/DATA_PIPELINE.md`](docs/DATA_PIPELINE.md) | How raw XBRL becomes a clean quarterly panel, and how to extend it |
| [`docs/MODEL_VALIDATION.md`](docs/MODEL_VALIDATION.md) | Assumptions, known weaknesses, validation evidence, next steps |
| [`PLAN.md`](PLAN.md) | The original phased build guide |

---

## Setup

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# SEC requires real contact details on every request and returns 403 without them
export SEC_USER_AGENT="Your Name your.email@example.com"

python src/run_pipeline.py --refresh
```

The User-Agent can also go in a `.sec_user_agent` file in the project root,
which is gitignored so a public clone never carries a personal email address.

Requires Python 3.10+ and three dependencies: `requests`, `pandas`, `openpyxl`.
Individual stages run standalone in the order listed in
[`docs/DATA_PIPELINE.md`](docs/DATA_PIPELINE.md).

---

## The hard part: getting clean numbers out of XBRL

Most of the engineering is in `build_db.py`, because filings data does not
arrive usable and its failure modes are quiet — they produce confident-looking
numbers, not errors. Five problems have to be solved before a single ratio is
trustworthy:

**1. Year-to-date cash flows.** Retailers report cash-flow statements
cumulatively from the fiscal-year start, so a Q3 10-Q covers ~39 weeks, not 13.
Filtering to "facts about 90 days long" silently discards three quarters of
every year. Facts sharing a `start` are instead differenced to recover each
discrete quarter.

**2. No discrete Q4.** 10-Ks report the full year only, so a rolling
four-quarter window never completes. Q4 falls out of the same differencing
step: the annual figure minus the nine-month year-to-date one.

**3. Taxonomy drift.** The concept a company uses *changes over time*. Target
left `Revenues` in FY2015 and `LongTermDebtNoncurrent` in FY2013; Dick's moved
to `UnsecuredDebt`; Macy's stopped tagging gross interest quarterly in FY2023;
Burlington and TJX never tag an operating-income subtotal at all. Picking "the
first tag that returns data" locks onto a dead concept. Metrics are therefore
**coalesced across candidate concepts period-by-period**, with a documented
derivation where none exists.

**4. Restatements.** The same period is reported in a 10-Q and again, restated,
in the next 10-K. The most recently *filed* value wins.

**5. Stale disclosures.** Kohl's last tagged a debt-maturity bucket in **2011**;
read literally it says 100% of today's debt matures within a year. Ross's
ladder was current but showed $500m due within a year that it had already
repaid. Ladders are used only if recent, complete, and still reconciling to
balance-sheet debt.

### Design rules

- **Missing is never zero.** "We could not extract this company's debt" and
  "this company has no debt" are different facts. Every metric propagates NaN,
  and the scorecard *excludes* factors it has no data for rather than scoring
  them as clean — a company whose debt didn't extract gets `NR`, not `A`.
- **Undefined-because-favourable is distinguished from undefined-because-missing.**
  Abercrombie has no funded debt and TJX earns net interest income, so their
  ratios don't exist. Those score as *strongest*, with the reasoning recorded.
- **No leverage multiple on negative EBITDA.** −3.0x sorts better than 8.0x but
  means the company has no earnings; those are suppressed and flagged instead.
- **A TTM needs four genuinely consecutive quarters**, or it is withheld.
- **Every threshold is a named constant in `src/config.py`** with its
  rationale, and every watchlist trigger prints the actual value against it.

---

## Validation

`src/validate.py` re-reads the raw SEC facts and reconciles the built panel
against them, independently of the code that built it. It runs as a gate inside
the pipeline and fails the run on any invariant violation:

- **TTM reconciliation** — where all four quarters of a fiscal year came from
  the same concept, they must sum to that concept's filed annual figure. This
  is the direct test of the de-cumulation and Q4-derivation logic. **1,321
  fiscal years currently reconcile exactly.**
- **Debt precedence** — a combined debt tag is never used where a
  current/noncurrent leg exists, so the two cannot double-count.
- **Balance-sheet containment and signs** — inventory ≤ current assets ≤ total
  assets, no negative stocks.
- **Quarter shape** — each quarter is a plausible share of its trailing year,
  which would catch a half-year mistakenly booked as a quarter.

Explainable discrepancies are reported as warnings with their cause rather than
suppressed — pre-2019 Target figures restated for the Canada exit, and Bath &
Body Works' FY2019 quarters, which are pre-separation L Brands consolidated
(~$12.9bn) against an annual figure restated to $5.4bn after the Victoria's
Secret spin-off.

---

## What's real and what's assumed

- **All financial data is real**, pulled live from SEC EDGAR's XBRL API.
- **Covenant thresholds, the floating-rate share, the inventory build, the
  cash-flow passthrough and the tax rate are assumptions** — illustrative of
  public retail credit agreements, not real negotiated terms. They live only in
  `src/config.py` and are restated on the workbook's Assumptions tab.
- **The Altman score is Z″, the non-manufacturer revision**, not the original
  1968 manufacturing Z, which needs a market-cap term XBRL doesn't carry and
  whose asset-turnover term flatters high-turnover retailers.
- **The PD proxy is a rules-based scorecard, not a calibrated PD.** It was not
  fitted to any historical default data. Low/Medium/High is a relative ranking,
  not a probability.
- **Operating leases are excluded from debt.** Rating agencies often capitalise
  them, which would raise retail leverage materially — the most important
  single caveat on these numbers.
- **EBITDA is unadjusted** — no addbacks for impairment, restructuring or
  stock compensation.
- **The scorecard is quantitative only.** It has no view on management,
  competitive position or brand trajectory. A structurally declining retailer
  with clean current ratios will score better here than a credit committee
  would grade it.

Full treatment in [`docs/MODEL_VALIDATION.md`](docs/MODEL_VALIDATION.md).

---

## Project structure

```
credit-risk-system/
  src/
    config.py           universe, concept mapping, every threshold + rationale
    fetch_data.py       SEC companyfacts pull, one request per company
    build_db.py         quarterly panel: de-cumulation, Q4 derivation, dedupe
    validate.py         reconciles the panel back to the raw filings
    calc_metrics.py     metric suite, scorecard, year-on-year deltas
    stress_test.py      scenario engine
    watchlist.py        level / trend / stress triggers
    build_excel.py      the Excel underwriting model
    build_powerbi.py    star-schema export + DAX
    build_dashboard.py  the self-contained HTML dashboard
    build_memo.py       the generated credit memos
    run_pipeline.py     runs all ten stages
  docs/                 methodology, pipeline, model validation
  index.html            redirects the GitHub Pages root to the dashboard
  data/raw/             cached SEC responses (gitignored)
  db/                   SQLite database (gitignored)
  output/               generated deliverables
```

## Known limitations

- The debt maturity ladder comes from XBRL where tagged; companies that never
  tag it are left blank rather than estimated. It is a 10-K disclosure, so it
  goes stale intra-year and is dropped when it stops reconciling.
- Fiscal calendars differ across issuers. The panel aligns on fiscal quarters;
  `period_end_date` is stored so periods can be aligned by calendar date where
  exact comparability matters.
- Metrics reflect the latest filed quarter and lag the market by up to a
  quarter; nothing since the last filing is visible.
- The `.pbix` itself must be assembled in Power BI Desktop, which is
  Windows-only. This repo produces the model and the build steps; the
  [live dashboard](https://samruddhiraodeo19.github.io/Corporate-Credit-Analysis/)
  exists so the analysis is viewable without it.
- The deployed dashboard is a static snapshot of the last committed run. It
  refreshes when the pipeline is re-run and `output/dashboard.html` is pushed —
  there is no server behind it, which is also why it costs nothing to host.
