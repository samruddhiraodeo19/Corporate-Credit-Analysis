# Model validation

This document states what the model does, what it assumes, where it is weak,
and what evidence exists that it computes what it claims to. It is the
deliverable that matters most for a credit model, because the outputs are only
worth as much as the reader's ability to judge their limits.

It corresponds to Phase 9 of `PLAN.md`.

---

## 1. Data sources and their limitations

**Source.** Every financial figure comes from SEC EDGAR's XBRL `companyfacts`
API — one request per company returning every concept the registrant has ever
tagged. Nothing is entered by hand. Company business descriptions
(`COMPANY_PROFILES` in `src/config.py`) and sector labels are the only
analyst-supplied content, and both are qualitative.

**Coverage.** Twelve US retail and consumer-discretionary issuers, chosen to
mix clearly-strong balance sheets with clearly-stressed ones so the watchlist
has real dispersion. Banks and insurers are excluded deliberately: standard
credit ratios do not mean what the textbook says on a financial-institution
balance sheet.

### Limitations inherent to the source

| Limitation | Effect | How the pipeline responds |
|---|---|---|
| **Taxonomy drift** — the concept a company uses changes over time. Target left `Revenues` in FY2015 and `LongTermDebtNoncurrent` in FY2013; Dick's moved to `UnsecuredDebt`; Macy's stopped tagging gross interest quarterly in FY2023. | Selecting one tag up front locks onto a dead concept and silently yields NaN or zero for every modern period. | Metrics are **coalesced across candidate concepts period-by-period**, so a series survives a mid-history tag change. |
| **No operating-income subtotal** — Burlington has never tagged `OperatingIncomeLoss`; TJX stopped in FY2019. | EBIT, and therefore EBITDA and every leverage ratio, is unavailable. | EBIT is rebuilt bottom-up as pretax income less net interest income, and the derivation is recorded in `ebit_source`. |
| **Year-to-date cash flows** — retailers report cash-flow statements cumulatively from the fiscal-year start, so a Q3 10-Q covers ~39 weeks. | Filtering to "facts about 90 days long" discards three quarters of every year, and TTM can never fill. | Facts sharing a `start` are sorted by `end` and differenced to recover each discrete quarter. |
| **No discrete Q4** — 10-Ks report the full year only. | A rolling four-quarter window never completes. | Q4 falls out of the same differencing step: the annual figure minus the nine-month year-to-date one. |
| **Restatements** — the same period is reported in a 10-Q and again, restated, in the next 10-K. | Duplicate and conflicting values for one period. | The most recently **filed** value wins, ties broken on accession number. |
| **Stale disclosures** — Kohl's last tagged a debt-maturity bucket in **2011**. | Read literally, it says 100% of today's debt matures within a year. | Maturity ladders are used only if recent, complete (≥3 buckets), from a single filing date, and still reconciling to balance-sheet debt within 25%. |
| **Missing `Liabilities` subtotal** — only 1 of the 12 issuers tags it. | Altman's equity-to-liabilities term is uncomputable. | Derived from the balance-sheet identity: Total Assets − Total Equity. |
| **Filing lag** | Metrics reflect the last filed quarter and can be up to a quarter stale. | The as-of date is on every output; `balance_sheet_as_of` records carry-forward. |

### Gaps deliberately left blank

The debt maturity ladder is left empty rather than estimated where a company
never tags it, or where it fails the reconciliation test. `scorecard_missing`
records which factors had no data for each company, and `scorecard_coverage`
reports the share of scorecard weight actually available.

---

## 2. Assumptions, stated explicitly

None of the following are real negotiated terms. Real credit agreements are
private. These are illustrative values in the range typically seen in public
retail credit agreements and rating-agency criteria. All live in
`src/config.py` and nowhere else.

### Credit policy

