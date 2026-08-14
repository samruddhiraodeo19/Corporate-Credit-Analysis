"""
Builds the Power BI dataset (PLAN Phase 7).

Usage:
    python src/build_powerbi.py

Produces output/powerbi/ containing a star-schema model, the DAX measures,
and a build guide for the three report pages.

Power BI Desktop is Windows-only and its .pbix is a proprietary binary, so
what this script produces is the *model* -- the part that carries the
analytical work -- laid out so that assembling the report is mechanical:
load the folder, confirm four relationships, paste the measures, drop the
visuals on the page.

Why a star schema rather than just pointing Power BI at the existing CSVs:
a single wide table forces every visual to reference a different column,
which means a new metric needs a new visual. With a metric dimension, one
chart sliced by `dim_metric` covers all of them, and the same measure works
on every page.

    dim_company ---<  fact_metric_quarterly  >--- dim_metric
         |       ---<  fact_stress           >--- dim_scenario
         |       ---<  fact_trigger
         |
    dim_date    ---<  fact_metric_quarterly
"""
import re
import shutil
import sys
from pathlib import Path

import pandas as pd

from config import (
    ALTMAN_ZPP_DISTRESS,
    ALTMAN_ZPP_SAFE,
    DEBT_EBITDA_COVENANT,
    MIN_CURRENT_RATIO,
    MIN_FCF_TO_DEBT,
    MIN_INTEREST_COVERAGE,
)

OUTPUT_DIR = Path(__file__).parent.parent / "output"
POWERBI_DIR = OUTPUT_DIR / "powerbi"

# Quarters of history to publish. Eight are needed for the trend page and
# another four to compute a year-on-year comparison against them; 20 gives
# headroom without shipping two decades of pre-taxonomy history.
QUARTERS_PUBLISHED = 20

# Metric catalogue: display name, category, Power BI format string, and the
# policy thresholds, so conditional formatting in the report reads its limits
# from the model instead of having them retyped into each visual.
METRIC_CATALOGUE = [
    ("debt_to_ebitda", "Debt / EBITDA", "Leverage", "Lower is better", '0.00"x"',
     2.0, DEBT_EBITDA_COVENANT),
    ("net_debt_to_ebitda", "Net debt / EBITDA", "Leverage", "Lower is better", '0.00"x"', 1.5, 3.5),
    ("interest_coverage", "EBITDA / interest", "Coverage", "Higher is better", '0.00"x"',
     6.0, MIN_INTEREST_COVERAGE),
    ("ebit_interest_coverage", "EBIT / interest", "Coverage", "Higher is better", '0.00"x"', 4.0, 1.5),
    ("fcf_to_debt", "FCF / debt", "Cash flow", "Higher is better", "0.0%", 0.20, MIN_FCF_TO_DEBT),
    ("current_ratio", "Current ratio", "Liquidity", "Higher is better", '0.00"x"',
     1.5, MIN_CURRENT_RATIO),
    ("quick_ratio", "Quick ratio", "Liquidity", "Higher is better", '0.00"x"', 0.8, 0.4),
    ("operating_margin", "Operating margin", "Profitability", "Higher is better", "0.0%", 0.08, 0.03),
    ("altman_z_double_prime", 'Altman Z"', "Distress", "Higher is better", "0.00",
     ALTMAN_ZPP_SAFE, ALTMAN_ZPP_DISTRESS),
    ("ebitda_ttm", "EBITDA (TTM)", "Scale", "Higher is better", '#,##0,,"m"', None, None),
    ("revenue_ttm", "Revenue (TTM)", "Scale", "Higher is better", '#,##0,,"m"', None, None),
    ("fcf_ttm", "Free cash flow (TTM)", "Cash flow", "Higher is better", '#,##0,,"m"', None, None),
    ("total_debt", "Total debt", "Leverage", "Lower is better", '#,##0,,"m"', None, None),
    ("net_debt", "Net debt", "Leverage", "Lower is better", '#,##0,,"m"', None, None),
    ("working_capital", "Working capital", "Liquidity", "Higher is better", '#,##0,,"m"', None, None),
]

