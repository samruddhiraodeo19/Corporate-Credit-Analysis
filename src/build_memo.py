"""
Generates the two-page credit memo (PLAN Phase 8).

Usage:
    python src/build_memo.py                # the most interesting name
    python src/build_memo.py --ticker KSS   # a specific name
    python src/build_memo.py --all          # every name on the watchlist

Produces output/memos/<TICKER>_credit_memo.md

The memo is generated from the pipeline's own numbers rather than written by
hand, so it cannot drift out of line with the model behind it: every figure
quoted is read from metrics_summary.csv and stress_test_results.csv, and the
commentary is assembled from the actual direction and size of each move.

The one thing that is not derived is the business description, which comes
from COMPANY_PROFILES in config.py and is labelled as analyst-supplied. A
memo has to say what the company does; no ratio carries that.
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

from config import (
    ALTMAN_ZPP_DISTRESS,
    ALTMAN_ZPP_SAFE,
    COMPANY_PROFILES,
    DEBT_EBITDA_COVENANT,
    EBITDA_TO_FCF_PASSTHROUGH,
    FLOATING_RATE_DEBT_PCT,
    INVENTORY_STRESS_PCT,
    MIN_CURRENT_RATIO,
    MIN_FCF_TO_DEBT,
    MIN_INTEREST_COVERAGE,
)

OUTPUT_DIR = Path(__file__).parent.parent / "output"
MEMO_DIR = OUTPUT_DIR / "memos"


# ---------------------------------------------------------------------------
# Formatting helpers -- every one renders missing data as "n/a", never 0.
# ---------------------------------------------------------------------------
def money(value, unit: str = "m") -> str:
    if pd.isna(value):
        return "n/a"
    divisor = 1e9 if unit == "bn" else 1e6
    return f"${value / divisor:,.1f}{unit}"


def auto_money(value) -> str:
    if pd.isna(value):
        return "n/a"
    return money(value, "bn") if abs(value) >= 1e9 else money(value, "m")


def multiple(value) -> str:
    return "n/a" if pd.isna(value) else f"{value:.2f}x"


def percent(value, places: int = 1) -> str:
    return "n/a" if pd.isna(value) else f"{value:.{places}%}"


def points(value) -> str:
    return "n/a" if pd.isna(value) else f"{value:.2f}"


def bps(value) -> str:
    return "n/a" if pd.isna(value) else f"{value * 10_000:,.0f}bps"


def direction(value, rising: str = "rose", falling: str = "fell",
              flat: str = "was broadly unchanged", threshold: float = 0.0) -> str:
    if pd.isna(value):
        return "n/a"
    if abs(value) <= threshold:
        return flat
    return rising if value > 0 else falling


def sentence(text: str) -> str:
    """Capitalise the first letter only. `str.capitalize()` lowercases the
    rest, which turns 'TTM EBITDA ... YoY' into 'Ttm ebitda ... yoy'."""
    text = text.strip()
    return text[0].upper() + text[1:] if text else text


WORD_NUMBERS = {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five",
                6: "Six", 7: "Seven", 8: "Eight", 9: "Nine"}


def spell(count: int, capitalised: bool = True) -> str:
    """Spell small numbers, so a sentence never opens with a bare numeral."""
    word = WORD_NUMBERS.get(count, str(count))
    return word if capitalised else word.lower()


def uncapitalise(text: str) -> str:
    """Lower only the first letter, so an embedded 'YoY' or 'EBITDA' survives
    being folded into the middle of a sentence."""
    return text[0].lower() + text[1:] if text else text


def change_phrase(current, change_pct, prior, noun: str) -> str:
    """Describe a year-on-year move. A percentage change off a near-zero base
    is arithmetically true and useless -- Wayfair's EBITDA 'rose 947%' because
    it started at $47m -- so large moves are quoted from the prior level."""
    if pd.isna(change_pct) or pd.isna(prior):
        return f"{noun} of {auto_money(current)}"
    if abs(change_pct) > 1.0:
        return (f"{noun} of {auto_money(current)}, against "
                f"{auto_money(prior)} a year earlier")
    return (f"{noun} of {auto_money(current)} {direction(change_pct)} "
            f"{abs(change_pct):.1%} year on year")


# ---------------------------------------------------------------------------
# Recommendation
# ---------------------------------------------------------------------------
def decide_recommendation(row: pd.Series, triggers: pd.DataFrame) -> tuple[str, str]:
    """Map the evidence to one of the four standard credit decisions."""
    level_high = triggers[(triggers["category"] == "Level") & (triggers["severity"] == "High")]
    severity = row.get("watchlist_severity", "Clear")

    if len(level_high) >= 2:
        return ("REJECT", "Multiple credit-policy tests are breached today, not "
                          "under a hypothetical scenario.")
    if len(level_high) == 1:
        return ("WATCHLIST", "A credit-policy test is breached today; the position is "
                             "maintainable but requires active monitoring.")
    if severity in ("Medium", "Low"):
        return ("APPROVE WITH CONDITIONS",
                "Inside every credit-policy test today, with identified deterioration "
                "or scenario sensitivity that warrants conditions.")
    return ("APPROVE", "Inside every credit-policy test today, with no material "
                       "deterioration and adequate stress headroom.")


def build_conditions(row: pd.Series, triggers: pd.DataFrame, stress: pd.DataFrame) -> list[str]:
    """Conditions tied to what actually fired, not a generic checklist."""
    conditions = []
    categories = set(triggers["category"])
    reasons = " ".join(triggers["reason"])

    if "Trend" in categories:
        conditions.append(
            "Quarterly reporting of the metrics below within 45 days of each 10-Q, "
            "with a written explanation of any further deterioration in the trend "
            "items identified above.")
    if "margin" in reasons.lower():
        conditions.append(
            "Margin recovery milestone: operating margin to stabilise within two "
            "quarters, or the facility is re-priced and the leverage test steps down.")
    if "matures within 12 months" in reasons:
        conditions.append(
            "Refinancing plan for the near-term maturity to be presented at least "
            "180 days ahead of the due date.")

    combined = stress[stress["scenario"] == "combined_recession"]
    if not combined.empty:
        headroom = combined.iloc[0].get("covenant_headroom_turns")
        if pd.notna(headroom) and headroom < 1.0:
            conditions.append(
                f"Leverage covenant set with reference to the combined-recession "
                f"outcome ({multiple(combined.iloc[0]['stressed_debt_to_ebitda'])}), "
                f"which leaves only {points(headroom)} turns of headroom.")

    if pd.notna(row.get("fcf_to_debt")) and row["fcf_to_debt"] < 0.15:
        conditions.append(
            "Restriction on incremental shareholder returns while free cash flow to "
            "debt remains below 15%.")
    if not conditions:
        conditions.append("Standard quarterly financial reporting and covenant "
                          "certification.")
    if row.get("watchlist_severity") == "High":
        conditions.insert(0, "No new exposure pending evidence that the breached tests "
                             "above have been restored on a reported quarter.")
    return conditions


# ---------------------------------------------------------------------------
# Narrative sections
# ---------------------------------------------------------------------------
def metrics_table(row: pd.Series) -> str:
    thresholds = {
        "Debt / EBITDA": f"≤ {DEBT_EBITDA_COVENANT:.2f}x",
        "EBITDA / interest": f"≥ {MIN_INTEREST_COVERAGE:.2f}x",
        "FCF / debt": f"≥ {MIN_FCF_TO_DEBT:.0%}",
        "Current ratio": f"≥ {MIN_CURRENT_RATIO:.2f}x",
        'Altman Z"': f"≥ {ALTMAN_ZPP_DISTRESS}",
    }

    def verdict(name: str, value) -> str:
        if pd.isna(value):
            return "n/a"
        passes = {
            "Debt / EBITDA": value <= DEBT_EBITDA_COVENANT,
            "EBITDA / interest": value >= MIN_INTEREST_COVERAGE,
            "FCF / debt": value >= MIN_FCF_TO_DEBT,
            "Current ratio": value >= MIN_CURRENT_RATIO,
            'Altman Z"': value >= ALTMAN_ZPP_DISTRESS,
        }.get(name)
        return "Pass" if passes else "**Fail**"

    rows = [
        ("Revenue (TTM)", auto_money(row.get("revenue_ttm")), "—", "—"),
        ("EBITDA (TTM)", auto_money(row.get("ebitda_ttm")), "—", "—"),
        ("Operating margin", percent(row.get("operating_margin")), "—", "—"),
        ("Total debt", auto_money(row.get("total_debt")), "—", "—"),
        ("Net debt", auto_money(row.get("net_debt")), "—", "—"),
        ("Debt / EBITDA", multiple(row.get("debt_to_ebitda")),
         thresholds["Debt / EBITDA"], verdict("Debt / EBITDA", row.get("debt_to_ebitda"))),
        ("Net debt / EBITDA", multiple(row.get("net_debt_to_ebitda")), "—", "—"),
        ("EBITDA / interest", multiple(row.get("interest_coverage")),
         thresholds["EBITDA / interest"], verdict("EBITDA / interest", row.get("interest_coverage"))),
        ("Free cash flow (TTM)", auto_money(row.get("fcf_ttm")), "—", "—"),
        ("FCF / debt", percent(row.get("fcf_to_debt")),
         thresholds["FCF / debt"], verdict("FCF / debt", row.get("fcf_to_debt"))),
        ("Current ratio", multiple(row.get("current_ratio")),
         thresholds["Current ratio"], verdict("Current ratio", row.get("current_ratio"))),
        ("Quick ratio", multiple(row.get("quick_ratio")), "—", "—"),
        ("Working capital", auto_money(row.get("working_capital")), "—", "—"),
        ('Altman Z" (non-manufacturer)', points(row.get("altman_z_double_prime")),
         thresholds['Altman Z"'], verdict('Altman Z"', row.get("altman_z_double_prime"))),
        ("Covenant headroom", f"{points(row.get('covenant_headroom_turns'))} turns", "—", "—"),
    ]
    lines = ["| Metric | Actual | Assumed threshold | Test |",
             "|---|---:|---:|:---:|"]
    lines += [f"| {name} | {value} | {limit} | {result} |" for name, value, limit, result in rows]
    return "\n".join(lines)


def trend_commentary(row: pd.Series, triggers: pd.DataFrame) -> str:
    leverage_change = row.get("debt_to_ebitda_yoy_chg")
    margin_change = row.get("operating_margin_yoy_chg")
    ebitda_change = row.get("ebitda_ttm_yoy_pct")
    coverage_change = row.get("interest_coverage_yoy_pct")
    wc_change = row.get("working_capital_yoy_pct")

    leverage = row.get("debt_to_ebitda")
    prior_leverage = leverage - leverage_change if pd.notna(leverage_change) and pd.notna(leverage) else None
    ebitda = row.get("ebitda_ttm")
    prior_ebitda = ebitda / (1 + ebitda_change) if pd.notna(ebitda_change) and ebitda_change != -1 \
        and pd.notna(ebitda) else None

    parts = []
    if pd.notna(ebitda_change):
        parts.append(change_phrase(ebitda, ebitda_change, prior_ebitda, "TTM EBITDA"))
    if pd.notna(margin_change):
        parts.append(
            f"operating margin {direction(margin_change)} to "
            f"{percent(row.get('operating_margin'))} "
            f"({'+' if margin_change > 0 else '-'}{bps(abs(margin_change))} YoY)")
    if pd.notna(leverage_change) and prior_leverage is not None:
        # A move of tens of turns comes off a distressed base, where the
        # multiple was meaningless. Quote the level, not the change.
        if abs(leverage_change) > 5:
            parts.append(f"leverage of {multiple(leverage)}, against "
                         f"{multiple(prior_leverage)} a year earlier")
        else:
            parts.append(f"leverage {'up' if leverage_change > 0 else 'down'} "
                         f"{abs(leverage_change):.2f} turns to {multiple(leverage)}")

    opening = sentence("; ".join(parts)) + "." if parts else \
        "Year-on-year comparatives are not available for this name."

    detail = []
    if pd.notna(coverage_change):
        if abs(coverage_change) > 1.0:
            detail.append(f"interest coverage of {multiple(row.get('interest_coverage'))}, "
                          f"materially rebuilt from a year earlier")
        else:
            detail.append(f"interest coverage {direction(coverage_change)} "
                          f"{abs(coverage_change):.1%} to {multiple(row.get('interest_coverage'))}")
    if pd.notna(wc_change):
        detail.append(f"working capital {direction(wc_change)} {abs(wc_change):.1%} to "
                      f"{auto_money(row.get('working_capital'))}")

    burn = row.get("consecutive_fcf_negative_qtrs")
    if pd.notna(burn) and burn >= 1:
        detail.append(f"free cash flow has been negative for {int(burn)} "
                      f"consecutive quarter{'s' if burn > 1 else ''}")

    second = (sentence("; ".join(detail)) + ".") if detail else ""

    # The interpretation, reconciled against what actually fired -- claiming
    # "no trend triggers fired" while one is listed above would be a plain
    # contradiction in the memo.
    trend_fired = triggers[triggers["category"] == "Trend"]["reason"].tolist()
    favourable = False
    if pd.notna(leverage_change) and pd.notna(ebitda_change):
        if leverage_change > 0 and ebitda_change < 0:
            read = ("The leverage increase is earnings-driven rather than the result of "
                    "new borrowing, which means it reverses if margin recovers and "
                    "compounds if it does not.")
        elif leverage_change > 0 and ebitda_change >= 0:
            read = ("Leverage rose despite stable or growing EBITDA, pointing to "
                    "incremental borrowing rather than earnings deterioration.")
        elif leverage_change <= 0 and ebitda_change > 0:
            read = ("Leverage is falling on improving earnings, which is the "
                    "constructive combination.")
            favourable = True
        else:
            read = ("Leverage fell while EBITDA declined, which implies debt reduction "
                    "is doing the work rather than earnings growth.")
    else:
        read = ""

    # Only the leverage-down-on-rising-earnings branch is actually favourable.
    # Appending "the direction of travel is favourable" to a name whose EBITDA
    # and margin both fell would contradict the paragraph above it.
    if trend_fired:
        count = len(trend_fired)
        listed = "; ".join(uncapitalise(r.split(" (trigger")[0]) for r in trend_fired)
        if favourable:
            lead, number = "The direction of travel is favourable, but ", spell(count, False)
            verb = "still fired"
        else:
            lead, number, verb = "", spell(count), "fired"
        read += (f" {lead}{number} early-warning test"
                 f"{'s' if count != 1 else ''} {verb}: {listed}.")
    elif read:
        read += " No early-warning test fired this quarter."
    return "\n\n".join(p for p in (opening, second, read.strip()) if p)


def stress_commentary(row: pd.Series, stress: pd.DataFrame) -> tuple[str, str]:
    scenarios = stress.set_index("scenario")
    lines = ["| Scenario | EBITDA | Debt/EBITDA | EBITDA/interest | FCF/debt | Covenant |",
             "|---|---:|---:|---:|---:|:---:|"]
    for name, record in scenarios.iterrows():
        breach = "**Breach**" if record.get("breaches_leverage_covenant") else "Pass"
        if pd.isna(record.get("stressed_debt_to_ebitda")):
            breach = "n/a"
        lines.append(
            f"| {record['scenario_label']} | {auto_money(record.get('stressed_ebitda'))} "
            f"| {multiple(record.get('stressed_debt_to_ebitda'))} "
            f"| {multiple(record.get('stressed_interest_coverage'))} "
            f"| {percent(record.get('stressed_fcf_to_debt'))} | {breach} |")
    table = "\n".join(lines)

    combined = scenarios.loc["combined_recession"] if "combined_recession" in scenarios.index else None
    if combined is None:
        return table, "Stress results are unavailable for this name."

    stressed_leverage = combined.get("stressed_debt_to_ebitda")
    headroom = combined.get("covenant_headroom_turns")
    decline = combined.get("ebitda_decline_pct")
    cushion = row.get("ebitda_cushion_pct")

    baseline_leverage = row.get("debt_to_ebitda")
    already_breaching = pd.notna(baseline_leverage) and baseline_leverage > DEBT_EBITDA_COVENANT

    if pd.isna(stressed_leverage):
        survives = "The combined recession scenario cannot be evaluated on the available data."
    elif already_breaching:
        # "Survives the scenario" is the wrong frame for a name already outside
        # policy on its reported numbers.
        survives = (
            f"The name is already through the assumed {DEBT_EBITDA_COVENANT}x covenant on its "
            f"reported balance sheet at {multiple(baseline_leverage)}, so the scenarios measure "
            f"how much worse the position gets rather than whether it holds. Under the combined "
            f"recession, EBITDA falls {abs(decline):.0%} to "
            f"{auto_money(combined.get('stressed_ebitda'))} and leverage reaches "
            f"{multiple(stressed_leverage)}. There is no covenant cushion to erode.")
    elif stressed_leverage > DEBT_EBITDA_COVENANT:
        survives = (
            f"The name does **not** survive the combined recession scenario. EBITDA falls "
            f"{abs(decline):.0%} to {auto_money(combined.get('stressed_ebitda'))} and leverage "
            f"reaches {multiple(stressed_leverage)}, {abs(headroom):.2f} turns through the "
            f"assumed {DEBT_EBITDA_COVENANT}x covenant.")
    else:
        survives = (
            f"The name survives the combined recession scenario. EBITDA falls "
            f"{abs(decline):.0%} to {auto_money(combined.get('stressed_ebitda'))}, taking "
            f"leverage to {multiple(stressed_leverage)} — still "
            f"{points(headroom)} turns inside the assumed {DEBT_EBITDA_COVENANT}x covenant.")

    if pd.notna(cushion) and cushion > 0:
        survives += (f" On the reported balance sheet, EBITDA would have to fall "
                     f"{cushion:.0%} from its current level before the covenant is "
                     f"breached at all.")

    # The worst SINGLE shock, excluding the combined scenario -- which is by
    # construction the most damaging and so tells the reader nothing.
    single_shocks = scenarios.drop(index=["baseline", "combined_recession"], errors="ignore")
    leverage_by_scenario = single_shocks["stressed_debt_to_ebitda"].dropna()
    if not leverage_by_scenario.empty and leverage_by_scenario.max() > leverage_by_scenario.min():
        worst = leverage_by_scenario.idxmax()
        survives += (f" Of the individual shocks, *{scenarios.loc[worst, 'scenario_label']}* "
                     f"does the most damage, taking leverage to "
                     f"{multiple(leverage_by_scenario.max())}.")
    return table, survives


def key_risks(row: pd.Series, triggers: pd.DataFrame, stress: pd.DataFrame) -> list[str]:
    """Specific, evidenced risks -- not a generic retail risk list."""
    risks = []

    margin = row.get("operating_margin")
    if pd.notna(margin) and margin < 0.06:
        combined = stress[stress["scenario"] == "ebitda_margin_down_300bps"]
        effect = ""
        if not combined.empty and pd.notna(combined.iloc[0].get("stressed_debt_to_ebitda")):
            effect = (f" A 300bps margin loss alone takes leverage to "
                      f"{multiple(combined.iloc[0]['stressed_debt_to_ebitda'])}.")
        risks.append(
            f"**Margin convexity.** At a {percent(margin)} operating margin, a small "
            f"absolute change in margin is a large proportional change in EBITDA, so "
            f"leverage is far more sensitive to pricing and freight than the headline "
            f"multiple suggests.{effect}")

    equity = row.get("book_equity")
    if pd.notna(equity) and equity < 0:
        risks.append(
            f"**Negative book equity ({auto_money(equity)}).** There is no equity "
            f"cushion beneath the debt, recovery in a stress would depend entirely on "
            f"going-concern value, and the Altman Z\" of "
            f"{points(row.get('altman_z_double_prime'))} reflects this directly.")

    refi = row.get("pct_debt_due_within_1y")
    if pd.notna(refi) and refi > 0.20:
        risks.append(
            f"**Refinancing concentration.** {percent(refi, 0)} of debt "
            f"({auto_money(row.get('debt_due_within_1y'))}) matures within twelve "
            f"months, so the credit is exposed to capital-market access at a specific "
            f"date rather than to operating performance alone.")

    coverage = row.get("interest_coverage")
    if pd.notna(coverage) and coverage < 6:
        rate_scenario = stress[stress["scenario"] == "rates_up_200bps"]
        effect = ""
        if not rate_scenario.empty and pd.notna(rate_scenario.iloc[0].get("stressed_interest_coverage")):
            effect = (f" A 200bps rate rise on the assumed {FLOATING_RATE_DEBT_PCT:.0%} "
                      f"floating-rate share takes coverage to "
                      f"{multiple(rate_scenario.iloc[0]['stressed_interest_coverage'])}.")
        risks.append(f"**Interest-rate sensitivity.** Coverage of {multiple(coverage)} "
                     f"leaves limited absorption for higher funding costs.{effect}")

    liquidity = row.get("current_ratio")
    if pd.notna(liquidity) and liquidity < 1.2:
        risks.append(
            f"**Working-capital dependence.** A current ratio of {multiple(liquidity)} "
            f"means the business runs on supplier financing; any tightening of vendor "
            f"terms or credit insurance would pressure liquidity quickly, and the "
            f"assumed {INVENTORY_STRESS_PCT:.0%} inventory build takes the quick ratio to "
            f"{multiple(stress[stress['scenario'] == 'inventory_build_30pct'].iloc[0]['stressed_quick_ratio']) if not stress[stress['scenario'] == 'inventory_build_30pct'].empty else 'n/a'}.")

    trend_reasons = triggers[triggers["category"] == "Trend"]["reason"].tolist()
    for reason in trend_reasons[:2]:
        if "margin" in reason.lower() and any("Margin convexity" in r for r in risks):
            continue
        risks.append(f"**Deterioration already visible.** {reason}.")

    if not risks:
        risks.append(
            "**Sector cyclicality.** Discretionary retail demand moves with employment "
            "and real income; the current metrics are strong, but they are measured at "
            "a point in the cycle rather than through it.")
    risks.append(
        "**Model limitation.** Leverage here excludes capitalised operating leases and "
        "uses unadjusted EBITDA. A rating agency capitalising leases would report "
        "materially higher leverage for any store-based retailer, including this one.")
    return risks[:5]


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------
def build_memo(ticker: str, summary: pd.DataFrame, watchlist: pd.DataFrame,
               triggers: pd.DataFrame, stress: pd.DataFrame) -> str:
    row = summary[summary["ticker"] == ticker].iloc[0]
    flags = watchlist[watchlist["ticker"] == ticker].iloc[0]
    row = pd.concat([row, flags[["watchlist_severity", "on_watchlist"]]])
    company_triggers = triggers[triggers["ticker"] == ticker]
    company_stress = stress[stress["ticker"] == ticker]

    recommendation, basis = decide_recommendation(row, company_triggers)
    conditions = build_conditions(row, company_triggers, company_stress)
    stress_table, stress_text = stress_commentary(row, company_stress)
    as_of = pd.to_datetime(row["period_end_date"]).date()

    lines = [
        f"# Credit Memo — {row['company_name']} ({ticker})",
        "",
        f"**Recommendation: {recommendation}**",
        "",
        f"| | |",
        f"|---|---|",
        f"| Internal grade | **{row['credit_grade']}** (PD proxy band: {row['pd_proxy_band']}) |",
        f"| Watchlist status | {flags['watchlist_severity']} "
        f"({int(flags['trigger_count'])} trigger{'s' if flags['trigger_count'] != 1 else ''}) |",
        f"| Financials as of | {as_of} (latest filed quarter) |",
        f"| Scorecard | {points(row.get('scorecard_score'))} on a 0 = best / 2 = worst scale, "
        f"{percent(row.get('scorecard_coverage'), 0)} data coverage |",
        f"| Prepared from | SEC EDGAR XBRL filings via this repository's pipeline |",
        "",
        f"{basis}",
        "",
        "---",
        "",
        "## 1. Company overview",
        "",
        f"{COMPANY_PROFILES.get(ticker, 'No analyst profile on file for this issuer.')}",
        "",
        f"On the latest filed quarter the business generated {auto_money(row.get('revenue_ttm'))} "
        f"of trailing-twelve-month revenue and {auto_money(row.get('ebitda_ttm'))} of EBITDA, "
        f"against {auto_money(row.get('total_debt'))} of total debt and "
        f"{auto_money(row.get('liquid_assets'))} of cash and short-term investments.",
        "",
        "## 2. Key credit metrics",
        "",
        metrics_table(row),
        "",
        f"Thresholds are the assumed credit policy defined in `src/config.py`; they are "
        f"illustrative of public retail credit agreements, not real negotiated covenants.",
        "",
        "## 3. Trend commentary",
        "",
        trend_commentary(row, company_triggers),
        "",
        "## 4. Stress test results",
        "",
        stress_table,
        "",
        stress_text,
        "",
        f"Scenario assumptions: {FLOATING_RATE_DEBT_PCT:.0%} of debt floating-rate, "
        f"{EBITDA_TO_FCF_PASSTHROUGH:.0%} of any EBITDA decline passing through to free "
        f"cash flow, and a cash-funded {INVENTORY_STRESS_PCT:.0%} inventory build.",
        "",
        "---",
        "",
        "## 5. Recommendation rationale",
        "",
    ]

    # Rationale: the evidence for the decision, then what would change it.
    if company_triggers.empty:
        lines.append(
            f"{ticker} passes every credit-policy test on the latest filed quarter and "
            f"shows no year-on-year deterioration large enough to trigger the "
            f"early-warning tests. Leverage of {multiple(row.get('debt_to_ebitda'))} sits "
            f"{points(row.get('covenant_headroom_turns'))} turns inside the assumed "
            f"covenant, and the name remains compliant in every stress scenario run.")
    else:
        grouped = company_triggers.groupby("category")["reason"].apply(list).to_dict()
        lines.append(
            f"The recommendation rests on {len(company_triggers)} trigger"
            f"{'s' if len(company_triggers) != 1 else ''} across "
            f"{len(grouped)} categor{'ies' if len(grouped) != 1 else 'y'}:")
        lines.append("")
        labels = {"Level": "Breached today", "Trend": "Deteriorating",
                  "Stress": "Breaches under scenario"}
        for category in ("Level", "Trend", "Stress"):
            for reason in grouped.get(category, []):
                lines.append(f"- **{labels[category]}** — {reason}.")

    heading = {"REJECT": "**Requirements to reconsider**",
               "WATCHLIST": "**Remediation requirements**"}.get(recommendation, "**Conditions**")
    lines += ["", heading, ""]
    lines += [f"{index}. {condition}" for index, condition in enumerate(conditions, start=1)]

    # What would move the recommendation. The available moves depend on where
    # it currently sits -- a rejected name cannot be "downgraded to Reject".
    lines += ["", "**What would change this view**", ""]
    if recommendation == "APPROVE":
        lines.append(
            f"- *To Approve with Conditions:* leverage above "
            f"{DEBT_EBITDA_COVENANT * 0.8:.2f}x, coverage below "
            f"{MIN_INTEREST_COVERAGE * 1.5:.1f}x, or any early-warning trend test firing.")
        lines.append("- *To Watchlist:* any credit-policy test breached on a reported quarter.")
    elif recommendation == "APPROVE WITH CONDITIONS":
        lines.append(
            f"- *To Approve:* two consecutive quarters with no trigger firing and leverage "
            f"sustained below {DEBT_EBITDA_COVENANT * 0.6:.2f}x.")
        lines.append(
            f"- *To Watchlist or Reject:* any credit-policy test breached on a reported "
            f"quarter, Altman Z\" below {ALTMAN_ZPP_DISTRESS}, or failure to meet the "
            f"conditions above within the agreed window.")
    else:
        lines.append(
            f"- *To Approve with Conditions:* leverage returned below "
            f"{DEBT_EBITDA_COVENANT}x and Altman Z\" above {ALTMAN_ZPP_DISTRESS} on two "
            f"consecutive reported quarters, with a current ratio at or above "
            f"{MIN_CURRENT_RATIO}x.")
        lines.append(
            "- *Sustained rejection:* further deterioration in any breached test, or "
            "a deferral of the maturity profile onto shorter-dated funding.")

    lines += ["", "## 6. Key risks", ""]
    lines += [f"{index}. {risk}" for index, risk in enumerate(key_risks(row, company_triggers, company_stress), start=1)]

    lines += [
        "", "---", "",
        "## Basis of preparation",
        "",
        f"- All financial data is taken from {row['company_name']}'s SEC filings via the "
        f"XBRL API, as of the quarter ended {as_of}. Debt is sourced from "
        f"*{row.get('debt_source', 'n/a')}*; EBIT from *{row.get('ebit_source', 'n/a')}*; "
        f"interest on a *{row.get('interest_basis', 'n/a')}* basis.",
        "- Covenant thresholds, the floating-rate share, the inventory build and the "
        "cash-flow passthrough are **assumptions**, not terms of any real agreement.",
        "- The internal grade and PD proxy come from a rules-based scorecard that was "
        "not fitted to historical default data. They rank relative risk; they are not "
        "probabilities of default.",
        "- Leverage excludes capitalised operating leases, and EBITDA is unadjusted "
        "(no addbacks for impairment, restructuring or stock compensation).",
        "- The scorecard is quantitative only. It carries no view on management, "
        "competitive position or brand trajectory, all of which a credit committee "
        "would weigh alongside these figures.",
        "",
        f"*Generated by `src/build_memo.py` from the pipeline output. "
        f"Regenerating after a data refresh will update every figure in this memo.*",
        "",
    ]
    return "\n".join(lines)


def pick_default(watchlist: pd.DataFrame) -> str:
    """The most interesting name: worst severity, then most triggers. A memo on
    an obviously-healthy credit is less useful than one on a contested name."""
    order = {"High": 0, "Medium": 1, "Low": 2, "Clear": 3}
    ranked = watchlist.assign(_rank=watchlist["watchlist_severity"].map(order))
    ranked = ranked.sort_values(["_rank", "trigger_count"], ascending=[True, False])
    return ranked.iloc[0]["ticker"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", help="generate a memo for this ticker")
    parser.add_argument("--all", action="store_true",
                        help="generate a memo for every name on the watchlist")
    args = parser.parse_args()

    required = ["metrics_summary.csv", "watchlist.csv", "watchlist_triggers.csv",
                "stress_test_results.csv"]
    missing = [f for f in required if not (OUTPUT_DIR / f).exists()]
    if missing:
        print(f"Missing {', '.join(missing)}. Run the pipeline first.")
        return 1

    summary = pd.read_csv(OUTPUT_DIR / "metrics_summary.csv")
    watchlist = pd.read_csv(OUTPUT_DIR / "watchlist.csv")
    triggers = pd.read_csv(OUTPUT_DIR / "watchlist_triggers.csv")
    stress = pd.read_csv(OUTPUT_DIR / "stress_test_results.csv")

    if args.all:
        tickers = watchlist.loc[watchlist["on_watchlist"], "ticker"].tolist()
    elif args.ticker:
        tickers = [args.ticker.upper()]
    else:
        tickers = [pick_default(watchlist)]

    unknown = [t for t in tickers if t not in set(summary["ticker"])]
    if unknown:
        print(f"Unknown ticker(s): {', '.join(unknown)}. "
              f"Available: {', '.join(sorted(summary['ticker']))}")
        return 1

    MEMO_DIR.mkdir(parents=True, exist_ok=True)
    for ticker in tickers:
        memo = build_memo(ticker, summary, watchlist, triggers, stress)
        path = MEMO_DIR / f"{ticker}_credit_memo.md"
        path.write_text(memo)
        recommendation = memo.split("**Recommendation: ")[1].split("**")[0]
        print(f"  {ticker:5s} {recommendation:24s} -> {path.relative_to(OUTPUT_DIR.parent)}")

    print(f"\nWrote {len(tickers)} memo(s) to {MEMO_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
