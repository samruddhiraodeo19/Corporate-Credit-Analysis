"""
Computes the credit metric suite from the quarterly panel in SQLite.

Usage:
    python src/calc_metrics.py

Outputs:
    output/metrics_all_periods.csv  full quarterly history, every metric
    output/metrics_summary.csv      latest quarter per company
    output/trends.csv               tidy 8-quarter trend series (for BI tools)

Two rules govern everything here:

  * A missing input produces NaN, never zero. "We could not extract this
    company's debt" and "this company has no debt" are different facts and
    must not collapse into the same number -- an earlier version summed
    missing debt legs with .fillna(0) and reported $0 debt (and an "A"
    grade) for four companies that plainly have debt.

  * Flows are summed over four quarters; stocks are read at a point in
    time. A trailing-twelve-month figure is only produced when four
    genuinely consecutive quarters are present.
"""
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from config import (
    ALTMAN_ZPP_DISTRESS,
    ALTMAN_ZPP_SAFE,
    DEBT_EBITDA_COVENANT,
    FLOW_METRICS,
    GRADE_BANDS,
    MATURITY_LADDER_MAX_AGE_DAYS,
    MATURITY_LADDER_MIN_BUCKETS,
    MATURITY_LADDER_RECONCILE_TOLERANCE,
    MAX_QUARTER_GAP_DAYS,
    MIN_SCORECARD_COVERAGE,
    PD_BANDS,
    SCORECARD,
    TREND_QUARTERS,
)

DB_PATH = Path(__file__).parent.parent / "db" / "credit_risk.db"
OUTPUT_DIR = Path(__file__).parent.parent / "output"

# Balance-sheet inputs may legitimately be disclosed only at year-end. They
# are carried forward at most this many quarters, and the effective as-of date
# is reported alongside so a stale input is visible rather than invisible.
MAX_STOCK_CARRYFORWARD = 1

TREND_METRICS = [
    "operating_margin", "working_capital", "debt_to_ebitda",
    "interest_coverage", "current_ratio", "quick_ratio",
    "ebitda_ttm", "fcf_ttm", "altman_z_double_prime",
]


# ---------------------------------------------------------------------------
# Panel assembly
# ---------------------------------------------------------------------------
def load_panel(conn: sqlite3.Connection) -> pd.DataFrame:
    """Pivot the long financials table into one row per company-quarter."""
    df = pd.read_sql("SELECT ticker, metric, period_end_date, value FROM financials", conn)
    panel = (
        df.pivot_table(index=["ticker", "period_end_date"], columns="metric",
                       values="value", aggfunc="last")
        .reset_index()
        .rename_axis(columns=None)
    )
    panel["period_end_date"] = pd.to_datetime(panel["period_end_date"])
    return panel.sort_values(["ticker", "period_end_date"]).reset_index(drop=True)


def column(panel: pd.DataFrame, name: str) -> pd.Series:
    """Return a metric column, or an all-NaN column if it was never extracted.
    Keeps a missing concept out of the arithmetic instead of defaulting it to
    zero and silently flattering the credit."""
    if name in panel.columns:
        return panel[name]
    return pd.Series(np.nan, index=panel.index, dtype="float64")


def carry_forward_stocks(panel: pd.DataFrame) -> pd.DataFrame:
    """Carry balance-sheet values forward at most MAX_STOCK_CARRYFORWARD
    quarters and record the date each company's balance sheet is really as of."""
    panel = panel.copy()
    stock_cols = [c for c in panel.columns
                  if c not in ("ticker", "period_end_date") and c not in FLOW_METRICS]

    has_bs = (panel["total_assets"].notna() if "total_assets" in panel.columns
              else pd.Series(False, index=panel.index))
    panel["balance_sheet_as_of"] = panel["period_end_date"].where(has_bs)
    panel["balance_sheet_as_of"] = panel.groupby("ticker")["balance_sheet_as_of"].ffill(
        limit=MAX_STOCK_CARRYFORWARD)

    for col in stock_cols:
        panel[col] = panel.groupby("ticker")[col].ffill(limit=MAX_STOCK_CARRYFORWARD)
    return panel