# Sector labels are analyst-supplied context, not something XBRL carries.
SECTORS = {
    "TGT": "Mass merchant", "TJX": "Off-price", "ROST": "Off-price",
    "BURL": "Off-price", "DKS": "Sporting goods", "BBY": "Consumer electronics",
    "GAP": "Apparel", "ANF": "Apparel", "KSS": "Department store",
    "M": "Department store", "BBWI": "Specialty / beauty", "W": "E-commerce home",
}


def build_dim_date(dates: pd.Series) -> pd.DataFrame:
    """A contiguous daily date table. Power BI's time intelligence requires
    one marked date table with no gaps; quarter-end dates alone won't do."""
    span = pd.date_range(dates.min().replace(month=1, day=1),
                         dates.max() + pd.offsets.YearEnd(0), freq="D")
    frame = pd.DataFrame({"date": span})
    frame["year"] = frame["date"].dt.year
    frame["quarter"] = "Q" + frame["date"].dt.quarter.astype(str)
    frame["year_quarter"] = frame["year"].astype(str) + " " + frame["quarter"]
    frame["month"] = frame["date"].dt.month
    frame["month_name"] = frame["date"].dt.strftime("%b")
    frame["month_year"] = frame["date"].dt.strftime("%b %Y")
    # Sort keys, so "Feb 2026" orders chronologically rather than alphabetically.
    frame["month_year_sort"] = frame["year"] * 100 + frame["month"]
    frame["is_quarter_end"] = frame["date"].isin(dates)
    return frame


def build_dim_company(summary: pd.DataFrame, watchlist: pd.DataFrame) -> pd.DataFrame:
    company = summary[["ticker", "company_name", "credit_grade", "pd_proxy_band",
                       "scorecard_score", "scorecard_coverage", "altman_zone",
                       "debt_source", "ebit_source", "interest_basis"]].copy()
    flags = watchlist[["ticker", "watchlist_severity", "on_watchlist",
                       "trigger_count", "sub_investment_grade"]]
    company = company.merge(flags, on="ticker", how="left")
    company["sector"] = company["ticker"].map(SECTORS)
    # Explicit sort orders: without them Power BI sorts "AA, A, B, BB, BBB"
    # alphabetically, which puts B ahead of BB and reads as nonsense.
    grade_order = {g: i for i, g in enumerate(["AA", "A", "BBB", "BB", "B", "CCC", "NR"])}
    severity_order = {s: i for i, s in enumerate(["High", "Medium", "Low", "Clear"])}
    company["grade_sort"] = company["credit_grade"].map(grade_order)
    company["severity_sort"] = company["watchlist_severity"].map(severity_order)
    return company.sort_values("grade_sort")


def build_dim_metric() -> pd.DataFrame:
    return pd.DataFrame(
        [(key, name, category, direction, fmt, good, weak, index)
         for index, (key, name, category, direction, fmt, good, weak)
         in enumerate(METRIC_CATALOGUE)],
        columns=["metric", "metric_name", "metric_category", "direction",
                 "format_string", "good_threshold", "weak_threshold", "metric_sort"])


def build_dim_scenario(stress: pd.DataFrame) -> pd.DataFrame:
    from stress_test import SCENARIOS

    rows = []
    for index, (name, params) in enumerate(SCENARIOS.items()):
        label = stress.loc[stress["scenario"] == name, "scenario_label"]
        rows.append({
            "scenario": name,
            "scenario_label": label.iloc[0] if not label.empty else name,
            "scenario_sort": index,
            "is_baseline": name == "baseline",
            "revenue_shock": params.get("revenue_shock", 0.0),
            "margin_shock_pts": params.get("margin_shock_pts", 0.0),
            "rate_shock_pts": params.get("rate_shock_pts", 0.0),
            "inventory_shock": params.get("inventory_shock", 0.0),
        })
    return pd.DataFrame(rows)


