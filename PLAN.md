# Corporate Credit-Risk Underwriting & Early-Warning System — Build Guide

## Before you start: scope it realistically

This is genuinely a multi-week project if built at full spec. Rather than trying to do all of it at once, build in phases — each phase produces something demoable on its own, so you have a working artifact even if you stop partway.

**Recommended scoping for a portfolio project (vs. the full spec):**
- **Companies:** Start with 10-12, not 20-30. You can expand later once the pipeline works — the hard part is building it correctly once, not adding more rows.
- **Industry:** Retail or consumer goods is a good choice — these companies have simple enough balance sheets that the ratios mean what textbooks say they mean (avoid banks/insurers; their financials don't fit standard credit ratios).
- **Metrics:** Build all 13, but expect the first 6 (leverage, coverage, liquidity) to take most of your time. Altman Z-score and PD proxy are quick once the inputs exist.
- **Deliverables:** Build the pipeline and Excel model first (phases 1-4 below) — those alone are a strong, complete portfolio piece. Add Power BI, the memo, and the validation doc (phases 5-7) if you have more time.

---

## Phase 1: Pick your companies and data source

### Step 1.1: Choose 10-12 companies in one industry
Pick a real, recognizable industry so the story makes sense to a reviewer — e.g. retail: Target, Kohl's, Macy's, Nordstrom, Gap, Dick's Sporting Goods, Best Buy, Foot Locker, Ross Stores, TJX, Burlington, Big Lots (or similar, adjust to what's currently public). Mixing 2-3 clearly-strong and 2-3 clearly-weak balance sheets makes your watchlist output more interesting than 12 similar companies.

### Step 1.2: Get real financial data from SEC EDGAR
You already have the pattern from the JPMorgan project. For structured financial statement line items (not narrative), use the XBRL Frames/CompanyConcept API:

```
https://data.sec.gov/api/xbrl/companyconcept/CIK{10-digit-padded}/us-gaap/{TAG}.json
```

Key tags you'll need per company:
| Metric needed | XBRL tag(s) to try |
|---|---|
| Revenue | `Revenues` or `RevenueFromContractWithCustomerExcludingAssessedTax` |
| EBITDA (build from parts) | `OperatingIncomeLoss` + `DepreciationDepletionAndAmortization` |
| Total debt | `LongTermDebtNoncurrent` + `LongTermDebtCurrent` (or `DebtCurrent`) |
| Cash | `CashAndCashEquivalentsAtCarryingValue` |
| Interest expense | `InterestExpense` |
| Current assets/liabilities | `AssetsCurrent`, `LiabilitiesCurrent` |
| Inventory | `InventoryNet` |
| Free cash flow (build from parts) | `NetCashProvidedByUsedInOperatingActivities` minus `PaymentsToAcquirePropertyPlantAndEquipment` |
| Retained earnings, total assets, total liabilities (for Altman Z) | `RetainedEarningsAccumulatedDeficit`, `Assets`, `Liabilities` |
| Market cap (for Altman Z) | Not in XBRL — pull separately from a market data source, or approximate with shares outstanding times price |

Not every company tags every concept identically — some report `Revenues`, others use `RevenueFromContractWithCustomerExcludingAssessedTax`. Build your pipeline to try a list of fallback tags per metric and use whichever one returns data (this is a real production concern with SEC data, not a beginner mistake).

### Step 1.3: Get a CIK-to-ticker mapping
Pull `https://www.sec.gov/files/company_tickers.json` once and cache it — this maps every ticker to its CIK so you don't have to hardcode CIKs manually for 12 companies.

---

## Phase 2: Build the Python/SQL data pipeline

### Step 2.1: Set up your project structure
```
credit-risk-system/
  data/
    raw/          # raw JSON pulls from SEC, cached
    processed/    # cleaned CSVs
  db/
    credit_risk.db  # SQLite database
  src/
    fetch_data.py    # pulls from SEC API
    build_db.py      # loads into SQLite
    calc_metrics.py  # computes the 13 ratios
    stress_test.py   # runs the 6 scenarios
    watchlist.py     # flags deteriorating companies
  README.md
```

