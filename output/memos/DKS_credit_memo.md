# Credit Memo — DICK'S SPORTING GOODS, INC. (DKS)

**Recommendation: APPROVE WITH CONDITIONS**

| | |
|---|---|
| Internal grade | **AA** (PD proxy band: Low) |
| Watchlist status | Medium (2 triggers) |
| Financials as of | 2026-05-02 (latest filed quarter) |
| Scorecard | 0.10 on a 0 = best / 2 = worst scale, 100% data coverage |
| Prepared from | SEC EDGAR XBRL filings via this repository's pipeline |

Inside every credit-policy test today, with identified deterioration or scenario sensitivity that warrants conditions.

---

## 1. Company overview

The largest US sporting-goods retailer, recently enlarged by a major acquisition that materially changed the earnings and debt profile. Integration execution is the dominant near-term credit variable.

On the latest filed quarter the business generated $19.2bn of trailing-twelve-month revenue and $1.7bn of EBITDA, against $1.9bn of total debt and $998.2m of cash and short-term investments.

## 2. Key credit metrics

| Metric | Actual | Assumed threshold | Test |
|---|---:|---:|:---:|
| Revenue (TTM) | $19.2bn | — | — |
| EBITDA (TTM) | $1.7bn | — | — |
| Operating margin | 6.1% | — | — |
| Total debt | $1.9bn | — | — |
| Net debt | $907.6m | — | — |
| Debt / EBITDA | 1.10x | ≤ 4.50x | Pass |
| Net debt / EBITDA | 0.53x | — | — |
| EBITDA / interest | 24.76x | ≥ 2.00x | Pass |
| Free cash flow (TTM) | $402.6m | — | — |
| FCF / debt | 21.1% | ≥ 5% | Pass |
| Current ratio | 1.50x | ≥ 1.00x | Pass |
| Quick ratio | 0.38x | — | — |
| Working capital | $2.4bn | — | — |
| Altman Z" (non-manufacturer) | 3.10 | ≥ 1.1 | Pass |
| Covenant headroom | 3.40 turns | — | — |

Thresholds are the assumed credit policy defined in `src/config.py`; they are illustrative of public retail credit agreements, not real negotiated covenants.

## 3. Trend commentary

TTM EBITDA of $1.7bn fell 10.0% year on year; operating margin fell to 6.1% (-495bps YoY); leverage up 0.33 turns to 1.10x.

Interest coverage fell 33.7% to 24.76x; working capital rose 26.5% to $2.4bn; free cash flow has been negative for 1 consecutive quarter.

The leverage increase is earnings-driven rather than the result of new borrowing, which means it reverses if margin recovers and compounds if it does not. Two early-warning tests fired: operating margin down 495bps YoY; interest coverage down 33.7% YoY.

## 4. Stress test results

| Scenario | EBITDA | Debt/EBITDA | EBITDA/interest | FCF/debt | Covenant |
|---|---:|---:|---:|---:|:---:|
| Baseline (as reported) | $1.7bn | 1.10x | 24.76x | 21.1% | Pass |
| Revenue -10% | $1.6bn | 1.23x | 22.29x | 15.7% | Pass |
| Revenue -20% | $1.4bn | 1.38x | 19.81x | 10.3% | Pass |
| EBITDA margin -300bps | $1.1bn | 1.66x | 16.49x | 3.0% | Pass |
| Rates +200bps | $1.7bn | 1.10x | 19.44x | 20.4% | Pass |
| Inventory +30% (cash funded) | $1.7bn | 1.10x | 24.76x | -64.2% | Pass |
| Combined recession | $976.5m | 1.95x | 11.01x | -88.5% | Pass |

The name survives the combined recession scenario. EBITDA falls 43% to $976.5m, taking leverage to 1.95x — still 2.55 turns inside the assumed 4.5x covenant. On the reported balance sheet, EBITDA would have to fall 75% from its current level before the covenant is breached at all. Of the individual shocks, *EBITDA margin -300bps* does the most damage, taking leverage to 1.66x.

Scenario assumptions: 50% of debt floating-rate, 80% of any EBITDA decline passing through to free cash flow, and a cash-funded 30% inventory build.

---

## 5. Recommendation rationale

The recommendation rests on 2 triggers across 1 category:

- **Deteriorating** — Operating margin down 495bps YoY (trigger 150bps).
- **Deteriorating** — Interest coverage down 33.7% YoY (trigger 25%).

**Conditions**

1. Quarterly reporting of the metrics below within 45 days of each 10-Q, with a written explanation of any further deterioration in the trend items identified above.
2. Margin recovery milestone: operating margin to stabilise within two quarters, or the facility is re-priced and the leverage test steps down.

**What would change this view**

- *To Approve:* two consecutive quarters with no trigger firing and leverage sustained below 2.70x.
- *To Watchlist or Reject:* any credit-policy test breached on a reported quarter, Altman Z" below 1.1, or failure to meet the conditions above within the agreed window.

## 6. Key risks

1. **Deterioration already visible.** Operating margin down 495bps YoY (trigger 150bps).
2. **Deterioration already visible.** Interest coverage down 33.7% YoY (trigger 25%).
3. **Model limitation.** Leverage here excludes capitalised operating leases and uses unadjusted EBITDA. A rating agency capitalising leases would report materially higher leverage for any store-based retailer, including this one.

---

## Basis of preparation

- All financial data is taken from DICK'S SPORTING GOODS, INC.'s SEC filings via the XBRL API, as of the quarter ended 2026-05-02. Debt is sourced from *combined debt tag*; EBIT from *reported*; interest on a *gross* basis.
- Covenant thresholds, the floating-rate share, the inventory build and the cash-flow passthrough are **assumptions**, not terms of any real agreement.
- The internal grade and PD proxy come from a rules-based scorecard that was not fitted to historical default data. They rank relative risk; they are not probabilities of default.
- Leverage excludes capitalised operating leases, and EBITDA is unadjusted (no addbacks for impairment, restructuring or stock compensation).
- The scorecard is quantitative only. It carries no view on management, competitive position or brand trajectory, all of which a credit committee would weigh alongside these figures.

*Generated by `src/build_memo.py` from the pipeline output. Regenerating after a data refresh will update every figure in this memo.*