def build_fact_metrics(all_periods: pd.DataFrame) -> pd.DataFrame:
    """Long-format quarterly facts: one row per company / date / metric."""
    metrics = [key for key, *_ in METRIC_CATALOGUE if key in all_periods.columns]
    recent = all_periods.sort_values("period_end_date").groupby("ticker").tail(QUARTERS_PUBLISHED)
    tidy = recent.melt(id_vars=["ticker", "period_end_date"], value_vars=metrics,
                       var_name="metric", value_name="value")
    tidy = tidy.dropna(subset=["value"])
    # Surrogate key for the date relationship.
    tidy = tidy.rename(columns={"period_end_date": "date"})
    return tidy.sort_values(["ticker", "metric", "date"])


def build_fact_stress(stress: pd.DataFrame) -> pd.DataFrame:
    """Long-format stress results, so one visual covers every stressed measure."""
    measures = ["stressed_ebitda", "stressed_debt_to_ebitda", "stressed_net_debt_to_ebitda",
                "stressed_interest_coverage", "stressed_fcf", "stressed_fcf_to_debt",
                "stressed_current_ratio", "stressed_quick_ratio", "covenant_headroom_turns",
                "ebitda_decline_pct"]
    present = [m for m in measures if m in stress.columns]
    tidy = stress.melt(id_vars=["ticker", "scenario"], value_vars=present,
                       var_name="measure", value_name="value")
    breaches = stress[["ticker", "scenario", "breaches_leverage_covenant",
                       "breaches_coverage_floor", "breaches_current_ratio_floor"]]
    tidy = tidy.merge(breaches, on=["ticker", "scenario"], how="left")
    tidy["measure_name"] = tidy["measure"].str.replace("stressed_", "", regex=False) \
        .str.replace("_", " ").str.capitalize()
    return tidy.dropna(subset=["value"])