### Step 2.2: Write the fetch script
```python
import requests
import time

HEADERS = {"User-Agent": "YourName youremail@example.com"}  # SEC requires this

def get_concept(cik_padded, tag):
    url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik_padded}/us-gaap/{tag}.json"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code == 404:
        return None  # this company doesn't report this tag
    resp.raise_for_status()
    time.sleep(0.15)  # stay well under SEC's 10 req/sec limit
    return resp.json()
```
Build a small fallback list per metric (e.g. try `Revenues`, then `RevenueFromContractWithCustomerExcludingAssessedTax` if the first returns `None`), and cache every raw JSON response to `data/raw/` so you're not re-hitting the API while you iterate on cleaning logic.

### Step 2.3: Normalize into a long table, then load into SQLite
Reshape everything into `(cik, ticker, company, fiscal_period, tag, value)` rows — same long-format principle as your flash report projects — then load into SQLite with a simple schema:

```sql
CREATE TABLE financials (
    ticker TEXT,
    company TEXT,
    fiscal_period TEXT,  -- e.g. '2024Q4'
    tag TEXT,
    value REAL
);
```

This is the point where SQL becomes genuinely useful: once loaded, you can write queries like "give me the latest 4 quarters of Revenues and OperatingIncomeLoss for every company" instead of juggling nested Python dicts.

### Step 2.4: Handle the annoying real-world stuff
- **Fiscal year mismatches**: not every company's Q4 ends the same calendar month. Store both `fiscal_period` and `period_end_date` so you can align by actual calendar quarter later if needed.
- **Restatements**: SEC data sometimes has the same period reported twice (once in a 10-Q, once restated in the next 10-K). Keep the most recently *filed* value for a given period — sort by `filed` date and take the last one.
- **Missing data**: some smaller companies won't report every tag. Your pipeline should log which company/metric combos came back empty rather than silently produce zeros — a credit analyst needs to know "no data" is different from "zero."

---

## Phase 3: Calculate the 13 credit metrics

Work through these in order — several depend on ones before them.

