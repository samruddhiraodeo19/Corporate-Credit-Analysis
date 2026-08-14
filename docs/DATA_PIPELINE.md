# Data pipeline

How raw SEC XBRL becomes a clean quarterly panel. This is where most of the
engineering in the project sits, because filings data does not arrive in a
usable shape and the failure modes are quiet — they produce confident-looking
numbers rather than errors.

---

## Stages

```
fetch_data.py    →  data/raw/{TICKER}.json     one companyfacts pull per issuer
build_db.py      →  db/credit_risk.db          normalised quarterly panel
validate.py                                    reconciles the panel to the filings
calc_metrics.py  →  output/metrics_*.csv       the metric suite + scorecard
stress_test.py   →  output/stress_*.csv        7 scenarios per company
watchlist.py     →  output/watchlist*.csv      level / trend / stress triggers
build_excel.py   →  credit_underwriting_model.xlsx
build_powerbi.py →  output/powerbi/            star schema + DAX
build_dashboard.py → output/dashboard.html
build_memo.py    →  output/memos/*.md
```

`run_pipeline.py` runs all ten in order. `--refresh` forces a re-pull from SEC.

---

## 1. Fetching

Uses the **`companyfacts`** endpoint — one request per company returning every
tagged concept — rather than `companyconcept`, which needs one request per tag.
That is ~20× fewer requests, but the real reason is that it lets the mapping
layer see every concept the company has *ever* reported, which is what makes
coalescing across taxonomy changes possible.

Responses are trimmed to the concepts the project uses before caching, so
`data/raw/` holds ~500KB per company rather than ~4MB.