MEASURES_DAX = f"""// ---------------------------------------------------------------------------
// DAX measures for the credit-risk dashboard
// Paste each block into Power BI via Modeling > New measure.
// Thresholds are read from dim_metric where possible so the report never
// hardcodes a policy limit that config.py owns.
// ---------------------------------------------------------------------------

// --- Portfolio headline measures -------------------------------------------

Companies Covered = DISTINCTCOUNT ( dim_company[ticker] )

Names On Watchlist =
CALCULATE ( DISTINCTCOUNT ( dim_company[ticker] ), dim_company[on_watchlist] = TRUE () )

% On Watchlist =
DIVIDE ( [Names On Watchlist], [Companies Covered] )

Sub-Investment Grade Names =
CALCULATE ( DISTINCTCOUNT ( dim_company[ticker] ), dim_company[sub_investment_grade] = TRUE () )

Total Triggers = COUNTROWS ( fact_trigger )

High Severity Triggers =
CALCULATE ( COUNTROWS ( fact_trigger ), fact_trigger[severity] = "High" )

// --- Latest-quarter metric values ------------------------------------------
// Every visual reads through this one measure. Because it resolves the latest
// date WITHIN the current filter context, the same measure works on a company
// page, a portfolio table, or a scatter plot without modification.

Latest Date = MAX ( fact_metric_quarterly[date] )

Metric Value =
VAR LatestDate =
    CALCULATE ( MAX ( fact_metric_quarterly[date] ), ALLEXCEPT ( fact_metric_quarterly, dim_company ) )
RETURN
    CALCULATE ( SUM ( fact_metric_quarterly[value] ), fact_metric_quarterly[date] = LatestDate )

// Named shortcuts for the scatter plot axes and KPI cards.

Debt to EBITDA =
CALCULATE ( [Metric Value], dim_metric[metric] = "debt_to_ebitda" )

Interest Coverage =
CALCULATE ( [Metric Value], dim_metric[metric] = "interest_coverage" )

FCF to Debt =
CALCULATE ( [Metric Value], dim_metric[metric] = "fcf_to_debt" )

Current Ratio =
CALCULATE ( [Metric Value], dim_metric[metric] = "current_ratio" )

Altman Z Double Prime =
CALCULATE ( [Metric Value], dim_metric[metric] = "altman_z_double_prime" )

EBITDA TTM =
CALCULATE ( [Metric Value], dim_metric[metric] = "ebitda_ttm" )

Total Debt =
CALCULATE ( [Metric Value], dim_metric[metric] = "total_debt" )

// --- Portfolio aggregates ---------------------------------------------------
// Portfolio leverage is deliberately debt-weighted, not an average of ratios:
// averaging multiples lets a tiny debt-free name offset a large levered one.

Portfolio Debt / EBITDA =
VAR TotalDebtAll =
    SUMX ( VALUES ( dim_company[ticker] ), [Total Debt] )
VAR TotalEbitdaAll =
    SUMX ( VALUES ( dim_company[ticker] ), [EBITDA TTM] )
RETURN
    DIVIDE ( TotalDebtAll, TotalEbitdaAll )

Median Debt / EBITDA =
MEDIANX ( VALUES ( dim_company[ticker] ), [Debt to EBITDA] )

// --- Covenant testing -------------------------------------------------------

Assumed Covenant = {DEBT_EBITDA_COVENANT}

Covenant Headroom =
VAR Leverage = [Debt to EBITDA]
RETURN
    IF ( NOT ISBLANK ( Leverage ), [Assumed Covenant] - Leverage )

Covenant Status =
VAR Leverage = [Debt to EBITDA]
RETURN
    SWITCH (
        TRUE (),
        ISBLANK ( Leverage ), "No data",
        Leverage > [Assumed Covenant], "Breach",
        Leverage > [Assumed Covenant] * 0.8, "Tight",
        "Compliant"
    )

// --- Stress measures --------------------------------------------------------

Stressed Value = SUM ( fact_stress[value] )

Stressed Debt to EBITDA =
CALCULATE ( [Stressed Value], fact_stress[measure] = "stressed_debt_to_ebitda" )

Stressed Interest Coverage =
CALCULATE ( [Stressed Value], fact_stress[measure] = "stressed_interest_coverage" )

Names Breaching Covenant =
CALCULATE (
    DISTINCTCOUNT ( fact_stress[ticker] ),
    fact_stress[breaches_leverage_covenant] = TRUE ()
)

// Names pushed into breach BY the scenario, excluding those already in breach
// at baseline -- the number a credit committee actually asks for.
Newly Breaching Under Scenario =
VAR BaselineBreachers =
    CALCULATETABLE (
        VALUES ( fact_stress[ticker] ),
        ALL ( dim_scenario ),
        dim_scenario[is_baseline] = TRUE (),
        fact_stress[breaches_leverage_covenant] = TRUE ()
    )
VAR ScenarioBreachers =
    CALCULATETABLE (
        VALUES ( fact_stress[ticker] ),
        fact_stress[breaches_leverage_covenant] = TRUE ()
    )
RETURN
    COUNTROWS ( EXCEPT ( ScenarioBreachers, BaselineBreachers ) )

// --- Conditional formatting helpers ----------------------------------------
// Return hex colours; bind via Format > Cell elements > Background colour >
// Format style = Field value.

Leverage Colour =
VAR Leverage = [Debt to EBITDA]
RETURN
    SWITCH (
        TRUE (),
        ISBLANK ( Leverage ), "#F2F2F2",
        Leverage > [Assumed Covenant], "#C00000",
        Leverage > 2, "#FFC000",
        "#4EA72E"
    )

Stress Breach Colour =
IF ( SELECTEDVALUE ( fact_stress[breaches_leverage_covenant] ) = TRUE (), "#C00000", "#FFFFFF" )

Severity Colour =
SWITCH (
    SELECTEDVALUE ( dim_company[watchlist_severity] ),
    "High", "#C00000",
    "Medium", "#FFC000",
    "Low", "#FFE699",
    "#4EA72E"
)
"""


