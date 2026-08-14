# Credit Memo — Bath & Body Works, Inc. (BBWI)

**Recommendation: APPROVE WITH CONDITIONS**

| | |
|---|---|
| Internal grade | **BB** (PD proxy band: Medium) |
| Watchlist status | Medium (1 trigger) |
| Financials as of | 2026-05-02 (latest filed quarter) |
| Scorecard | 0.80 on a 0 = best / 2 = worst scale, 100% data coverage |
| Prepared from | SEC EDGAR XBRL filings via this repository's pipeline |

Inside every credit-policy test today, with identified deterioration or scenario sensitivity that warrants conditions.

---

## 1. Company overview

A specialty retailer of personal care and home fragrance, separated from its former parent in 2021. High margins and strong cash conversion, but the separation left it with a leveraged capital structure and negative book equity.

On the latest filed quarter the business generated $7.2bn of trailing-twelve-month revenue and $1.4bn of EBITDA, against $3.6bn of total debt and $820.0m of cash and short-term investments.

## 2. Key credit metrics

| Metric | Actual | Assumed threshold | Test |
|---|---:|---:|:---:|
| Revenue (TTM) | $7.2bn | — | — |
| EBITDA (TTM) | $1.4bn | — | — |
| Operating margin | 15.8% | — | — |
| Total debt | $3.6bn | — | — |
| Net debt | $2.8bn | — | — |
| Debt / EBITDA | 2.58x | ≤ 4.50x | Pass |
| Net debt / EBITDA | 2.00x | — | — |
| EBITDA / interest | 5.12x | ≥ 2.00x | Pass |
| Free cash flow (TTM) | $909.0m | — | — |
| FCF / debt | 25.2% | ≥ 5% | Pass |
| Current ratio | 1.38x | ≥ 1.00x | Pass |
| Quick ratio | 0.81x | — | — |
| Working capital | $522.0m | — | — |
| Altman Z" (non-manufacturer) | 1.20 | ≥ 1.1 | Pass |
| Covenant headroom | 1.92 turns | — | — |

Thresholds are the assumed credit policy defined in `src/config.py`; they are illustrative of public retail credit agreements, not real negotiated covenants.

## 3. Trend commentary

TTM EBITDA of $1.4bn fell 10.5% year on year; operating margin fell to 15.8% (-169bps YoY); leverage up 0.10 turns to 2.58x.

Interest coverage fell 1.3% to 5.12x; working capital fell 0.8% to $522.0m.

The leverage increase is earnings-driven rather than the result of new borrowing, which means it reverses if margin recovers and compounds if it does not. One early-warning test fired: operating margin down 169bps YoY.

## 4. Stress test results

| Scenario | EBITDA | Debt/EBITDA | EBITDA/interest | FCF/debt | Covenant |
|---|---:|---:|---:|---:|:---:|
| Baseline (as reported) | $1.4bn | 2.58x | 5.12x | 25.2% | Pass |
| Revenue -10% | $1.3bn | 2.87x | 4.61x | 22.8% | Pass |
| Revenue -20% | $1.1bn | 3.23x | 4.10x | 20.5% | Pass |
| EBITDA margin -300bps | $1.2bn | 3.06x | 4.33x | 21.5% | Pass |
| Rates +200bps | $1.4bn | 2.58x | 4.53x | 24.4% | Pass |
| Inventory +30% (cash funded) | $1.4bn | 2.58x | 5.12x | 18.7% | Pass |
| Combined recession | $1.0bn | 3.60x | 3.25x | 11.4% | Pass |

The name survives the combined recession scenario. EBITDA falls 28% to $1.0bn, taking leverage to 3.60x — still 0.90 turns inside the assumed 4.5x covenant. On the reported balance sheet, EBITDA would have to fall 43% from its current level before the covenant is breached at all. Of the individual shocks, *Revenue -20%* does the most damage, taking leverage to 3.23x.

Scenario assumptions: 50% of debt floating-rate, 80% of any EBITDA decline passing through to free cash flow, and a cash-funded 30% inventory build.

---

## 5. Recommendation rationale

The recommendation rests on 1 trigger across 1 category:

- **Deteriorating** — Operating margin down 169bps YoY (trigger 150bps).

**Conditions**

1. Quarterly reporting of the metrics below within 45 days of each 10-Q, with a written explanation of any further deterioration in the trend items identified above.
2. Margin recovery milestone: operating margin to stabilise within two quarters, or the facility is re-priced and the leverage test steps down.
3. Leverage covenant set with reference to the combined-recession outcome (3.60x), which leaves only 0.90 turns of headroom.

**What would change this view**

- *To Approve:* two consecutive quarters with no trigger firing and leverage sustained below 2.70x.
- *To Watchlist or Reject:* any credit-policy test breached on a reported quarter, Altman Z" below 1.1, or failure to meet the conditions above within the agreed window.

## 6. Key risks

1. **Negative book equity ($-1.1bn).** There is no equity cushion beneath the debt, recovery in a stress would depend entirely on going-concern value, and the Altman Z" of 1.20 reflects this directly.
2. **Interest-rate sensitivity.** Coverage of 5.12x leaves limited absorption for higher funding costs. A 200bps rate rise on the assumed 50% floating-rate share takes coverage to 4.53x.
3. **Deterioration already visible.** Operating margin down 169bps YoY (trigger 150bps).
4. **Model limitation.** Leverage here excludes capitalised operating leases and uses unadjusted EBITDA. A rating agency capitalising leases would report materially higher leverage for any store-based retailer, including this one.

---

## Basis of preparation

- All financial data is taken from Bath & Body Works, Inc.'s SEC filings via the XBRL API, as of the quarter ended 2026-05-02. Debt is sourced from *current + noncurrent legs*; EBIT from *reported*; interest on a *gross* basis.
- Covenant thresholds, the floating-rate share, the inventory build and the cash-flow passthrough are **assumptions**, not terms of any real agreement.
- The internal grade and PD proxy come from a rules-based scorecard that was not fitted to historical default data. They rank relative risk; they are not probabilities of default.
- Leverage excludes capitalised operating leases, and EBITDA is unadjusted (no addbacks for impairment, restructuring or stock compensation).
- The scorecard is quantitative only. It carries no view on management, competitive position or brand trajectory, all of which a credit committee would weigh alongside these figures.

*Generated by `src/build_memo.py` from the pipeline output. Regenerating after a data refresh will update every figure in this memo.*
