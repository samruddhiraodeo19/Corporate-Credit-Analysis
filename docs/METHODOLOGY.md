# Credit methodology

How each metric is defined, how the scorecard turns them into a grade, how the
stress scenarios work, and what puts a name on the watchlist.

Every threshold named here is a constant in `src/config.py` and is defined
nowhere else, so there is exactly one place to change any of them.

---

## 1. Metric definitions

All flow measures are trailing-twelve-month (TTM) sums of four consecutive
quarters. Balance-sheet measures are point-in-time at the quarter end. A TTM is
only produced when four genuinely consecutive quarters exist — a gap suppresses
it rather than summing across a longer span.

### Earnings

| Metric | Definition |
|---|---|
| **EBIT** | Reported `OperatingIncomeLoss` where tagged; otherwise pretax income less net interest income. Source recorded in `ebit_source`. |
| **EBITDA** | EBIT + depreciation & amortisation (TTM). Unadjusted — no addbacks. |
| **Operating margin** | EBIT (TTM) ÷ revenue (TTM) |

### Leverage

| Metric | Definition |
|---|---|
| **Total debt** | Current + noncurrent debt legs where either is disclosed; otherwise a combined debt tag. Never zero-filled from nothing. Includes finance leases where the registrant's tag includes them; **excludes operating leases**. |
| **Net debt** | Total debt − (cash + short-term investments) |
| **Debt/EBITDA** | Total debt ÷ EBITDA (TTM) |
| **Net debt/EBITDA** | Net debt ÷ EBITDA (TTM) |

A leverage multiple is **never** reported against negative EBITDA. −3.0x sorts
better than 8.0x but means the company has no earnings at all; those are
suppressed and the watchlist raises a separate high-severity trigger instead.

### Coverage

| Metric | Definition |
|---|---|
| **EBITDA/interest** | EBITDA (TTM) ÷ gross interest expense (TTM) |
| **EBIT/interest** | EBIT (TTM) ÷ gross interest expense (TTM) |

Where a company no longer discloses gross interest quarterly, net interest is
used and `interest_basis` records it. A company earning **net interest income**
has no interest burden: the ratio is undefined, reported as not-meaningful, and
scored as *strongest* — not as missing data.

### Cash flow

| Metric | Definition |
|---|---|
| **Free cash flow** | Operating cash flow − capital expenditure (TTM) |
| **FCF/debt** | FCF (TTM) ÷ total debt |
| **Cash burn** | Quarter-on-quarter change in cash, plus a count of consecutive negative-FCF quarters |

### Liquidity

| Metric | Definition |
|---|---|
| **Current ratio** | Current assets ÷ current liabilities |
| **Quick ratio** | (Current assets − inventory) ÷ current liabilities |
| **Working capital** | Current assets − current liabilities |

### Structure

| Metric | Definition |
|---|---|
| **Debt maturity profile** | The five-year ladder plus "thereafter", taken from XBRL where tagged. Used only if recent, complete, from a single filing date, and reconciling to balance-sheet debt within 25%. |
| **Refinancing concentration** | Debt due within 12 months ÷ total ladder |

### Distress

**Altman Z″** (the non-manufacturer revision):

```
Z" = 6.56·(WC/TA) + 3.26·(RE/TA) + 6.72·(EBIT/TA) + 1.05·(BookEquity/TL)
```

Zones: **< 1.1** distress · **1.1–2.6** grey · **> 2.6** safe.

Z′ (the private-firm variant, which retains an asset-turnover term) is computed
alongside for reference. See `docs/MODEL_VALIDATION.md` §3 for why Z″ is the
headline and what remains wrong with it.

---

## 2. Scorecard, grade and PD proxy

Seven factors, each scored **0 (best) / 1 / 2 (worst)** against stated bands,
then combined on fixed weights.

| Factor | Direction | Good (0 pts) | Weak (1 pt) | Weight |
|---|---|---|---|---|
| Debt/EBITDA | lower better | ≤ 2.0x | ≤ 4.0x | 25% |
| Net debt/EBITDA | lower better | ≤ 1.5x | ≤ 3.5x | 10% |
| EBITDA/interest | higher better | ≥ 6.0x | ≥ 3.0x | 20% |
| FCF/debt | higher better | ≥ 20% | ≥ 8% | 15% |
| Current ratio | higher better | ≥ 1.5x | ≥ 1.0x | 10% |
| Quick ratio | higher better | ≥ 0.8x | ≥ 0.4x | 5% |
| Altman Z″ | higher better | ≥ 2.6 | ≥ 1.1 | 15% |

The weighted average maps to a letter grade and a PD-proxy band:

