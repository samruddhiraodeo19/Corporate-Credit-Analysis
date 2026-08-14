# Credit Memo — TJX COMPANIES INC /DE/ (TJX)

**Recommendation: APPROVE WITH CONDITIONS**

| | |
|---|---|
| Internal grade | **A** (PD proxy band: Low) |
| Watchlist status | Medium (1 trigger) |
| Financials as of | 2026-05-02 (latest filed quarter) |
| Scorecard | 0.15 on a 0 = best / 2 = worst scale, 100% data coverage |
| Prepared from | SEC EDGAR XBRL filings via this repository's pipeline |

Inside every credit-policy test today, with identified deterioration or scenario sensitivity that warrants conditions.

---

## 1. Company overview

The largest off-price apparel and home-fashion retailer, buying opportunistically and selling below department-store prices. Off-price tends to gain share when consumers trade down, which makes the model counter-cyclical relative to the rest of the sector.

On the latest filed quarter the business generated $61.6bn of trailing-twelve-month revenue and $8.8bn of EBITDA, against $2.9bn of total debt and $5.6bn of cash and short-term investments.

## 2. Key credit metrics

| Metric | Actual | Assumed threshold | Test |
|---|---:|---:|:---:|
| Revenue (TTM) | $61.6bn | — | — |
| EBITDA (TTM) | $8.8bn | — | — |
| Operating margin | 12.3% | — | — |
| Total debt | $2.9bn | — | — |
| Net debt | $-2.7bn | — | — |
| Debt / EBITDA | 0.32x | ≤ 4.50x | Pass |
| Net debt / EBITDA | -0.31x | — | — |
| EBITDA / interest | n/a | ≥ 2.00x | n/a |
| Free cash flow (TTM) | $5.5bn | — | — |
| FCF / debt | 190.8% | ≥ 5% | Pass |
| Current ratio | 1.14x | ≥ 1.00x | Pass |
| Quick ratio | 0.54x | — | — |
| Working capital | $1.8bn | — | — |
| Altman Z" (non-manufacturer) | 3.02 | ≥ 1.1 | Pass |
| Covenant headroom | 4.18 turns | — | — |

Thresholds are the assumed credit policy defined in `src/config.py`; they are illustrative of public retail credit agreements, not real negotiated covenants.

## 3. Trend commentary

TTM EBITDA of $8.8bn rose 19.2% year on year; operating margin rose to 12.3% (+124bps YoY); leverage down 0.06 turns to 0.32x.

Working capital rose 1.0% to $1.8bn.

Leverage is falling on improving earnings, which is the constructive combination. The direction of travel is favourable, but one early-warning test still fired: 35% of debt matures within 12 months - refinancing concentration.

## 4. Stress test results

| Scenario | EBITDA | Debt/EBITDA | EBITDA/interest | FCF/debt | Covenant |
|---|---:|---:|---:|---:|:---:|
| Baseline (as reported) | $8.8bn | 0.32x | n/a | 190.8% | Pass |
| Revenue -10% | $8.0bn | 0.36x | n/a | 172.4% | Pass |
| Revenue -20% | $7.1bn | 0.41x | n/a | 153.9% | Pass |
| EBITDA margin -300bps | $7.0bn | 0.41x | n/a | 152.2% | Pass |
| Rates +200bps | $8.8bn | 0.32x | 307.84x | 190.1% | Pass |
| Inventory +30% (cash funded) | $8.8bn | 0.32x | n/a | 110.6% | Pass |
| Combined recession | $5.9bn | 0.48x | 206.95x | 49.3% | Pass |

The name survives the combined recession scenario. EBITDA falls 33% to $5.9bn, taking leverage to 0.48x — still 4.02 turns inside the assumed 4.5x covenant. On the reported balance sheet, EBITDA would have to fall 93% from its current level before the covenant is breached at all. Of the individual shocks, *EBITDA margin -300bps* does the most damage, taking leverage to 0.41x.

Scenario assumptions: 50% of debt floating-rate, 80% of any EBITDA decline passing through to free cash flow, and a cash-funded 30% inventory build.

---

## 5. Recommendation rationale

The recommendation rests on 1 trigger across 1 category:

- **Deteriorating** — 35% of debt matures within 12 months - refinancing concentration (trigger 25%).

**Conditions**

1. Quarterly reporting of the metrics below within 45 days of each 10-Q, with a written explanation of any further deterioration in the trend items identified above.
2. Refinancing plan for the near-term maturity to be presented at least 180 days ahead of the due date.

**What would change this view**

- *To Approve:* two consecutive quarters with no trigger firing and leverage sustained below 2.70x.
- *To Watchlist or Reject:* any credit-policy test breached on a reported quarter, Altman Z" below 1.1, or failure to meet the conditions above within the agreed window.

## 6. Key risks

1. **Refinancing concentration.** 35% of debt ($1.0bn) matures within twelve months, so the credit is exposed to capital-market access at a specific date rather than to operating performance alone.
2. **Working-capital dependence.** A current ratio of 1.14x means the business runs on supplier financing; any tightening of vendor terms or credit insurance would pressure liquidity quickly, and the assumed 30% inventory build takes the quick ratio to 0.36x.
3. **Deterioration already visible.** 35% of debt matures within 12 months - refinancing concentration (trigger 25%).
4. **Model limitation.** Leverage here excludes capitalised operating leases and uses unadjusted EBITDA. A rating agency capitalising leases would report materially higher leverage for any store-based retailer, including this one.

---

## Basis of preparation

- All financial data is taken from TJX COMPANIES INC /DE/'s SEC filings via the XBRL API, as of the quarter ended 2026-05-02. Debt is sourced from *current + noncurrent legs*; EBIT from *derived: pretax less net interest*; interest on a *net of interest income* basis.
- Covenant thresholds, the floating-rate share, the inventory build and the cash-flow passthrough are **assumptions**, not terms of any real agreement.
- The internal grade and PD proxy come from a rules-based scorecard that was not fitted to historical default data. They rank relative risk; they are not probabilities of default.
- Leverage excludes capitalised operating leases, and EBITDA is unadjusted (no addbacks for impairment, restructuring or stock compensation).
- The scorecard is quantitative only. It carries no view on management, competitive position or brand trajectory, all of which a credit committee would weigh alongside these figures.

*Generated by `src/build_memo.py` from the pipeline output. Regenerating after a data refresh will update every figure in this memo.*