SEC requires real contact details in the User-Agent and returns 403 without
them. It is resolved at runtime from `SEC_USER_AGENT` or a gitignored
`.sec_user_agent` file, never committed. A ticker that no longer resolves is a
**hard error**, not a silent skip — `JWN`, `GPS` and `FL` all stopped resolving
(Nordstrom went private, Gap's ticker changed, Foot Locker was acquired), and
an earlier version quietly analysed 7 companies while reporting 10.

---

## 2. Normalisation — the five real problems

### Instant vs duration facts

Balance-sheet concepts are point-in-time (no `start`); income-statement and
cash-flow concepts cover a period. They cannot be handled the same way, and
only the latter are TTM-summed.

### Year-to-date cash flows

Retailers report cash-flow statements **cumulatively from the fiscal-year
start**. Target's Q2 operating cash flow fact runs `2025-02-02 → 2025-08-02` —
26 weeks, not 13.

Filtering to "facts about 90 days long" therefore keeps only Q1 of each year
and throws away the other three. The fix: facts sharing a `start` are sorted by
`end` and **differenced**.

```
YTD(Feb→May)  = Q1
YTD(Feb→Aug)  − YTD(Feb→May)  = Q2
YTD(Feb→Nov)  − YTD(Feb→Aug)  = Q3
FY (Feb→Jan)  − YTD(Feb→Nov)  = Q4
```

Only differences landing on a ~13-week window are kept, so a gap (a missing
year-to-date fact) produces a 26-week difference that is correctly discarded
rather than silently booked as one quarter.

### No discrete Q4

10-Ks report the full year only, so a rolling four-quarter window would never
complete. Q4 falls out of the same differencing step, as the last line above.

Natively-reported 13-week facts always beat anything reconstructed by
subtraction; `is_derived` records which is which.

### Taxonomy drift

The concept a company uses **changes over time**:

| Company | Change |
|---|---|
| Target | left `Revenues` in FY2015, `LongTermDebtNoncurrent` in FY2013 |
| Dick's | moved to `UnsecuredDebt` in FY2019 |
| Macy's | stopped tagging gross interest quarterly in FY2023 |
| Gap | tags inventory as `InventoryFinishedGoodsNetOfReserves` |
| Burlington, TJX | never tag an operating-income subtotal |

"Try each tag, take the first that returns data" locks onto a **dead** concept
and produces NaN or zero for every modern period — the single largest source of
silent wrongness in this domain. Instead, each metric **coalesces across its
candidate concepts period-by-period**: for each quarter, the first concept in
the list that reports a value wins, so a series survives a mid-history change.

Where no concept exists at all, there is a documented derivation:

- **EBIT** ← pretax income less net interest income
- **Interest** ← net interest expense, with `interest_basis` flagging it
- **Total debt** ← a combined debt tag, only where neither leg is disclosed
- **Total liabilities** ← Total assets − total equity

### Restatements

The same period is often reported twice — in a 10-Q, then restated in the next
10-K. The most recently **filed** value wins, ties broken deterministically on
accession number.

---

## 3. Design rules

**Missing is never zero.** "We could not extract this company's debt" and "this
company has no debt" are different facts. Every metric propagates NaN rather
than defaulting to zero. An earlier version summed missing debt legs with
`.fillna(0)` and reported $0 debt — and an "A" grade — for four companies that
plainly have debt.

**...but a repaid balance is zero.** A company that repays its last borrowing
stops tagging debt concepts entirely, because the caption leaves its balance
sheet. Abercrombie tagged `LongTermDebtNoncurrent = 0` through FY2024 and then
dropped it. Where the last value a company actually reported was zero, later
gaps are treated as nil debt; companies that *never* reported a debt concept
stay NaN, since that could equally be an extraction failure.

**A TTM needs four genuinely consecutive quarters.** If one is missing, the
four available rows span more than a year and their sum would overstate the
period, so the TTM is withheld.

**Balance-sheet values carry forward at most one quarter**, and
`balance_sheet_as_of` records the date the figures are really as of.

**Stale disclosures are dropped, not used.** Kohl's last tagged a debt-maturity
bucket in 2011; read literally it claims 100% of today's debt matures within a
year. Ross's ladder was current but showed $500m due within a year that it had
*already repaid*. Ladders must be recent, complete, from a single filing date,
and still reconcile to balance-sheet debt within 25%.

---

## 4. Schema

```sql
companies      ticker, cik, company_name, fetched_at
financials     ticker, metric, tag_used, fact_type, fiscal_year, fiscal_quarter,
               period_start_date, period_end_date, form, filed_date,
               is_derived, value          -- long format, PK (ticker, metric, period)
debt_maturity  ticker, bucket, period_end_date, filed_date, value
data_quality   ticker, metric, tags_used, quarters_found,
               first_period, last_period, derived_share
```

Long format means a new metric never requires a schema change. `data_quality`
is the extraction audit — which concept fed each metric, how much history it
covers, and how much was reconstructed from year-to-date figures. It surfaces
in the workbook's Data Quality tab.

---

## 5. Validation

`validate.py` re-reads the raw facts and reconciles the panel against them
independently of the code that built it, failing the run on any invariant
violation. **1,321 fiscal years currently reconcile exactly** to their filed
annual figures — the direct proof that de-cumulation and Q4 derivation are
correct.

Full results, the explained discrepancies, and the bugs these checks caught are
in [`MODEL_VALIDATION.md`](MODEL_VALIDATION.md) §4.

---

## 6. Extending it

**Add a company** — put the ticker in `COMPANIES` in `src/config.py` and add a
`COMPANY_PROFILES` entry (used by the memo) and a `SECTORS` entry in
`build_powerbi.py`. Run with `--refresh`.

**Add a metric** — add its candidate concepts to `TAG_FALLBACKS`, list it in
`FLOW_METRICS` if it is a flow, then compute it in `calc_metrics.py`. Add it to
`METRIC_CATALOGUE` in `build_powerbi.py` and it appears in the dashboard and
the Power BI model without a new visual.

**Change a threshold** — every one is a named constant in `src/config.py` and
is defined nowhere else. The Excel model reads the covenant through a live
formula, so changing it re-rates the portfolio in the workbook too.

**Add a stress scenario** — one entry in `SCENARIOS` in `stress_test.py`.
Scenarios are data, not code, and all share one calculation.