| Assumption | Value | Basis |
|---|---|---|
| Maximum Debt/EBITDA (assumed covenant) | 4.50x | Typical total-leverage maintenance test in public retail term loans |
| Minimum EBITDA/interest coverage | 2.00x | Typical minimum coverage test |
| Minimum current ratio | 1.00x | Working-capital liquidity floor |
| Minimum FCF/debt | 5% | Below this, cash flow cannot meaningfully deleverage the balance sheet |
| Refinancing concentration trigger | 25% of debt due within 12 months | Judgement |

### Stress scenarios

| Assumption | Value | Why |
|---|---|---|
| Floating-rate share of debt | 50% | Filings rarely give a clean fixed/floating split. Only this share reprices in the rate scenario. |
| Inventory build | +30%, cash-funded | A cash-funded build swaps one current asset for another, so it hits the quick ratio and net debt but not the current ratio — the correct signature of a stock build. |
| EBITDA-to-FCF passthrough | 80% | A sales decline releases working capital, cushioning first-year cash flow, so an EBITDA fall does not reach FCF one-for-one. |
| Cash tax rate | 25% | Converts the pre-tax earnings shock into an after-tax cash-flow shock. |

### Early-warning triggers

Leverage +0.75 turns YoY · operating margin −150bps YoY · TTM EBITDA −15% YoY ·
interest coverage −25% YoY · working capital −20% YoY · 2 consecutive
negative-FCF quarters.

These are judgement calls, calibrated so that a name still inside its covenants
but moving materially in the wrong direction is surfaced before it breaches.

### Scorecard bands

Seven factors, each scored 0 (best) / 1 / 2 (worst) against stated bands and
combined on fixed weights (leverage 35%, coverage 20%, cash flow 15%, liquidity
15%, distress score 15%). Grade cutoffs and the full band table are in
`src/config.py` under `SCORECARD` and `GRADE_BANDS`.

---

## 3. Known weaknesses

### The Altman Z-score

This pipeline uses **Z″**, the non-manufacturer revision, not the original 1968
Z:

```
Z" = 6.56·(WC/TA) + 3.26·(RE/TA) + 6.72·(EBIT/TA) + 1.05·(BookEquity/TL)
```

Zones: below 1.1 distress · 1.1–2.6 grey · above 2.6 safe.

**Why not the original Z.** The 1968 model was built and validated on
*manufacturing* companies, using a market-capitalisation term that XBRL does
not carry and an asset-turnover term that systematically flatters
high-turnover retailers — a discounter can post a strong Z on sales velocity
alone while carrying real credit stress. Z″ drops the turnover term and uses
book equity, so it is both fully computable from filings and the variant
Altman himself recommends for non-manufacturers.

**Weaknesses that remain.** Z″ was still calibrated decades ago, on a sample
containing no modern e-commerce or omni-channel retailers, and no company with
today's lease-accounting treatment. Asset-light businesses look worse on
`WC/TA` and `RE/TA` than their cash generation warrants; a company that has
bought back stock for years carries negative retained earnings and scores
poorly regardless of its actual capacity to service debt. **Treat the zone as a
ranking signal, not a verdict.**

### The probability-of-default proxy

**It is not a probability of default.** It is a rules-based scorecard that was
never fitted to historical default data, because no default history was used
anywhere in this project. The Low / Medium / High bands are a *relative
ranking* of the twelve names against each other and against stated thresholds.
They cannot be read as "x% chance of default", compared against agency default
studies, or used to price risk. The name "PD proxy" is retained because it
describes the role the score plays, not the statistics behind it.

A genuine PD model would need a default-flagged panel spanning at least one
full credit cycle, a fitted statistical model (logistic regression or a hazard
model), out-of-sample and out-of-time testing, and recalibration against
realised default rates.

### Definitional conservatism

- **Operating leases are excluded from debt.** Rating agencies commonly
  capitalise them, which would raise leverage materially for every store-based
  retailer here. Reported leverage is therefore *lower* than an agency-adjusted
  figure — the most important single caveat on these numbers.
- **EBITDA is unadjusted.** No addbacks for impairment, restructuring or
  stock-based compensation, so it is more conservative than a credit
  agreement's "Adjusted EBITDA" definition would allow.