BUILD_GUIDE = f"""# Power BI build guide

The analytical work lives in the model in this folder. Power BI Desktop is
Windows-only and `.pbix` is a proprietary binary, so the report itself has to
be assembled in the application — these steps make that mechanical.

## 1. Load the data

**Home > Get data > Text/CSV**, and load all eight files in this folder. Or
**Get data > Folder** and point at this directory to load them in one step.

In **Transform data**, confirm the types Power BI inferred:

- `dim_date[date]` and `fact_metric_quarterly[date]` → **Date**
- every `value`, threshold and shock column → **Decimal number**
- `on_watchlist`, `sub_investment_grade`, `is_baseline`, `breaches_*` → **True/False**

## 2. Create the relationships

Power BI will guess some of these. Delete anything it invented that isn't on
this list, then create the rest in **Model view** by dragging field to field.
All are one-to-many, single direction, from the dimension to the fact.

| From (one side) | To (many side) |
|---|---|
| `dim_company[ticker]` | `fact_metric_quarterly[ticker]` |
| `dim_metric[metric]` | `fact_metric_quarterly[metric]` |
| `dim_date[date]` | `fact_metric_quarterly[date]` |
| `dim_company[ticker]` | `fact_stress[ticker]` |
| `dim_scenario[scenario]` | `fact_stress[scenario]` |
| `dim_company[ticker]` | `fact_trigger[ticker]` |

Then **Table tools > Mark as date table** on `dim_date`, using `date`.

## 3. Set sort orders

Without this, Power BI sorts grades alphabetically and puts `B` ahead of `BB`.
Select the column, then **Column tools > Sort by column**:

- `dim_company[credit_grade]` → sort by `grade_sort`
- `dim_company[watchlist_severity]` → sort by `severity_sort`
- `dim_scenario[scenario_label]` → sort by `scenario_sort`
- `dim_metric[metric_name]` → sort by `metric_sort`
- `dim_date[month_year]` → sort by `month_year_sort`

## 4. Add the measures

Open `measures.dax` and paste each block via **Modeling > New measure**.

## 5. Build the three pages

### Page 1 — Portfolio Overview

- **Cards** across the top: `Companies Covered`, `Names On Watchlist`,
  `% On Watchlist`, `Sub-Investment Grade Names`, `Portfolio Debt / EBITDA`.
- **Matrix**: rows `dim_company[ticker]` and `company_name`; values
  `Debt to EBITDA`, `Interest Coverage`, `FCF to Debt`, `Current Ratio`,
  `Altman Z Double Prime`, `Covenant Headroom`, plus `credit_grade` and
  `watchlist_severity`. Set the Debt/EBITDA background colour to
  **Field value → `Leverage Colour`**.
- **Scatter chart** — the single visual that tells most of the story:
  X = `Debt to EBITDA`, Y = `Interest Coverage`, Details = `dim_company[ticker]`,
  Legend = `dim_company[watchlist_severity]`, Size = `EBITDA TTM`.
  Add an X-axis constant line at **{DEBT_EBITDA_COVENANT}** (the assumed covenant)
  and a Y-axis constant line at **{MIN_INTEREST_COVERAGE}** (the coverage floor).
  The bottom-right quadrant is the problem set.
- **Slicers**: `dim_company[sector]` and `dim_company[credit_grade]`.

### Page 2 — Company Deep Dive

- **Slicer** on `dim_company[ticker]`, set to **Single select**.
- **Line chart**: X = `dim_date[month_year]`, Y = `SUM(fact_metric_quarterly[value])`,
  Small multiples = `dim_metric[metric_name]`, filtered to the ratio metrics.
  This is the eight-quarter trend; because it is driven by `dim_metric`, adding
  a metric to the catalogue adds a panel with no rework.
- **Cards**: `Debt to EBITDA`, `Interest Coverage`, `Covenant Headroom`,
  `Covenant Status`.
- **Table**: `fact_trigger[category]`, `severity`, `reason` — the reasons this
  name is (or isn't) on the watchlist, in the analyst's own words.
- **Column chart**: X = `dim_scenario[scenario_label]`,
  Y = `Stressed Debt to EBITDA`, with a constant line at {DEBT_EBITDA_COVENANT}.

### Page 3 — Stress Test Matrix

- **Matrix**: rows `dim_company[ticker]`, columns `dim_scenario[scenario_label]`,
  values `Stressed Debt to EBITDA`. Background colour → **Field value →
  `Stress Breach Colour`** to get the heatmap: every red cell is a covenant breach.
- **Second matrix** below it with `Stressed Interest Coverage`. The rate and
  inventory shocks don't move EBITDA, so they cannot change a leverage multiple —
  their effect is only visible on this second matrix and on liquidity.
- **Cards**: `Names Breaching Covenant` and `Newly Breaching Under Scenario`.
- **Slicer** on `dim_scenario[scenario_label]` to drive the cards.

## 6. Refresh

Re-run `python src/run_pipeline.py --refresh`, then **Home > Refresh** in Power
BI. The file names and columns are stable, so the report keeps working.

## Note on connecting to SQLite instead

The guide above uses the CSV extracts because they need no driver. Power BI can
read `db/credit_risk.db` directly through an ODBC SQLite driver, but that is an
extra install on every machine that opens the report, and the extracts are the
same numbers.
"""