| # | Metric | Formula |
|---|---|---|
| 1 | EBITDA | Operating Income + D&A |
| 2 | Debt/EBITDA | Total Debt divided by EBITDA (trailing 4 quarters) |
| 3 | Net Debt/EBITDA | (Total Debt minus Cash) divided by EBITDA |
| 4 | Interest Coverage | EBITDA divided by Interest Expense |
| 5 | FCF/Debt | (Operating Cash Flow minus CapEx) divided by Total Debt |
| 6 | Current Ratio | Current Assets divided by Current Liabilities |
| 7 | Quick Ratio | (Current Assets minus Inventory) divided by Current Liabilities |
| 8 | Debt Maturity Profile | Bucket debt by maturity year (from 10-K debt schedule footnote — this one requires reading the actual filing text, not just XBRL, since maturity schedules aren't always cleanly tagged) |
| 9 | Cash Burn | Change in cash quarter-over-quarter, for companies with negative operating cash flow |
| 10 | Operating Margin Trend | Operating Income divided by Revenue, plotted over 8 trailing quarters |
| 11 | Working Capital Trend | (Current Assets minus Current Liabilities), plotted over 8 trailing quarters |
| 12 | Altman Z-Score | Z = 1.2A + 1.4B + 3.3C + 0.6D + 1.0E, where A = Working Capital/Total Assets, B = Retained Earnings/Total Assets, C = EBIT/Total Assets, D = Market Cap/Total Liabilities, E = Sales/Total Assets |
| 13 | Probability-of-Default Proxy | Not a real PD model (those require historical default data you won't have access to) — build a simple scorecard instead: assign points based on which "risk band" each ratio above falls into (e.g. Debt/EBITDA under 2x = 0 points, 2-4x = 1 point, over 4x = 2 points), sum the points, map the total to a rough PD band (Low/Medium/High). Document clearly that this is a proxy, not a calibrated model — see Phase 9. |

**Covenant headroom** and **internal credit grade** don't have universal formulas — they depend on assumed covenant terms (since you won't have access to real private credit agreements). Handle them like this:
- **Covenant headroom**: assume a plausible covenant (e.g. "Debt/EBITDA must stay below 4.5x," typical for a retail term loan) and calculate how much cushion each company has (headroom = covenant threshold minus actual ratio). State your assumed covenant explicitly in the model — don't present it as real.
- **Internal credit grade**: build a simple letter-grade scorecard (AAA down to CCC) driven by weighted scores across the leverage, coverage, and liquidity metrics — similar mechanically to your PD proxy, just presented as a letter grade instead of a probability band.

---

## Phase 4: Run the stress scenarios

For each company, recompute EBITDA, Debt/EBITDA, Interest Coverage, and FCF/Debt under each scenario:

1. **Revenue −10%**: multiply revenue by 0.90, hold margin % constant, recompute EBITDA and downstream ratios
2. **Revenue −20%**: same, times 0.80
3. **EBITDA margin −300bps**: subtract 3.0 percentage points from the margin, apply to actual (not stressed) revenue
4. **Rates +200bps**: recompute interest expense as (existing floating-rate debt times +2%) plus existing fixed-rate interest — if you don't have a fixed/floating split from the filings, a simplifying assumption (e.g. 50% floating) is fine as long as you state it
5. **Inventory increase**: assume a stated percent increase (e.g. +30%), recompute quick ratio and working capital
6. **Combined recession scenario**: revenue −15%, margin −300bps, rates +200bps simultaneously — this is your worst-case, and usually the one that actually breaks a name

Structure this as a function that takes a company's baseline row and a scenario's parameters, and returns a new row of stressed metrics — this way all 6 scenarios (plus baseline) share the same calculation code instead of being copy-pasted six times.

---

## Phase 5: Build the watchlist logic

Define clear, stated rules — this is what makes it look like a real system instead of a vibe:

```python
DEBT_EBITDA_COVENANT = 4.5
MIN_INTEREST_COVERAGE = 2.0
MIN_CURRENT_RATIO = 1.0
ALTMAN_DISTRESS_THRESHOLD = 1.8

def flag_watchlist(company_row, stressed_rows):
    reasons = []
    if company_row["debt_to_ebitda"] > DEBT_EBITDA_COVENANT:
        reasons.append("Debt/EBITDA above assumed covenant threshold")
    if company_row["interest_coverage"] < MIN_INTEREST_COVERAGE:
        reasons.append("Interest coverage below 2.0x")
    if company_row["current_ratio"] < MIN_CURRENT_RATIO:
        reasons.append("Current ratio below 1.0x")
    if company_row["altman_z"] < ALTMAN_DISTRESS_THRESHOLD:
        reasons.append("Altman Z-score in distress zone")
    combined_stress = stressed_rows["combined_recession"]
    if combined_stress["debt_to_ebitda"] > DEBT_EBITDA_COVENANT and company_row["debt_to_ebitda"] <= DEBT_EBITDA_COVENANT:
        reasons.append("Breaches covenant under combined recession scenario")
    return reasons  # empty list = not on watchlist
```
Keep every threshold as a named constant at the top of the file, not a magic number buried in an if-statement — you'll want to tune these once you see real output, and a reviewer asking "why 4.5x?" should get a clear answer (cite a typical retail covenant range from public credit agreements or rating agency criteria, and say so).

---

## Phase 6: Build the Excel underwriting model

This is a separate, standalone deliverable — not just a dump of your Python output. Structure it as:
- **Tab 1 — Summary/Watchlist**: one row per company, all 13 metrics, credit grade, watchlist flag, color-coded (green/yellow/red) using conditional formatting
- **Tab 2 — Company Detail**: pick 2-3 companies (one strong, one weak, one borderline) and build a full one-page underwriting summary per company — trended ratios, stress scenario outputs, and a written 2-3 sentence rationale
- **Tab 3 — Stress Scenarios**: a matrix of company by scenario, showing stressed Debt/EBITDA or Interest Coverage under each of the 6 scenarios
- **Tab 4 — Assumptions**: every assumption you made (covenant thresholds, floating-rate percent, inventory stress percent) listed explicitly, so nothing is a hidden hardcode

Export your Python-calculated metrics to CSV, then either paste-link into Excel or write directly with `openpyxl` (you already have this pattern from the flash report projects) — building the formulas natively in Excel for at least the Summary tab is worth doing by hand once, since "I can build this in raw Excel, not just generate it with Python" is exactly the skill FP&A/credit roles test for.

---

## Phase 7: Build the Power BI dashboard

- **Page 1 — Portfolio Overview**: a table or matrix of all companies with grade/watchlist status, plus a scatter plot of Debt/EBITDA (x-axis) vs. Interest Coverage (y-axis) — this single chart tells most of the story visually
- **Page 2 — Company Deep Dive**: a slicer to pick one company, showing its trended ratios over 8 quarters and its stress scenario outputs
- **Page 3 — Stress Test Matrix**: a heatmap (company by scenario) showing which names breach covenant thresholds under which scenarios

Connect Power BI directly to your SQLite database (or export the final tables to CSV and import) so the dashboard reflects the same numbers as your Excel model and Python pipeline — reviewers do sometimes cross-check that your three deliverables agree with each other.

---

## Phase 8: Write the two-page credit memo

Pick the single most interesting company from your set (ideally one that's borderline or watchlist-flagged — "Approve" memos on obviously-healthy companies are less interesting to read). Structure:

1. **Recommendation** (top of page 1, one line): Approve / Approve with Conditions / Watchlist / Reject
2. **Company overview** (2-3 sentences): business, size, why it's in your dataset
3. **Key credit metrics** (a small table): the 13 metrics, actual vs. your assumed thresholds
4. **Trend commentary** (short paragraph): is leverage rising or falling, is margin compressing, what's driving it
5. **Stress test results** (short paragraph plus table): does the company survive the combined recession scenario, and by how much
6. **Recommendation rationale** (the core of page 2): why this recommendation, what conditions (if "approve with conditions"), what would move it to watchlist/reject
7. **Key risks** (bullet list): 3-4 specific risks, not generic ones

---

## Phase 9: Write the model-validation document

This is the deliverable that signals the most seniority, since it shows you understand the model's limits, not just its outputs. Cover:

- **Data sources and limitations**: SEC XBRL data, tag inconsistencies across companies, any gaps you had to leave blank rather than fill in
- **Key assumptions stated explicitly**: your assumed covenant thresholds, floating-rate debt percent, inventory stress percent, PD-proxy scoring bands — repeat these from Phase 3/4 so this document is self-contained
- **Known weaknesses of the Altman Z-score** for this use case (it was built and validated on manufacturing companies in the 1960s-70s; using it for modern retail/tech is a real, commonly-cited limitation — worth stating plainly)
- **Why the PD proxy is not a calibrated PD**: no historical default data was used to fit it; it's a rules-based scorecard, not a statistical model — say this directly rather than letting the name "probability of default" overstate what it is
- **Suggested next steps for a real deployment**: back-testing against actual historical downgrades/defaults, incorporating qualitative factors (management quality, competitive position) that no ratio captures

---

## Suggested build order if you want working output fast

1. Phase 1-2 (data pipeline) — get this solid first, everything depends on it
2. Phase 3 (metrics) for just 3-4 companies to sanity-check your formulas before scaling to all 10-12
3. Phase 5 (watchlist logic) — this is where the "system" part becomes visible
4. Phase 6 (Excel model) — your first full, presentable deliverable
5. Phases 4, 7, 8, 9 in whatever order you have time for — all are valuable, none are dependencies for each other

Want me to start building this with you? I'd suggest starting with the real SEC data pull for 3-4 companies and the core leverage/coverage/liquidity metrics — that gives us a working, real-data proof of concept before scaling to the full company list and all 13 metrics.