- **Coverage is computed on gross interest where disclosed**, but on net
  interest for companies that stopped reporting gross quarterly. The
  `interest_basis` column flags which.
- **Undefined ratios are distinguished from missing data.** A debt-free
  company has no leverage multiple and a company earning net interest income
  has no coverage ratio; both are scored as *strongest*, with the reasoning
  recorded, rather than dropped as gaps.

### Scope

The scorecard is **purely quantitative**. It has no view on management quality,
competitive position, brand trajectory or channel shift. A structurally
declining retailer with clean current ratios will score better here than a
credit committee would grade it. This is the single largest gap between this
model's output and a real internal rating.

---

## 4. Validation evidence

`src/validate.py` re-reads the raw SEC facts and reconciles the built panel
against them **independently of the code that built it**. It runs as a gate
inside the pipeline and fails the run on any invariant violation.

| Check | What it proves | Current result |
|---|---|---|
| **TTM reconciliation** | Where all four quarters of a fiscal year came from the same concept, they must sum to that concept's filed annual figure. This is the direct test of the de-cumulation and Q4-derivation logic. | **1,321 fiscal years reconcile exactly** |
| **Debt precedence** | A combined debt tag is never used where a current/noncurrent leg exists, so the two cannot double-count. | 323 overlapping company-quarters, 0 violations |
| **Balance-sheet containment** | Inventory ≤ current assets ≤ total assets; no negative stocks. | 865 company-quarters, 0 violations |
| **Quarter shape** | Each quarter is a plausible share of its trailing year — would catch a half-year mistakenly booked as a quarter. | 788 quarters, 1 flagged for review |

### Discrepancies investigated and explained

Reported as warnings, not failures, because each has an identified cause and
none affects the periods the metrics consume:

- **Bath & Body Works FY2019** — quarters sum to ~$12.9bn against a filed
  $5.4bn. The quarters are pre-separation *L Brands* consolidated figures; the
  annual was restated to Bath & Body Works only after the Victoria's Secret
  spin-off. The original 10-Q quarters were never refiled.
- **Target pre-2015** — figures restated for the Canada exit and discontinued
  operations, while the original quarterly filings stand.
- **Bath & Body Works Q1 FY2020 at 6.9% of its trailing year** — the COVID
  shutdown quarter, when the entire store estate was closed. Real, not an
  extraction error.

Failures are enforced only for periods within the trailing three years, which
is the window the metrics actually consume.

### Bugs this validation caught

Documented because they are the reason the checks exist:

1. A maturity ladder assembled from buckets tagged in *different years*,
   producing "100% of Kohl's debt matures within 12 months" off a 2011
   disclosure.
2. A ladder that was internally consistent but stale — Ross's showed $500m due
   within a year that it had already repaid, visible only because the ladder no
   longer reconciled to balance-sheet debt.
3. Derived EBIT overstated for TJX by roughly $200m a year, because net
   interest *income* was not being backed out of pretax income.

---

## 5. Suggested next steps for a real deployment

1. **Back-test against realised outcomes.** Assemble a default- and
   downgrade-flagged panel across a full credit cycle and measure whether the
   watchlist actually led rating actions. Until this exists, the trigger
   thresholds are reasoned but unproven.
2. **Fit a real PD model** on that panel and retire the scorecard proxy, or
   keep the scorecard as an interpretable overlay on a fitted model.
3. **Capitalise operating leases** and report leverage on both bases, so the
   output is comparable to agency metrics.
4. **Incorporate qualitative factors** — management, competitive position,
   channel exposure — that no ratio captures, most likely as an analyst
   override with a recorded justification.
5. **Add market-based signals** (bond spreads, CDS, equity volatility) as a
   cross-check. They move well before filings do, and would materially improve
   the "early warning" claim.
6. **Widen the universe beyond retail** and confirm the concept-mapping layer
   generalises; the tag-coalescing approach should, but it has only been tested
   on twelve issuers in one sector.
7. **Schedule against the filing calendar** so the panel refreshes as 10-Qs land.
