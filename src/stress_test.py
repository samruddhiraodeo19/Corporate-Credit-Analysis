"""
Applies the stress scenarios to each company's latest credit metrics.

Usage:
    python src/stress_test.py

Requires output/metrics_summary.csv. Produces:
    output/stress_test_results.csv   every company x scenario, full detail
    output/stress_matrix.csv         company x scenario leverage matrix

All seven scenarios (baseline plus six stresses) run through one function so
the calculation can't drift between them.

What each shock is assumed to do:
  * Revenue shock  - volume/traffic decline at constant EBITDA margin.
  * Margin shock   - margin compression in percentage points of EBITDA
                     margin, applied to unstressed revenue.
  * Rate shock     - repricing of the assumed floating-rate share of debt.
                     Fixed-rate debt is unaffected.
  * Inventory      - a merchandise build funded out of cash: inventory up,
                     cash down, total current assets unchanged. That hits
                     the quick ratio and net debt but not the current ratio,
                     which is the correct signature of a stock build.

Cash flow is stressed too, rather than held at its baseline value. A fall in
EBITDA does not pass through to free cash flow one-for-one: a sales decline
releases working capital (inventory and payables unwind), which cushions cash
flow in the first year, so only EBITDA_TO_FCF_PASSTHROUGH of the decline is
assumed to reach FCF, after tax at CASH_TAX_RATE.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from config import (
    CASH_TAX_RATE,
    DEBT_EBITDA_COVENANT,
    EBITDA_TO_FCF_PASSTHROUGH,
    FLOATING_RATE_DEBT_PCT,
    INVENTORY_BUILD_IS_CASH_FUNDED,
    INVENTORY_STRESS_PCT,
    MIN_CURRENT_RATIO,
    MIN_INTEREST_COVERAGE,
)

OUTPUT_DIR = Path(__file__).parent.parent / "output"

# Scenario definitions. Keeping these as data (not code) means adding a
# scenario is a one-line change and every scenario shares one calculation.
SCENARIOS = {
    "baseline": {},
    "revenue_down_10": {"revenue_shock": -0.10},
    "revenue_down_20": {"revenue_shock": -0.20},
    "ebitda_margin_down_300bps": {"margin_shock_pts": -3.0},
    "rates_up_200bps": {"rate_shock_pts": 2.0},
    "inventory_build_30pct": {"inventory_shock": INVENTORY_STRESS_PCT},
    "combined_recession": {"revenue_shock": -0.15, "margin_shock_pts": -3.0,
                           "rate_shock_pts": 2.0, "inventory_shock": INVENTORY_STRESS_PCT},
}

SCENARIO_LABELS = {
    "baseline": "Baseline (as reported)",
    "revenue_down_10": "Revenue -10%",
    "revenue_down_20": "Revenue -20%",
    "ebitda_margin_down_300bps": "EBITDA margin -300bps",
    "rates_up_200bps": "Rates +200bps",
    "inventory_build_30pct": f"Inventory +{INVENTORY_STRESS_PCT:.0%} (cash funded)",
    "combined_recession": "Combined recession",
}


def _nan(value) -> float:
    """Coerce a possibly-missing CSV field to float, mapping blanks to NaN."""
    try:
        out = float(value)
    except (TypeError, ValueError):
        return np.nan
    return out


def _div(numerator: float, denominator: float, require_positive: bool = False) -> float:
    """Ratio guarded against a zero, missing or (optionally) negative base.
    Leverage against negative EBITDA is suppressed rather than reported as a
    flattering negative multiple."""
    if np.isnan(numerator) or np.isnan(denominator) or denominator == 0:
        return np.nan
    if require_positive and denominator < 0:
        return np.nan
    return numerator / denominator


def apply_scenario(row: pd.Series, params: dict) -> dict:
    """Recompute the credit metrics for one company under one scenario."""
    revenue = _nan(row.get("revenue_ttm"))
    ebitda = _nan(row.get("ebitda_ttm"))
    total_debt = _nan(row.get("total_debt"))
    cash = _nan(row.get("liquid_assets"))
    interest = _nan(row.get("interest_expense_eff_ttm"))
    fcf = _nan(row.get("fcf_ttm"))
    current_assets = _nan(row.get("current_assets"))
    current_liabilities = _nan(row.get("current_liabilities"))
    inventory = _nan(row.get("inventory"))

    # --- Earnings ---------------------------------------------------------
    revenue_shock = params.get("revenue_shock", 0.0)
    margin_shock = params.get("margin_shock_pts", 0.0) / 100.0
    stressed_revenue = revenue * (1 + revenue_shock)

    base_margin = _div(ebitda, revenue)
    if np.isnan(base_margin):
        # No revenue base to work from: scale EBITDA by the revenue shock and
        # let the margin shock drop out rather than inventing a margin.
        stressed_ebitda = ebitda * (1 + revenue_shock)
    else:
        stressed_ebitda = stressed_revenue * (base_margin + margin_shock)

    # --- Interest ---------------------------------------------------------
    rate_shock = params.get("rate_shock_pts", 0.0) / 100.0
    added_interest = total_debt * FLOATING_RATE_DEBT_PCT * rate_shock if not np.isnan(total_debt) else 0.0
    stressed_interest = (0.0 if np.isnan(interest) else interest) + added_interest
    if np.isnan(interest) and added_interest == 0:
        stressed_interest = np.nan

    # --- Liquidity --------------------------------------------------------
    inventory_shock = params.get("inventory_shock", 0.0)
    inventory_build = inventory * inventory_shock if not np.isnan(inventory) else 0.0
    stressed_inventory = inventory + inventory_build
    stressed_cash = cash - inventory_build if INVENTORY_BUILD_IS_CASH_FUNDED else cash
    # A cash-funded build swaps one current asset for another, so current
    # assets are unchanged; a debt-funded build would raise them.
    stressed_current_assets = current_assets if INVENTORY_BUILD_IS_CASH_FUNDED \
        else current_assets + inventory_build

    # --- Cash flow --------------------------------------------------------
    ebitda_delta = stressed_ebitda - ebitda
    interest_delta = stressed_interest - (0.0 if np.isnan(interest) else interest)
    if np.isnan(interest_delta):
        interest_delta = 0.0
    stressed_fcf = fcf + (ebitda_delta * EBITDA_TO_FCF_PASSTHROUGH - interest_delta) * (1 - CASH_TAX_RATE)
    # The inventory build itself is a one-off cash outflow in the stress year.
    stressed_fcf -= inventory_build

    stressed_net_debt = total_debt - (0.0 if np.isnan(stressed_cash) else stressed_cash)

    debt_to_ebitda = _div(total_debt, stressed_ebitda, require_positive=True)
    coverage = _div(stressed_ebitda, stressed_interest, require_positive=True)

    return {
        "stressed_revenue": stressed_revenue,
        "stressed_ebitda": stressed_ebitda,
        "stressed_ebitda_margin": _div(stressed_ebitda, stressed_revenue),
        "stressed_interest_expense": stressed_interest,
        "stressed_debt_to_ebitda": debt_to_ebitda,
        "stressed_net_debt_to_ebitda": _div(stressed_net_debt, stressed_ebitda, require_positive=True),
        "stressed_interest_coverage": coverage,
        "stressed_fcf": stressed_fcf,
        "stressed_fcf_to_debt": _div(stressed_fcf, total_debt, require_positive=True),
        "stressed_current_ratio": _div(stressed_current_assets, current_liabilities, require_positive=True),
        "stressed_quick_ratio": _div(stressed_current_assets - (0.0 if np.isnan(stressed_inventory) else stressed_inventory),
                                     current_liabilities, require_positive=True),
        "covenant_headroom_turns": DEBT_EBITDA_COVENANT - debt_to_ebitda if not np.isnan(debt_to_ebitda) else np.nan,
        "ebitda_decline_pct": _div(ebitda_delta, ebitda) if not np.isnan(ebitda) else np.nan,
        # A company with no debt cannot breach a leverage covenant; NaN
        # leverage (no data) is not treated as a pass.
        "breaches_leverage_covenant": bool(debt_to_ebitda > DEBT_EBITDA_COVENANT)
        if not np.isnan(debt_to_ebitda) else False,
        "breaches_coverage_floor": bool(coverage < MIN_INTEREST_COVERAGE)
        if not np.isnan(coverage) else False,
        "breaches_current_ratio_floor": bool(
            _div(stressed_current_assets, current_liabilities) < MIN_CURRENT_RATIO)
        if not np.isnan(_div(stressed_current_assets, current_liabilities)) else False,
    }


def main() -> int:
    summary_path = OUTPUT_DIR / "metrics_summary.csv"
    all_periods_path = OUTPUT_DIR / "metrics_all_periods.csv"
    if not summary_path.exists() or not all_periods_path.exists():
        print(f"{summary_path} not found. Run calc_metrics.py first.")
        return 1

    summary = pd.read_csv(summary_path)
    # The summary is the reporting view; the stress model also needs raw
    # balance-sheet inputs (inventory, current assets) that don't belong in it.
    full = pd.read_csv(all_periods_path)
    full["period_end_date"] = pd.to_datetime(full["period_end_date"])
    summary["period_end_date"] = pd.to_datetime(summary["period_end_date"])
    inputs = ["ticker", "period_end_date", "inventory", "current_assets",
              "current_liabilities", "interest_expense_eff_ttm"]
    latest = summary.merge(full[[c for c in inputs if c in full.columns]],
                           on=["ticker", "period_end_date"], how="left")

    rows = []
    for _, company in latest.iterrows():
        for name, params in SCENARIOS.items():
            result = apply_scenario(company, params)
            rows.append({
                "ticker": company["ticker"],
                "company_name": company.get("company_name"),
                "period_end_date": company["period_end_date"].date(),
                "scenario": name,
                "scenario_label": SCENARIO_LABELS[name],
                "credit_grade": company.get("credit_grade"),
                **result,
            })

    results = pd.DataFrame(rows)
    results["scenario"] = pd.Categorical(results["scenario"], categories=SCENARIOS, ordered=True)
    results = results.sort_values(["ticker", "scenario"])
    results.to_csv(OUTPUT_DIR / "stress_test_results.csv", index=False)

    matrix = results.pivot(index="ticker", columns="scenario",
                           values="stressed_debt_to_ebitda")
    matrix.to_csv(OUTPUT_DIR / "stress_matrix.csv")
    coverage_matrix = results.pivot(index="ticker", columns="scenario",
                                    values="stressed_interest_coverage")
    coverage_matrix.to_csv(OUTPUT_DIR / "stress_matrix_coverage.csv")

    print(f"Stressed Debt/EBITDA by scenario (assumed covenant {DEBT_EBITDA_COVENANT}x)\n")
    print(matrix.sort_values("combined_recession", ascending=False)
          .to_string(float_format=lambda v: f"{v:,.2f}", na_rep="  n/a"))
    # The rate and inventory shocks leave EBITDA untouched, so they cannot
    # move a leverage multiple -- they show up in coverage and liquidity.
    print(f"\nStressed EBITDA/interest coverage (floor {MIN_INTEREST_COVERAGE}x)\n")
    print(coverage_matrix.sort_values("combined_recession")
          .to_string(float_format=lambda v: f"{v:,.1f}", na_rep="  n/m"))

    baseline_breach = set(results.loc[
        (results["scenario"] == "baseline") & results["breaches_leverage_covenant"], "ticker"])
    stressed = results[(results["scenario"] != "baseline") & results["breaches_leverage_covenant"]]
    newly = stressed[~stressed["ticker"].isin(baseline_breach)]

    print("\nAssumed leverage covenant:")
    if baseline_breach:
        print(f"  Already in breach at baseline: {', '.join(sorted(baseline_breach))}")
    if not newly.empty:
        print("  Breaches only under stress (the names a covenant test would catch):")
        for ticker, group in newly.groupby("ticker", observed=True):
            print(f"    {ticker:5s} {', '.join(group['scenario_label'])}")
    else:
        print("  No additional company is pushed into breach by any single scenario.")

    survivors = results[(results["scenario"] == "combined_recession")]
    worst = survivors.nsmallest(3, "covenant_headroom_turns")[
        ["ticker", "stressed_debt_to_ebitda", "covenant_headroom_turns", "ebitda_decline_pct"]]
    print("\nThinnest headroom under the combined recession scenario:")
    print(worst.to_string(index=False, float_format=lambda v: f"{v:,.2f}", na_rep="n/a"))

    print(f"\nSaved stress_test_results.csv and stress_matrix.csv -> {OUTPUT_DIR}")
    print("Next: python src/watchlist.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