| Score | Grade | | Score | Band |
|---|---|---|---|---|
| ≤ 0.15 | AA | | ≤ 0.40 | Low |
| ≤ 0.40 | A | | ≤ 1.00 | Medium |
| ≤ 0.75 | BBB | | > 1.00 | High |
| ≤ 1.10 | BB | | | |
| ≤ 1.50 | B | | | |
| > 1.50 | CCC | | | |

### Two rules that matter more than the bands

**Missing data is excluded, not scored as clean.** A factor with no data drops
out of both the numerator and the denominator, and the share of weight actually
available is reported as `scorecard_coverage`. Below 60% coverage the grade is
suppressed to **NR** rather than reported. An earlier version scored missing
data as zero points, which handed "A" grades to companies whose debt simply
hadn't extracted.

**Undefined-because-favourable is distinguished from undefined-because-missing.**
A debt-free company has no FCF/debt ratio and a net-interest-earning company
has no coverage ratio. Both score 0 points — the strongest outcome — because in
each case the ratio is undefined for a good reason.

The PD-proxy band is a **relative ranking, not a probability**. See
`docs/MODEL_VALIDATION.md` §3.

---

## 3. Stress scenarios

Seven scenarios — baseline plus six shocks — all run through one function, so
the calculation cannot drift between them.

| Scenario | Shock |
|---|---|
| Baseline | As reported |
| Revenue −10% | Volume decline at constant EBITDA margin |
| Revenue −20% | Same, deeper |
| EBITDA margin −300bps | Margin compression on unstressed revenue |
| Rates +200bps | Repricing of the assumed 50% floating-rate share |
| Inventory +30% | Cash-funded merchandise build |
| Combined recession | Revenue −15%, margin −300bps, rates +200bps, inventory +30% |

### How each shock propagates

- **Revenue** scales EBITDA at a constant margin.
- **Margin** subtracts percentage points from the EBITDA margin, applied to
  unstressed revenue. This is the shock that breaks thin-margin businesses: at
  a 1.7% margin, −300bps is an 80% EBITDA decline.
- **Rates** add interest on the floating-rate share only. Fixed-rate debt is
  unaffected, so this moves coverage and cash flow but **cannot move a leverage
  multiple** — which is why the outputs carry a separate coverage matrix.
- **Inventory** is assumed cash-funded: inventory up, cash down, total current
  assets unchanged. That hits the quick ratio and net debt but not the current
  ratio, which is the correct signature of a stock build.
- **Cash flow is stressed too**, not held at baseline. An EBITDA decline
  reaches FCF at 80% (a sales decline releases working capital, cushioning the
  first year), net of tax at 25%, and the inventory build is charged as a
  one-off outflow.

---

## 4. Watchlist triggers

Three independent families, because they catch different things. Every firing
records the actual value against the threshold, so "why is this name on the
list?" is answered with a number.

### Level — already outside credit policy today

| Trigger | Threshold | Severity |
|---|---|---|
| Debt/EBITDA above assumed covenant | > 4.50x | High |
| TTM EBITDA negative (leverage not meaningful) | ≤ 0 | High |
| Interest coverage below floor | < 2.00x | High |
| Altman Z″ in distress zone | < 1.1 | High |
| Current ratio below floor | < 1.00x | Medium |
| FCF/debt too thin to deleverage | < 5% | Medium |

### Trend — still compliant, but moving the wrong way

This is the early-warning half of the system. The point is to call a name
*before* it breaches.

| Trigger | Threshold | Severity |
|---|---|---|
| Leverage rising | > +0.75 turns YoY | Medium |
| Operating margin compressing | > −150bps YoY | Medium |
| TTM EBITDA declining | > −15% YoY | Medium |
| Consecutive negative-FCF quarters | ≥ 2 | Medium |
| Refinancing concentration | > 25% due within 12m | Medium |
| Interest coverage deteriorating | > −25% YoY | Low |
| Working capital shrinking | > −20% YoY | Low |

Year-on-year comparisons are guarded on the actual date gap (330–400 days), so
a company with a missing quarter is never compared against an 18-month-old
figure.

### Stress — compliant today, breaches under a defined scenario

Raised when a scenario pushes leverage through the covenant or coverage below
the floor. Names **already** in breach at baseline are not double-reported
here; the level triggers have them.

### Severity

`High > Medium > Low > Clear`, taking the worst trigger fired, then ranked by
trigger count. This drives the review queue: a breach today outranks a
projected one.

---

## 5. From triggers to a recommendation

The credit memo (`src/build_memo.py`) maps the evidence to one of four standard
decisions:

| Evidence | Recommendation |
|---|---|
| ≥ 2 high-severity level triggers | **Reject** |
| 1 high-severity level trigger | **Watchlist** |
| Any medium/low trigger, no level breach | **Approve with conditions** |
| No triggers | **Approve** |

Conditions attach to the triggers that actually fired — a margin trigger
produces a margin-recovery milestone, a refinancing concentration produces a
refinancing-plan deadline — rather than a generic checklist.
