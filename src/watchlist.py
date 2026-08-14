"""
Builds the final watchlist from baseline metrics, trend deterioration and
stress results.

Usage:
    python src/watchlist.py

Requires output/metrics_summary.csv and output/stress_test_results.csv.
Produces output/watchlist.csv

Three independent families of trigger, because they catch different things:

  LEVEL      - the company is already outside credit policy today.
  TREND      - the company is still inside policy but moving the wrong way
               fast. This is the "early warning" half of the system: a name
               whose leverage rose a full turn and whose margin fell 200bps
               year on year is the one to call before it breaches, not after.
  STRESS     - the company is inside policy today and would fall outside it
               under a defined scenario.

Every trigger is a named constant in config.py with a stated rationale, and
every firing records the actual value against the threshold, so a reviewer
asking "why is this name on the list?" gets a number rather than a verdict.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from config import (
    ALTMAN_ZPP_DISTRESS,
    DEBT_EBITDA_COVENANT,
    EW_COVERAGE_DROP_PCT,
    EW_EBITDA_DECLINE_PCT,
    EW_LEVERAGE_RISE_TURNS,
    EW_MARGIN_DROP_BPS,
    EW_WORKING_CAPITAL_DROP_PCT,
    GRADE_ORDER,
    INVESTMENT_GRADE_FLOOR,
    MIN_CURRENT_RATIO,
    MIN_FCF_TO_DEBT,
    MIN_INTEREST_COVERAGE,
    REFI_CONCENTRATION_PCT,
)

OUTPUT_DIR = Path(__file__).parent.parent / "output"

# Severity drives the review queue: a breach today outranks a projected one.
# "Clear" rather than "None": the label round-trips through CSV, where
# pandas reads the literal string "None" back as a null value.
SEVERITY_RANK = {"High": 0, "Medium": 1, "Low": 2, "Clear": 3}


def _ok(value) -> bool:
    return value is not None and not pd.isna(value)


def level_triggers(row: pd.Series) -> list[tuple[str, str, str]]:
    """Tests against current credit policy. (severity, category, reason)"""
    fired = []
    leverage = row.get("debt_to_ebitda")
    if _ok(leverage) and leverage > DEBT_EBITDA_COVENANT:
        fired.append(("High", "Level", f"Debt/EBITDA {leverage:.2f}x above assumed "
                                       f"{DEBT_EBITDA_COVENANT}x covenant"))
    # Negative EBITDA leaves leverage undefined; that is worse than a high
    # multiple, not better, and must not slip through as "no data".
    if pd.isna(leverage) and _ok(row.get("ebitda_ttm")) and row["ebitda_ttm"] <= 0:
        fired.append(("High", "Level", f"TTM EBITDA negative "
                                       f"(${row['ebitda_ttm'] / 1e6:,.0f}m) - leverage not meaningful"))

    coverage = row.get("interest_coverage")
    if _ok(coverage) and coverage < MIN_INTEREST_COVERAGE:
        fired.append(("High", "Level", f"Interest coverage {coverage:.2f}x below "
                                       f"{MIN_INTEREST_COVERAGE}x floor"))

    current = row.get("current_ratio")
    if _ok(current) and current < MIN_CURRENT_RATIO:
        fired.append(("Medium", "Level", f"Current ratio {current:.2f}x below "
                                         f"{MIN_CURRENT_RATIO}x"))

    zscore = row.get("altman_z_double_prime")
    if _ok(zscore) and zscore < ALTMAN_ZPP_DISTRESS:
        fired.append(("High", "Level", f"Altman Z\" {zscore:.2f} in distress zone "
                                       f"(below {ALTMAN_ZPP_DISTRESS})"))

    fcf = row.get("fcf_to_debt")
    if _ok(fcf) and fcf < MIN_FCF_TO_DEBT and not row.get("no_debt"):
        fired.append(("Medium", "Level", f"FCF/Debt {fcf:.1%} below {MIN_FCF_TO_DEBT:.0%} - "
                                         f"limited capacity to deleverage from cash flow"))
    return fired


def trend_triggers(row: pd.Series) -> list[tuple[str, str, str]]:
    """Year-on-year deterioration tests -- the early-warning layer."""
    fired = []
    leverage_change = row.get("debt_to_ebitda_yoy_chg")
    if _ok(leverage_change) and leverage_change > EW_LEVERAGE_RISE_TURNS:
        fired.append(("Medium", "Trend", f"Leverage up {leverage_change:.2f} turns YoY "
                                         f"(trigger {EW_LEVERAGE_RISE_TURNS})"))

    margin_change = row.get("operating_margin_yoy_chg")
    if _ok(margin_change) and margin_change * 10_000 < -EW_MARGIN_DROP_BPS:
        fired.append(("Medium", "Trend", f"Operating margin down {abs(margin_change) * 10_000:.0f}bps "
                                         f"YoY (trigger {EW_MARGIN_DROP_BPS}bps)"))

    ebitda_change = row.get("ebitda_ttm_yoy_pct")
    if _ok(ebitda_change) and ebitda_change < -EW_EBITDA_DECLINE_PCT:
        fired.append(("Medium", "Trend", f"TTM EBITDA down {abs(ebitda_change):.1%} YoY "
                                         f"(trigger {EW_EBITDA_DECLINE_PCT:.0%})"))

    coverage_change = row.get("interest_coverage_yoy_pct")
    if _ok(coverage_change) and coverage_change < -EW_COVERAGE_DROP_PCT:
        fired.append(("Low", "Trend", f"Interest coverage down {abs(coverage_change):.1%} YoY "
                                      f"(trigger {EW_COVERAGE_DROP_PCT:.0%})"))

    wc_change = row.get("working_capital_yoy_pct")
    if _ok(wc_change) and wc_change < -EW_WORKING_CAPITAL_DROP_PCT:
        fired.append(("Low", "Trend", f"Working capital down {abs(wc_change):.1%} YoY "
                                      f"(trigger {EW_WORKING_CAPITAL_DROP_PCT:.0%})"))

    burn = row.get("consecutive_fcf_negative_qtrs")
    if _ok(burn) and burn >= 2:
        fired.append(("Medium", "Trend", f"{int(burn)} consecutive quarters of negative free cash flow"))

    due = row.get("pct_debt_due_within_1y")
    if _ok(due) and due > REFI_CONCENTRATION_PCT:
        fired.append(("Medium", "Trend", f"{due:.0%} of debt matures within 12 months - "
                                         f"refinancing concentration (trigger {REFI_CONCENTRATION_PCT:.0%})"))
    return fired


def stress_triggers(row: pd.Series, stress: pd.DataFrame) -> list[tuple[str, str, str]]:
    """Scenarios that push a currently-compliant company outside policy."""
    fired = []
    baseline_leverage = row.get("debt_to_ebitda")
    already_breaching = _ok(baseline_leverage) and baseline_leverage > DEBT_EBITDA_COVENANT

    company_stress = stress[stress["ticker"] == row["ticker"]]
    for _, scenario in company_stress.iterrows():
        if scenario["scenario"] == "baseline":
            continue
        label = scenario["scenario_label"]
        if scenario.get("breaches_leverage_covenant") and not already_breaching:
            fired.append(("Medium", "Stress",
                          f"Breaches {DEBT_EBITDA_COVENANT}x covenant under {label} "
                          f"(stressed {scenario['stressed_debt_to_ebitda']:.2f}x)"))
        if scenario.get("breaches_coverage_floor") and not (
                _ok(row.get("interest_coverage")) and row["interest_coverage"] < MIN_INTEREST_COVERAGE):
            fired.append(("Medium", "Stress",
                          f"Coverage falls to {scenario['stressed_interest_coverage']:.2f}x "
                          f"under {label}"))
    return fired


def build_watchlist(summary: pd.DataFrame, stress: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (one row per company, one row per individual trigger).

    The tidy trigger table is what the dashboard and the credit memo consume:
    re-splitting a pipe-joined string downstream is fragile and loses the
    severity and category of each individual firing.
    """
    records, trigger_rows = [], []
    for _, row in summary.iterrows():
        triggers = level_triggers(row) + trend_triggers(row) + stress_triggers(row, stress)
        for severity_label, category, reason in triggers:
            trigger_rows.append({
                "ticker": row["ticker"],
                "company_name": row.get("company_name"),
                "category": category,
                "severity": severity_label,
                "reason": reason,
            })
        severities = [SEVERITY_RANK[s] for s, _, _ in triggers]
        worst = min(severities) if severities else SEVERITY_RANK["Clear"]
        severity = next(k for k, v in SEVERITY_RANK.items() if v == worst)

        by_category = {c: [r for s, cat, r in triggers if cat == c] for c in ("Level", "Trend", "Stress")}
        grade = row.get("credit_grade")
        records.append({
            "ticker": row["ticker"],
            "company_name": row.get("company_name"),
            "period_end_date": row.get("period_end_date"),
            "credit_grade": grade,
            "pd_proxy_band": row.get("pd_proxy_band"),
            "watchlist_severity": severity if triggers else "Clear",
            "on_watchlist": bool(triggers),
            "trigger_count": len(triggers),
            "sub_investment_grade": grade in GRADE_ORDER
                                    and GRADE_ORDER.index(grade) > GRADE_ORDER.index(INVESTMENT_GRADE_FLOOR),
            "debt_to_ebitda": row.get("debt_to_ebitda"),
            "interest_coverage": row.get("interest_coverage"),
            "fcf_to_debt": row.get("fcf_to_debt"),
            "current_ratio": row.get("current_ratio"),
            "altman_z_double_prime": row.get("altman_z_double_prime"),
            "covenant_headroom_turns": row.get("covenant_headroom_turns"),
            "level_triggers": " | ".join(by_category["Level"]),
            "trend_triggers": " | ".join(by_category["Trend"]),
            "stress_triggers": " | ".join(by_category["Stress"]),
            "all_triggers": " | ".join(r for _, _, r in triggers),
        })

    watchlist = pd.DataFrame(records)
    watchlist["_rank"] = watchlist["watchlist_severity"].map(SEVERITY_RANK)
    watchlist = watchlist.sort_values(
        ["_rank", "trigger_count"], ascending=[True, False]).drop(columns="_rank")

    triggers_tidy = pd.DataFrame(trigger_rows, columns=[
        "ticker", "company_name", "category", "severity", "reason"])
    if not triggers_tidy.empty:
        triggers_tidy["_rank"] = triggers_tidy["severity"].map(SEVERITY_RANK)
        triggers_tidy = triggers_tidy.sort_values(
            ["_rank", "ticker", "category"]).drop(columns="_rank")
    return watchlist, triggers_tidy


