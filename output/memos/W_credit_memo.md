# Credit Memo — Wayfair Inc. (W)

**Recommendation: REJECT**

| | |
|---|---|
| Internal grade | **B** (PD proxy band: High) |
| Watchlist status | High (6 triggers) |
| Financials as of | 2026-06-30 (latest filed quarter) |
| Scorecard | 1.35 on a 0 = best / 2 = worst scale, 100% data coverage |
| Prepared from | SEC EDGAR XBRL filings via this repository's pipeline |

Multiple credit-policy tests are breached today, not under a hypothetical scenario.

---

## 1. Company overview

An online retailer of furniture and home goods, operating an asset-light drop-ship model. Long loss-making and only recently approaching profitability; the capital structure includes convertible notes and book equity is deeply negative.

On the latest filed quarter the business generated $12.9bn of trailing-twelve-month revenue and $492.0m of EBITDA, against $2.8bn of total debt and $1.1bn of cash and short-term investments.

## 2. Key credit metrics

| Metric | Actual | Assumed threshold | Test |
|---|---:|---:|:---:|
| Revenue (TTM) | $12.9bn | — | — |
| EBITDA (TTM) | $492.0m | — | — |
| Operating margin | 1.7% | — | — |
| Total debt | $2.8bn | — | — |
| Net debt | $1.7bn | — | — |
| Debt / EBITDA | 5.68x | ≤ 4.50x | **Fail** |
| Net debt / EBITDA | 3.36x | — | — |
| EBITDA / interest | 3.39x | ≥ 2.00x | Pass |
| Free cash flow (TTM) | $562.0m | — | — |
| FCF / debt | 20.1% | ≥ 5% | Pass |
| Current ratio | 0.74x | ≥ 1.00x | **Fail** |
| Quick ratio | 0.71x | — | — |
| Working capital | $-583.0m | — | — |
| Altman Z" (non-manufacturer) | -6.70 | ≥ 1.1 | **Fail** |
| Covenant headroom | -1.18 turns | — | — |

Thresholds are the assumed credit policy defined in `src/config.py`; they are illustrative of public retail credit agreements, not real negotiated covenants.

## 3. Trend commentary

TTM EBITDA of $492.0m, against $47.0m a year earlier; operating margin rose to 1.7% (+413bps YoY); leverage of 5.68x, against 61.36x a year earlier.

Interest coverage of 3.39x, materially rebuilt from a year earlier; working capital fell 44.0% to $-583.0m.

Leverage is falling on improving earnings, which is the constructive combination. The direction of travel is favourable, but one early-warning test still fired: working capital down 44.0% YoY.

## 4. Stress test results

| Scenario | EBITDA | Debt/EBITDA | EBITDA/interest | FCF/debt | Covenant |
|---|---:|---:|---:|---:|:---:|
| Baseline (as reported) | $492.0m | 5.68x | 3.39x | 20.1% | **Breach** |
| Revenue -10% | $442.8m | 6.32x | 3.05x | 19.0% | **Breach** |
| Revenue -20% | $393.6m | 7.11x | 2.71x | 18.0% | **Breach** |
| EBITDA margin -300bps | $104.9m | 26.67x | 0.72x | 11.8% | **Breach** |
| Rates +200bps | $492.0m | 5.68x | 2.84x | 19.3% | **Breach** |
| Inventory +30% (cash funded) | $492.0m | 5.68x | 3.39x | 19.2% | **Breach** |
| Combined recession | $89.1m | 31.37x | 0.52x | 9.8% | **Breach** |

The name is already through the assumed 4.5x covenant on its reported balance sheet at 5.68x, so the scenarios measure how much worse the position gets rather than whether it holds. Under the combined recession, EBITDA falls 82% to $89.1m and leverage reaches 31.37x. There is no covenant cushion to erode. Of the individual shocks, *EBITDA margin -300bps* does the most damage, taking leverage to 26.67x.

Scenario assumptions: 50% of debt floating-rate, 80% of any EBITDA decline passing through to free cash flow, and a cash-funded 30% inventory build.

---

## 5. Recommendation rationale

The recommendation rests on 6 triggers across 3 categories:

- **Breached today** — Debt/EBITDA 5.68x above assumed 4.5x covenant.
- **Breached today** — Altman Z" -6.70 in distress zone (below 1.1).
- **Breached today** — Current ratio 0.74x below 1.0x.
- **Deteriorating** — Working capital down 44.0% YoY (trigger 20%).
- **Breaches under scenario** — Coverage falls to 0.72x under EBITDA margin -300bps.
- **Breaches under scenario** — Coverage falls to 0.52x under Combined recession.

**Requirements to reconsider**

1. No new exposure pending evidence that the breached tests above have been restored on a reported quarter.
2. Quarterly reporting of the metrics below within 45 days of each 10-Q, with a written explanation of any further deterioration in the trend items identified above.
3. Margin recovery milestone: operating margin to stabilise within two quarters, or the facility is re-priced and the leverage test steps down.
4. Leverage covenant set with reference to the combined-recession outcome (31.37x), which leaves only -26.87 turns of headroom.

**What would change this view**

- *To Approve with Conditions:* leverage returned below 4.5x and Altman Z" above 1.1 on two consecutive reported quarters, with a current ratio at or above 1.0x.
- *Sustained rejection:* further deterioration in any breached test, or a deferral of the maturity profile onto shorter-dated funding.

## 6. Key risks

1. **Margin convexity.** At a 1.7% operating margin, a small absolute change in margin is a large proportional change in EBITDA, so leverage is far more sensitive to pricing and freight than the headline multiple suggests. A 300bps margin loss alone takes leverage to 26.67x.
2. **Negative book equity ($-2.8bn).** There is no equity cushion beneath the debt, recovery in a stress would depend entirely on going-concern value, and the Altman Z" of -6.70 reflects this directly.
3. **Interest-rate sensitivity.** Coverage of 3.39x leaves limited absorption for higher funding costs. A 200bps rate rise on the assumed 50% floating-rate share takes coverage to 2.84x.
4. **Working-capital dependence.** A current ratio of 0.74x means the business runs on supplier financing; any tightening of vendor terms or credit insurance would pressure liquidity quickly, and the assumed 30% inventory build takes the quick ratio to 0.69x.
5. **Deterioration already visible.** Working capital down 44.0% YoY (trigger 20%).

---

## Basis of preparation

- All financial data is taken from Wayfair Inc.'s SEC filings via the XBRL API, as of the quarter ended 2026-06-30. Debt is sourced from *current + noncurrent legs*; EBIT from *reported*; interest on a *net of interest income* basis.
- Covenant thresholds, the floating-rate share, the inventory build and the cash-flow passthrough are **assumptions**, not terms of any real agreement.
- The internal grade and PD proxy come from a rules-based scorecard that was not fitted to historical default data. They rank relative risk; they are not probabilities of default.
- Leverage excludes capitalised operating leases, and EBITDA is unadjusted (no addbacks for impairment, restructuring or stock compensation).
- The scorecard is quantitative only. It carries no view on management, competitive position or brand trajectory, all of which a credit committee would weigh alongside these figures.

*Generated by `src/build_memo.py` from the pipeline output. Regenerating after a data refresh will update every figure in this memo.*