def main() -> int:
    required = ["metrics_summary.csv", "metrics_all_periods.csv", "watchlist.csv",
                "watchlist_triggers.csv", "stress_test_results.csv"]
    missing = [f for f in required if not (OUTPUT_DIR / f).exists()]
    if missing:
        print(f"Missing {', '.join(missing)}. Run the pipeline first.")
        return 1

    summary = pd.read_csv(OUTPUT_DIR / "metrics_summary.csv", parse_dates=["period_end_date"])
    all_periods = pd.read_csv(OUTPUT_DIR / "metrics_all_periods.csv",
                              parse_dates=["period_end_date"])
    watchlist = pd.read_csv(OUTPUT_DIR / "watchlist.csv")
    triggers = pd.read_csv(OUTPUT_DIR / "watchlist_triggers.csv")
    stress = pd.read_csv(OUTPUT_DIR / "stress_test_results.csv")

    if POWERBI_DIR.exists():
        shutil.rmtree(POWERBI_DIR)
    POWERBI_DIR.mkdir(parents=True)

    fact_metrics = build_fact_metrics(all_periods)
    tables = {
        "dim_company": build_dim_company(summary, watchlist),
        "dim_metric": build_dim_metric(),
        "dim_scenario": build_dim_scenario(stress),
        "dim_date": build_dim_date(fact_metrics["date"]),
        "fact_metric_quarterly": fact_metrics,
        "fact_stress": build_fact_stress(stress),
        "fact_trigger": triggers,
    }
    for name, frame in tables.items():
        frame.to_csv(POWERBI_DIR / f"{name}.csv", index=False)

    (POWERBI_DIR / "measures.dax").write_text(MEASURES_DAX)
    (POWERBI_DIR / "BUILD_GUIDE.md").write_text(BUILD_GUIDE)

    print(f"Built the Power BI dataset -> {POWERBI_DIR}\n")
    for name, frame in tables.items():
        kind = "dimension" if name.startswith("dim") else "fact"
        print(f"  {name:24s} {len(frame):6,d} rows  ({kind}, {len(frame.columns)} cols)")
    measure_count = len(re.findall(r"^[A-Z][\w %/'-]*\s=", MEASURES_DAX, re.MULTILINE))
    print(f"\n  measures.dax             {measure_count} measures")
    print("  BUILD_GUIDE.md           relationships, sort orders, and the 3 report pages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
