# Credit Memo — TARGET CORP (TGT)

**Recommendation: APPROVE WITH CONDITIONS**

| | |
|---|---|
| Internal grade | **BBB** (PD proxy band: Medium) |
| Watchlist status | Medium (1 trigger) |
| Financials as of | 2026-05-02 (latest filed quarter) |
| Scorecard | 0.60 on a 0 = best / 2 = worst scale, 100% data coverage |
| Prepared from | SEC EDGAR XBRL filings via this repository's pipeline |

Inside every credit-policy test today, with identified deterioration or scenario sensitivity that warrants conditions.

---

## 1. Company overview

A national mass merchant selling general merchandise and food through owned and leased large-format stores, with a growing same-day fulfilment business. Scale and an investment-grade balance sheet are the credit strengths; discretionary-heavy mix is the cyclical exposure.

On the latest filed quarter the business generated $106.4bn of trailing-twelve-month revenue and $7.9bn of EBITDA, against $15.4bn of total debt and $8.1bn of cash and short-term investments.

## 2. Key credit metrics

| Metric | Actual | Assumed threshold | Test |
|---|---:|---:|:---:|
| Revenue (TTM) | $106.4bn | — | — |
| EBITDA (TTM) | $7.9bn | — | — |
| Operating margin | 4.5% | — | — |
| Total debt | $15.4bn | — | — |
| Net debt | $7.3bn | — | — |
| Debt / EBITDA | 1.94x | ≤ 4.50x | Pass |
| Net debt / EBITDA | 0.92x | — | — |
| EBITDA / interest | 17.76x | ≥ 2.00x | Pass |
| Free cash flow (TTM) | $3.0bn | — | — |
| FCF / debt | 19.7% | ≥ 5% | Pass |
| Current ratio | 0.93x | ≥ 1.00x | **Fail** |
| Quick ratio | 0.30x | — | — |
| Working capital | $-1.3bn | — | — |
| Altman Z" (non-manufacturer) | 1.36 | ≥ 1.1 | Pass |
| Covenant headroom | 2.56 turns | — | — |

Thresholds are the assumed credit policy defined in `src/config.py`; they are illustrative of public retail credit agreements, not real negotiated covenants.

## 3. Trend commentary

TTM EBITDA of $7.9bn fell 9.7% year on year; operating margin fell to 4.5% (-93bps YoY); leverage up 0.18 turns to 1.94x.

Interest coverage fell 14.9% to 17.76x; working capital fell 7.1% to $-1.3bn; free cash flow has been negative for 1 consecutive quarter.

The leverage increase is earnings-driven rather than the result of new borrowing, which means it reverses if margin recovers and compounds if it does not. No early-warning test fired this quarter.

## 4. Stress test results

| Scenario | EBITDA | Debt/EBITDA | EBITDA/interest | FCF/debt | Covenant |
|---|---:|---:|---:|---:|:---:|
| Baseline (as reported) | $7.9bn | 1.94x | 17.76x | 19.7% | Pass |
| Revenue -10% | $7.1bn | 2.16x | 15.99x | 16.6% | Pass |
| Revenue -20% | $6.4bn | 2.43x | 14.21x | 13.5% | Pass |
| EBITDA margin -300bps | $4.7bn | 3.25x | 10.62x | 7.2% | Pass |
| Rates +200bps | $7.9bn | 1.94x | 13.21x | 18.9% | Pass |
| Inventory +30% (cash funded) | $7.9bn | 1.94x | 17.76x | -4.3% | Pass |
| Combined recession | $4.0bn | 3.82x | 6.71x | -20.3% | Pass |

The name survives the combined recession scenario. EBITDA falls 49% to $4.0bn, taking leverage to 3.82x — still 0.68 turns inside the assumed 4.5x covenant. On the reported balance sheet, EBITDA would have to fall 57% from its current level before the covenant is breached at all. Of the individual shocks, *EBITDA margin -300bps* does the most damage, taking leverage to 3.25x.

Scenario assumptions: 50% of debt floating-rate, 80% of any EBITDA decline passing through to free cash flow, and a cash-funded 30% inventory build.

---

## 5. Recommendation rationale

The recommendation rests on 1 trigger across 1 category:

- **Breached today** — Current ratio 0.93x below 1.0x.

**Conditions**

1. Leverage covenant set with reference to the combined-recession outcome (3.82x), which leaves only 0.68 turns of headroom.

**What would change this view**

- *To Approve:* two consecutive quarters with no trigger firing and leverage sustained below 2.70x.
- *To Watchlist or Reject:* any credit-policy test breached on a reported quarter, Altman Z" below 1.1, or failure to meet the conditions above within the agreed window.

## 6. Key risks

1. **Margin convexity.** At a 4.5% operating margin, a small absolute change in margin is a large proportional change in EBITDA, so leverage is far more sensitive to pricing and freight than the headline multiple suggests. A 300bps margin loss alone takes leverage to 3.25x.
2. **Working-capital dependence.** A current ratio of 0.93x means the business runs on supplier financing; any tightening of vendor terms or credit insurance would pressure liquidity quickly, and the assumed 30% inventory build takes the quick ratio to 0.11x.
3. **Model limitation.** Leverage here excludes capitalised operating leases and uses unadjusted EBITDA. A rating agency capitalising leases would report materially higher leverage for any store-based retailer, including this one.

---

## Basis of preparation

- All financial data is taken from TARGET CORP's SEC filings via the XBRL API, as of the quarter ended 2026-05-02. Debt is sourced from *current + noncurrent legs*; EBIT from *reported*; interest on a *gross* basis.
- Covenant thresholds, the floating-rate share, the inventory build and the cash-flow passthrough are **assumptions**, not terms of any real agreement.
- The internal grade and PD proxy come from a rules-based scorecard that was not fitted to historical default data. They rank relative risk; they are not probabilities of default.
- Leverage excludes capitalised operating leases, and EBITDA is unadjusted (no addbacks for impairment, restructuring or stock compensation).
- The scorecard is quantitative only. It carries no view on management, competitive position or brand trajectory, all of which a credit committee would weigh alongside these figures.

*Generated by `src/build_memo.py` from the pipeline output. Regenerating after a data refresh will update every figure in this memo.*