def main() -> int:
    summary_path = OUTPUT_DIR / "metrics_summary.csv"
    stress_path = OUTPUT_DIR / "stress_test_results.csv"
    all_periods_path = OUTPUT_DIR / "metrics_all_periods.csv"
    if not summary_path.exists() or not stress_path.exists():
        print("Missing inputs. Run calc_metrics.py then stress_test.py first.")
        return 1

    summary = pd.read_csv(summary_path)
    stress = pd.read_csv(stress_path)

    # no_debt / burn counters live in the full panel, not the reporting view.
    full = pd.read_csv(all_periods_path)
    full["period_end_date"] = pd.to_datetime(full["period_end_date"])
    summary["period_end_date"] = pd.to_datetime(summary["period_end_date"])
    extra = [c for c in ["ticker", "period_end_date", "no_debt", "ebitda_ttm"] if c in full.columns]
    summary = summary.merge(full[extra], on=["ticker", "period_end_date"], how="left",
                            suffixes=("", "_full"))

    watchlist, triggers = build_watchlist(summary, stress)
    watchlist.to_csv(OUTPUT_DIR / "watchlist.csv", index=False)
    triggers.to_csv(OUTPUT_DIR / "watchlist_triggers.csv", index=False)

    flagged = watchlist[watchlist["on_watchlist"]]
    print(f"WATCHLIST - {len(flagged)} of {len(watchlist)} names flagged\n")
    for _, row in flagged.iterrows():
        print(f"{row['ticker']:5s} {row['watchlist_severity']:6s} grade {row['credit_grade']:3s}  "
              f"{row['company_name']}")
        for category in ("level_triggers", "trend_triggers", "stress_triggers"):
            if row[category]:
                tag = category.split("_")[0].upper()
                for reason in row[category].split(" | "):
                    print(f"        [{tag:6s}] {reason}")
        print()

    clean = watchlist[~watchlist["on_watchlist"]]
    if not clean.empty:
        print(f"No triggers: {', '.join(clean['ticker'])}")

    print(f"\nSaved watchlist.csv ({len(watchlist)} names) and "
          f"watchlist_triggers.csv ({len(triggers)} triggers) -> {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