def add_ttm(panel: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Trailing-twelve-month sums for flow metrics.

    A TTM is only valid over four CONSECUTIVE quarters. If a quarter is
    missing, the four rows in the window span more than a year and their sum
    would silently overstate the period, so the result is suppressed.
    """
    panel = panel.copy()
    gap_days = panel.groupby("ticker")["period_end_date"].diff().dt.days
    broken = (gap_days > MAX_QUARTER_GAP_DAYS).fillna(False)
    # Rows i-3..i contain the three inter-quarter gaps at i-2, i-1 and i.
    window_broken = broken.groupby(panel["ticker"]).transform(
        lambda s: s.rolling(3, min_periods=1).max()).astype(bool)

    for col in cols:
        values = column(panel, col)
        ttm = values.groupby(panel["ticker"]).transform(
            lambda s: s.rolling(4, min_periods=4).sum())
        panel[f"{col}_ttm"] = ttm.where(~window_broken)
    return panel


def add_derived_inputs(panel: pd.DataFrame) -> pd.DataFrame:
    """Reconcile the alternative disclosure styles into single clean inputs."""
    panel = panel.copy()

    # Net non-operating interest, signed so that POSITIVE = net income.
    # Either taken from a net tag directly, or built from the gross legs.
    gross_interest = column(panel, "interest_expense")
    interest_income = column(panel, "interest_income")
    has_legs = gross_interest.notna() | interest_income.notna()
    from_legs = (interest_income.fillna(0) - gross_interest.fillna(0)).where(has_legs)
    net_interest = column(panel, "net_interest_income").fillna(from_legs)

    # EBIT: use the tagged operating-income subtotal where it exists, else
    # rebuild it from the bottom up as pretax income less net interest income.
    # Burlington and (since FY2019) TJX never tag an operating-income line.
    # Subtracting NET interest matters: TJX earns more interest than it pays,
    # so treating pretax income as EBIT would overstate it by ~$200m a year.
    rebuilt_ebit = column(panel, "pretax_income") - net_interest.fillna(0)
    rebuilt_ebit = rebuilt_ebit.where(column(panel, "pretax_income").notna())
    panel["ebit"] = column(panel, "operating_income").fillna(rebuilt_ebit)
    panel["ebit_source"] = np.where(
        column(panel, "operating_income").notna(), "reported",
        np.where(rebuilt_ebit.notna(), "derived: pretax less net interest", "unavailable"))

    # Interest expense for coverage: prefer gross (the rating-agency
    # convention). Where a company only discloses net interest quarterly, use
    # the net expense. A company earning net interest income carries no
    # interest burden at all -- recorded as 0 rather than as missing data, so
    # coverage scores as strongest instead of dropping out of the scorecard.
    net_expense = (-net_interest).clip(lower=0)
    panel["interest_expense_eff"] = gross_interest.fillna(net_expense)
    panel["interest_basis"] = np.where(
        gross_interest.notna(), "gross",
        np.where(net_interest.notna(), "net of interest income", "unavailable"))

    # Total debt: sum the current/noncurrent legs where either is disclosed,
    # otherwise fall back to a combined debt tag. Never zero-filled from
    # nothing -- a company with no debt data stays NaN.
    legs = [column(panel, c) for c in ("debt_noncurrent", "debt_current", "short_term_borrowings")]
    any_leg = pd.concat([s.notna() for s in legs], axis=1).any(axis=1)
    leg_sum = pd.concat([s.fillna(0) for s in legs], axis=1).sum(axis=1).where(any_leg)
    total_debt = leg_sum.fillna(column(panel, "debt_total_reported"))
    source = np.where(any_leg, "current + noncurrent legs",
                      np.where(column(panel, "debt_total_reported").notna(),
                               "combined debt tag", "unavailable"))

    # A company that repays its last borrowing stops tagging debt concepts
    # altogether, because the caption leaves its balance sheet (Abercrombie
    # tagged LongTermDebtNoncurrent = 0 through FY2024, then dropped it).
    # Where the last value a company actually reported was zero, later gaps
    # are nil debt, not unknown debt. Companies that never reported a debt
    # concept stay NaN -- that could equally be an extraction failure.
    last_reported = total_debt.groupby(panel["ticker"]).ffill()
    infer_nil = total_debt.isna() & (last_reported == 0)
    panel["total_debt"] = total_debt.mask(infer_nil, 0.0)
    panel["debt_source"] = np.where(infer_nil, "nil (debt caption removed after full repayment)", source)

    # Only 1 of 12 retailers tags the `Liabilities` subtotal, so derive it
    # from the balance-sheet identity where it's absent.
    derived_liabilities = column(panel, "total_assets") - column(panel, "total_equity_incl_nci")
    panel["total_liabilities_eff"] = column(panel, "total_liabilities").fillna(derived_liabilities)

    panel["book_equity"] = column(panel, "total_equity_incl_nci").fillna(
        column(panel, "stockholders_equity"))
    panel["liquid_assets"] = column(panel, "cash").fillna(0) + \
        column(panel, "short_term_investments").fillna(0)
    panel["liquid_assets"] = panel["liquid_assets"].where(column(panel, "cash").notna())
    return panel


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
def safe_div(numerator: pd.Series, denominator: pd.Series,
             require_positive_denominator: bool = False) -> pd.Series:
    """Divide, returning NaN rather than +/-inf where the denominator is zero.

    `require_positive_denominator` additionally suppresses the ratio when the
    denominator is negative. A leverage multiple against NEGATIVE EBITDA is
    the classic credit-analysis trap: -3.0x looks better than 8.0x on a sort,
    but it means the company has no earnings at all.
    """
    denom = pd.to_numeric(denominator, errors="coerce")
    valid = denom.notna() & (denom != 0)
    if require_positive_denominator:
        valid &= denom > 0
    return (pd.to_numeric(numerator, errors="coerce") / denom.where(valid))


def calc_metrics(panel: pd.DataFrame) -> pd.DataFrame:
    flows = [c for c in FLOW_METRICS if c in panel.columns] + ["ebit", "interest_expense_eff"]
    out = add_ttm(panel, flows)

    # 1. EBITDA (TTM) = EBIT + D&A
    out["ebitda_ttm"] = out["ebit_ttm"] + column(out, "depreciation_amortization_ttm")

    # 2/3. Leverage
    out["net_debt"] = out["total_debt"] - out["liquid_assets"].fillna(0)
    out["debt_to_ebitda"] = safe_div(out["total_debt"], out["ebitda_ttm"], True)
    out["net_debt_to_ebitda"] = safe_div(out["net_debt"], out["ebitda_ttm"], True)

    # 4. Coverage. Where the company earns net interest income there is no
    # interest burden to cover, so the ratio is not meaningful (recorded as
    # NaN) but is scored as strongest rather than as missing.
    interest_ttm = out["interest_expense_eff_ttm"]
    out["interest_coverage"] = safe_div(out["ebitda_ttm"], interest_ttm, True)
    out["ebit_interest_coverage"] = safe_div(out["ebit_ttm"], interest_ttm, True)
    out["no_interest_burden"] = interest_ttm.notna() & (interest_ttm <= 0)

    # 5. Cash generation
    out["fcf_ttm"] = out["operating_cash_flow_ttm"] - column(out, "capex_ttm")
    out["fcf_to_debt"] = safe_div(out["fcf_ttm"], out["total_debt"], True)
    # Debt-free: FCF/Debt and leverage are undefined rather than missing, and
    # represent the strongest possible position, not an absent data point.
    out["no_debt"] = out["total_debt"].notna() & (out["total_debt"] == 0)

    # 6/7. Liquidity
    current_assets, current_liabilities = column(out, "current_assets"), column(out, "current_liabilities")
    out["current_ratio"] = safe_div(current_assets, current_liabilities, True)
    out["quick_ratio"] = safe_div(current_assets - column(out, "inventory").fillna(0),
                                  current_liabilities, True)
    out["working_capital"] = current_assets - current_liabilities

    # 9. Cash burn: quarter-on-quarter cash movement, plus a count of
    # consecutive negative-FCF quarters (the actual early-warning signal).
    out["quarterly_fcf"] = column(out, "operating_cash_flow") - column(out, "capex").fillna(0)
    out["cash_change_qoq"] = out.groupby("ticker")["cash"].diff() if "cash" in out else np.nan
    negative = out["quarterly_fcf"] < 0
    out["consecutive_fcf_negative_qtrs"] = negative.groupby(
        [out["ticker"], (~negative).cumsum()]).cumsum()

    # 10/11. Trend inputs
    out["operating_margin"] = safe_div(out["ebit_ttm"], column(out, "revenue_ttm"))

    # 12. Altman Z. Z" (non-manufacturer revision) is the headline: it uses
    # book equity instead of market cap, so it is fully computable from
    # filings, and it drops the asset-turnover term that inflates the
    # original manufacturing Z for high-turnover retailers. Z' is carried
    # alongside for reference.
    total_assets = column(out, "total_assets")
    a = safe_div(out["working_capital"], total_assets, True)
    b = safe_div(column(out, "retained_earnings"), total_assets, True)
    c = safe_div(out["ebit_ttm"], total_assets, True)
    d = safe_div(out["book_equity"], out["total_liabilities_eff"], True)
    e = safe_div(column(out, "revenue_ttm"), total_assets, True)
    out["altman_z_double_prime"] = 6.56 * a + 3.26 * b + 6.72 * c + 1.05 * d
    out["altman_z_prime"] = 0.717 * a + 0.847 * b + 3.107 * c + 0.420 * d + 0.998 * e
    out["altman_zone"] = pd.cut(
        out["altman_z_double_prime"],
        bins=[-np.inf, ALTMAN_ZPP_DISTRESS, ALTMAN_ZPP_SAFE, np.inf],
        labels=["Distress", "Grey", "Safe"])

    # Covenant headroom against the ASSUMED maintenance test (see config).
    out["covenant_headroom_turns"] = DEBT_EBITDA_COVENANT - out["debt_to_ebitda"]
    # How far EBITDA could fall before the assumed covenant trips.
    covenant_min_ebitda = safe_div(out["total_debt"], pd.Series(
        DEBT_EBITDA_COVENANT, index=out.index))
    out["ebitda_cushion_pct"] = safe_div(out["ebitda_ttm"] - covenant_min_ebitda, out["ebitda_ttm"], True)

    return out


# ---------------------------------------------------------------------------
# Scorecard -> PD proxy band and internal credit grade
# ---------------------------------------------------------------------------
def _factor_points(value: float, direction: str, thresholds: list[float]) -> float | None:
    if value is None or pd.isna(value):
        return None
    good, weak = thresholds
    if direction == "lower_better":
        return 0.0 if value <= good else (1.0 if value <= weak else 2.0)
    return 0.0 if value >= good else (1.0 if value >= weak else 2.0)


def score_row(row: pd.Series) -> pd.Series:
    """Weighted 0-2 scorecard. Factors with no data are excluded from both
    the numerator and the denominator, and the share of weight actually
    available is reported -- so a thin data set produces a suppressed grade
    rather than a flattering one."""
    weighted_sum = available_weight = 0.0
    missing = []
    for metric, direction, thresholds, weight in SCORECARD:
        value = row.get(metric)
        # An undefined ratio because there is nothing to cover or repay is the
        # best possible outcome, not an absent data point.
        no_burden = metric == "interest_coverage" and row.get("no_interest_burden")
        no_debt = metric == "fcf_to_debt" and row.get("no_debt")
        if no_burden or no_debt:
            points = 0.0
        else:
            points = _factor_points(value, direction, thresholds)
        if points is None:
            missing.append(metric)
            continue
        weighted_sum += points * weight
        available_weight += weight

    total_weight = sum(w for *_, w in SCORECARD)
    coverage = available_weight / total_weight
    if available_weight == 0 or coverage < MIN_SCORECARD_COVERAGE:
        return pd.Series({
            "scorecard_score": np.nan, "scorecard_coverage": round(coverage, 3),
            "credit_grade": "NR", "pd_proxy_band": "Insufficient data",
            "scorecard_missing": ",".join(missing),
        })

    score = weighted_sum / available_weight
    grade = next(g for cutoff, g in GRADE_BANDS if score <= cutoff)
    band = next(b for cutoff, b in PD_BANDS if score <= cutoff)
    return pd.Series({
        "scorecard_score": round(score, 3), "scorecard_coverage": round(coverage, 3),
        "credit_grade": grade, "pd_proxy_band": band,
        "scorecard_missing": ",".join(missing),
    })


def add_scorecard(out: pd.DataFrame) -> pd.DataFrame:
    return out.join(out.apply(score_row, axis=1))


# ---------------------------------------------------------------------------
# Year-on-year deltas (inputs to the early-warning rules in watchlist.py)
# ---------------------------------------------------------------------------
def add_yoy(out: pd.DataFrame) -> pd.DataFrame:
    """Compare each quarter with the same quarter a year earlier. Guarded on
    the actual date gap so a company with a missing quarter isn't compared
    against an 18-month-old figure."""
    out = out.copy()
    prior_date = out.groupby("ticker")["period_end_date"].shift(4)
    year_gap = (out["period_end_date"] - prior_date).dt.days
    valid = year_gap.between(330, 400)

    for metric in ["debt_to_ebitda", "operating_margin", "ebitda_ttm",
                   "interest_coverage", "working_capital"]:
        prior = out.groupby("ticker")[metric].shift(4).where(valid)
        out[f"{metric}_yoy_prior"] = prior
        out[f"{metric}_yoy_chg"] = out[metric] - prior
        out[f"{metric}_yoy_pct"] = safe_div(out[metric] - prior, prior.abs())
    return out


def attach_maturity_ladder(conn: sqlite3.Connection, summary: pd.DataFrame) -> pd.DataFrame:
    """Metric 8: the near-term maturity wall from the tagged 10-K ladder.

    A ladder is only used if it is recent enough to describe today's debt and
    complete enough to be a profile rather than a single stray bucket --
    otherwise the refinancing percentage is left blank, which is the honest
    answer, instead of being computed off a stale fragment.
    """
    ladder = pd.read_sql("SELECT ticker, bucket, period_end_date, value FROM debt_maturity", conn)
    if ladder.empty:
        summary["pct_debt_due_within_1y"] = np.nan
        return summary

    wide = ladder.pivot_table(index="ticker", columns="bucket", values="value", aggfunc="last")
    as_of = ladder.groupby("ticker")["period_end_date"].max().rename("maturity_ladder_as_of")
    buckets = [c for c in wide.columns if c.startswith("maturity_")]
    wide["maturity_buckets_tagged"] = wide[buckets].notna().sum(axis=1)
    wide["debt_due_within_1y"] = wide.get("maturity_year_1")
    wide["debt_due_within_3y"] = wide[[c for c in
                                       ["maturity_year_1", "maturity_year_2", "maturity_year_3"]
                                       if c in wide.columns]].sum(axis=1, min_count=1)
    wide["maturity_ladder_total"] = wide[buckets].sum(axis=1, min_count=1)

    summary = summary.merge(wide.join(as_of), on="ticker", how="left")
    ladder_date = pd.to_datetime(summary["maturity_ladder_as_of"])
    age_days = (summary["period_end_date"] - ladder_date).dt.days
    # How well the tagged ladder ties back to balance-sheet debt. A gap means
    # the stack has changed since the disclosure (repayment, new issuance) or
    # that the ladder is face value against a carrying amount net of discount.
    reconciliation = safe_div(summary["maturity_ladder_total"], summary["total_debt"], True)
    summary["maturity_ladder_vs_debt"] = reconciliation

    usable = ((age_days.abs() <= MATURITY_LADDER_MAX_AGE_DAYS)
              & (summary["maturity_buckets_tagged"] >= MATURITY_LADDER_MIN_BUCKETS)
              & (reconciliation - 1).abs().le(MATURITY_LADDER_RECONCILE_TOLERANCE))

    summary["maturity_ladder_usable"] = usable
    summary["pct_debt_due_within_1y"] = safe_div(
        summary["debt_due_within_1y"], summary["maturity_ladder_total"], True).where(usable)
    for col in ("debt_due_within_1y", "debt_due_within_3y", "maturity_ladder_total"):
        summary[col] = summary[col].where(usable)
    return summary


def build_trends(metrics: pd.DataFrame) -> pd.DataFrame:
    """Tidy long-format trend series for the last N quarters -- the shape a
    BI tool or Excel chart wants."""
    recent = metrics.groupby("ticker").tail(TREND_QUARTERS)
    present = [m for m in TREND_METRICS if m in recent.columns]
    tidy = recent.melt(
        id_vars=["ticker", "period_end_date"], value_vars=present,
        var_name="metric", value_name="value")
    return tidy.dropna(subset=["value"]).sort_values(["ticker", "metric", "period_end_date"])


SUMMARY_COLUMNS = [
    "ticker", "company_name", "period_end_date", "fiscal_quarter", "balance_sheet_as_of",
    "revenue_ttm", "ebit_ttm", "ebitda_ttm", "operating_margin",
    "total_debt", "liquid_assets", "net_debt", "total_assets", "total_liabilities_eff",
    "book_equity", "working_capital",
    "debt_to_ebitda", "net_debt_to_ebitda", "interest_coverage", "ebit_interest_coverage",
    "fcf_ttm", "fcf_to_debt", "current_ratio", "quick_ratio",
    "altman_z_double_prime", "altman_z_prime", "altman_zone",
    "covenant_headroom_turns", "ebitda_cushion_pct",
    "debt_due_within_1y", "debt_due_within_3y", "pct_debt_due_within_1y",
    "maturity_ladder_as_of", "maturity_ladder_vs_debt",
    "consecutive_fcf_negative_qtrs",
    "scorecard_score", "scorecard_coverage", "credit_grade", "pd_proxy_band",
    "debt_source", "ebit_source", "interest_basis", "scorecard_missing",
    "debt_to_ebitda_yoy_chg", "operating_margin_yoy_chg", "ebitda_ttm_yoy_pct",
    "interest_coverage_yoy_pct", "working_capital_yoy_pct",
]


def main() -> int:
    if not DB_PATH.exists():
        print(f"{DB_PATH} not found. Run fetch_data.py then build_db.py first.")
        return 1

    conn = sqlite3.connect(DB_PATH)
    panel = load_panel(conn)
    if panel.empty:
        print("No data in database. Run fetch_data.py and build_db.py first.")
        return 1

    names = pd.read_sql("SELECT ticker, company_name FROM companies", conn)
    quarters = pd.read_sql(
        "SELECT DISTINCT ticker, period_end_date, fiscal_year, fiscal_quarter "
        "FROM financials WHERE fiscal_quarter IS NOT NULL", conn)
    quarters["period_end_date"] = pd.to_datetime(quarters["period_end_date"])
    quarters = quarters.drop_duplicates(subset=["ticker", "period_end_date"])

    panel = carry_forward_stocks(panel)
    panel = add_derived_inputs(panel)
    metrics = calc_metrics(panel)
    metrics = add_yoy(metrics)
    metrics = add_scorecard(metrics)
    metrics = metrics.merge(names, on="ticker", how="left").merge(
        quarters, on=["ticker", "period_end_date"], how="left")

    # Latest quarter with a usable set of credit inputs, per company.
    usable = metrics[metrics["ebitda_ttm"].notna() | metrics["current_ratio"].notna()]
    summary = usable.sort_values("period_end_date").groupby("ticker").tail(1).copy()
    summary = attach_maturity_ladder(conn, summary)
    conn.close()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    metrics.to_csv(OUTPUT_DIR / "metrics_all_periods.csv", index=False)
    summary[[c for c in SUMMARY_COLUMNS if c in summary.columns]].sort_values(
        "debt_to_ebitda", ascending=False).to_csv(OUTPUT_DIR / "metrics_summary.csv", index=False)
    build_trends(metrics).to_csv(OUTPUT_DIR / "trends.csv", index=False)

    view = summary.sort_values("scorecard_score", na_position="last")
    print(f"Latest credit metrics ({len(view)} companies)\n")
    display = view[["ticker", "period_end_date", "debt_to_ebitda", "interest_coverage",
                    "fcf_to_debt", "current_ratio", "altman_z_double_prime",
                    "credit_grade", "pd_proxy_band", "scorecard_coverage"]].copy()
    display["period_end_date"] = display["period_end_date"].dt.date
    print(display.to_string(index=False, float_format=lambda v: f"{v:,.2f}", na_rep="n/a"))

    thin = view[view["scorecard_coverage"] < 1.0]
    if not thin.empty:
        print("\nIncomplete scorecards (factors with no extractable data):")
        for _, row in thin.iterrows():
            print(f"  {row['ticker']:5s} coverage {row['scorecard_coverage']:.0%}"
                  f"  missing: {row['scorecard_missing'] or 'none'}")

    print(f"\nSaved metrics_summary.csv, metrics_all_periods.csv, trends.csv -> {OUTPUT_DIR}")
    print("Next: python src/stress_test.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
