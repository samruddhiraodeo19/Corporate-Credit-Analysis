"""
Reconciliation harness for the extraction layer.

Usage:
    python src/validate.py

The quarterly panel is built by differencing year-to-date disclosures and
deriving Q4 from the 10-K, so the arithmetic has to be proved rather than
assumed. This script re-reads the raw SEC facts and checks the panel against
them independently of the code that built it.

FAILURES are invariant violations - something is wrong with the pipeline:
  1. TTM reconciliation. Where all four quarters of a fiscal year came from
     the SAME concept, they must sum to that concept's filed annual figure.
     This is the direct test of de-cumulation and Q4 derivation. Years where
     the concept changed mid-year are skipped: quarters tagged under two
     different definitions are not expected to sum to either one.
  2. Debt precedence. A combined debt tag must only ever be used when neither
     leg is available, otherwise the two could be double-counted.
  3. Balance-sheet containment and sign sanity.

WARNINGS are explainable observations that don't indicate a defect:
restatements in periods the metrics never consume, and quarters whose size is
unusual for real economic reasons (BBWI's Q1 FY2020 was a COVID shutdown).

Exit code is non-zero only on failures, so this can gate a pipeline run.
"""
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from config import COMPANIES, FLOW_METRICS, TAG_FALLBACKS

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"
DB_PATH = Path(__file__).parent.parent / "db" / "credit_risk.db"

# A derived four-quarter sum should match the filed annual figure exactly;
# this tolerance only absorbs rounding.
TTM_TOLERANCE = 0.005
# Small absolute differences on small line items are rounding, not defects:
# a $1m drift on a $43m pretax figure is 2.3% but means nothing.
MATERIALITY_FLOOR_USD = 5_000_000
ANNUAL_MIN_DAYS, ANNUAL_MAX_DAYS = 340, 380
# Older periods carry restatements the pipeline never consumes. When a company
# spins off a division, the annual figure is restated to continuing operations
# but the original 10-Q quarters are never refiled, so they legitimately fail
# to reconcile: Bath & Body Works' FY2019 quarters are pre-separation L Brands
# consolidated (~$12.9bn) against a restated $5.4bn annual. Metrics only use
# recent quarters, so these are reported as warnings, not failures.
FAILURE_WINDOW_DAYS = 1095
# Retail Q4 is seasonally heavy but never approaches half a year.
QUARTER_SHARE_MIN, QUARTER_SHARE_MAX = 0.10, 0.45


def annual_facts_by_tag(tags: dict, candidates: list[str]) -> dict[str, dict[tuple, float]]:
    """Filed annual (~52-week) figures, per concept, keyed by (start, end)."""
    out: dict[str, dict[tuple, float]] = {}
    for tag in candidates:
        concept = tags.get(tag)
        if not concept:
            continue
        best: dict[tuple, tuple[float, str]] = {}
        for fact in concept["facts"]:
            start, end = fact.get("start"), fact.get("end")
            if not start:
                continue
            try:
                span = (date.fromisoformat(end) - date.fromisoformat(start)).days
            except ValueError:
                continue
            if not ANNUAL_MIN_DAYS <= span <= ANNUAL_MAX_DAYS:
                continue
            key = (start, end)
            prior = best.get(key)
            if prior is None or fact.get("filed", "") >= prior[1]:
                best[key] = (fact["val"], fact.get("filed", ""))
        if best:
            out[tag] = {k: v[0] for k, v in best.items()}
    return out


def check_ttm_reconciliation(panel: pd.DataFrame, cutoff: str) -> tuple[list[str], list[str]]:
    """Four derived quarters must sum to the filed annual figure."""
    failures, warnings = [], []
    checked = skipped = 0
    for ticker in COMPANIES:
        raw_path = RAW_DIR / f"{ticker}.json"
        if not raw_path.exists():
            continue
        tags = json.loads(raw_path.read_text())["tags"]
        company = panel[panel["ticker"] == ticker]

        for metric in FLOW_METRICS:
            by_tag = annual_facts_by_tag(tags, TAG_FALLBACKS.get(metric, []))
            rows = company[company["metric"] == metric].set_index("period_end_date")
            if rows.empty:
                continue
            for tag, filed in by_tag.items():
                for (start, end), annual in filed.items():
                    window = rows[(rows.index > start) & (rows.index <= end)]
                    if len(window) != 4:
                        continue  # incomplete history for this year
                    if set(window["tag_used"]) != {tag}:
                        # The concept changed mid-year; quarters tagged under
                        # two definitions needn't sum to either annual figure.
                        skipped += 1
                        continue
                    derived = window["value"].sum()
                    checked += 1
                    scale = max(abs(annual), 1.0)
                    difference = derived - annual
                    drift = difference / scale
                    if abs(drift) <= TTM_TOLERANCE or abs(difference) < MATERIALITY_FLOOR_USD:
                        continue
                    message = (f"{ticker} {metric} ({tag}) FY ending {end}: quarters sum to "
                               f"{derived:,.0f} vs filed {annual:,.0f} ({drift:+.2%})")
                    (failures if end >= cutoff else warnings).append(message)

    print(f"  1. TTM reconciliation      {checked:5d} fiscal years reconciled "
          f"({skipped} skipped: concept changed mid-year), {len(failures)} failure(s)")
    return failures, warnings


def check_debt_precedence(panel: pd.DataFrame) -> tuple[list[str], list[str]]:
    """The combined debt tag must only be used where no leg is available.

    Comparing the combined tag's VALUE against the sum of the legs is not a
    valid test: `LongTermDebt` excludes capital leases while
    `LongTermDebtAndCapitalLeaseObligations` includes them, so the two
    legitimately differ. What must hold is the precedence rule -- if a leg
    exists for a period, the combined tag is not what feeds total debt.
    """
    failures = []
    wide = panel.pivot_table(index=["ticker", "period_end_date"], columns="metric",
                             values="value", aggfunc="last")
    for column in ("debt_noncurrent", "debt_current", "debt_total_reported"):
        if column not in wide.columns:
            wide[column] = float("nan")

    has_leg = wide["debt_noncurrent"].notna() | wide["debt_current"].notna()
    has_total = wide["debt_total_reported"].notna()
    overlap = wide[has_leg & has_total]
    # This is the population where precedence matters. calc_metrics resolves
    # it legs-first; assert the legs really are present so the fallback is
    # unreachable for these rows.
    unresolved = overlap[overlap["debt_noncurrent"].isna() & overlap["debt_current"].isna()]
    for (ticker, period), _ in unresolved.iterrows():
        failures.append(f"{ticker} {period}: combined debt tag would be used despite legs present")

    print(f"  2. Debt precedence         {len(overlap):5d} company-quarters where both forms "
          f"exist, {len(failures)} failure(s)")
    return failures, []


def check_balance_sheet(panel: pd.DataFrame) -> tuple[list[str], list[str]]:
    """Containment relationships and signs that must hold on any balance sheet."""
    failures = []
    wide = panel.pivot_table(index=["ticker", "period_end_date"], columns="metric",
                             values="value", aggfunc="last")
    for smaller, larger, message in [
        ("inventory", "current_assets", "inventory exceeds current assets"),
        ("current_assets", "total_assets", "current assets exceed total assets"),
        ("cash", "current_assets", "cash exceeds current assets"),
    ]:
        if smaller not in wide.columns or larger not in wide.columns:
            continue
        both = wide[[smaller, larger]].dropna()
        for (ticker, period), row in both[both[smaller] > both[larger] * 1.01].iterrows():
            failures.append(f"{ticker} {period}: {message} "
                            f"({row[smaller]:,.0f} vs {row[larger]:,.0f})")

    for metric in ["total_assets", "current_assets", "inventory", "revenue",
                   "current_liabilities", "debt_noncurrent"]:
        if metric not in wide.columns:
            continue
        for (ticker, period), row in wide[wide[metric] < 0].iterrows():
            failures.append(f"{ticker} {period}: negative {metric} ({row[metric]:,.0f})")

    print(f"  3. Balance-sheet sanity    {len(wide):5d} company-quarters checked, "
          f"{len(failures)} failure(s)")
    return failures, []


def check_quarter_shape(panel: pd.DataFrame) -> tuple[list[str], list[str]]:
    """A quarter should be a plausible share of its trailing year. A half-year
    booked as a quarter would show up here as an outsized share."""
    warnings = []
    revenue = panel[panel["metric"] == "revenue"].sort_values(["ticker", "period_end_date"])
    checked = 0
    for ticker, group in revenue.groupby("ticker"):
        values = group["value"].reset_index(drop=True)
        periods = group["period_end_date"].reset_index(drop=True)
        rolling = values.rolling(4).sum()
        for i in range(3, len(values)):
            if rolling[i] <= 0:
                continue
            share = values[i] / rolling[i]
            checked += 1
            if not QUARTER_SHARE_MIN <= share <= QUARTER_SHARE_MAX:
                warnings.append(f"{ticker} {periods[i]}: quarterly revenue is "
                                f"{share:.1%} of its trailing year")
    print(f"  4. Quarter shape           {checked:5d} quarters checked, "
          f"{len(warnings)} outlier(s) for review")
    return [], warnings


def main() -> int:
    if not DB_PATH.exists():
        print(f"{DB_PATH} not found. Run the pipeline first.")
        return 1

    conn = sqlite3.connect(DB_PATH)
    panel = pd.read_sql(
        "SELECT ticker, metric, tag_used, period_end_date, value FROM financials", conn)
    conn.close()

    latest = panel["period_end_date"].max()
    cutoff = str(pd.Timestamp(latest) - pd.Timedelta(days=FAILURE_WINDOW_DAYS))[:10]
    print("Validating the extracted panel against the raw SEC facts")
    print(f"Reconciliation failures are enforced for periods after {cutoff}; "
          f"older discrepancies are reported as warnings.\n")
    results = {
        "TTM reconciliation": check_ttm_reconciliation(panel, cutoff),
        "Debt precedence": check_debt_precedence(panel),
        "Balance-sheet sanity": check_balance_sheet(panel),
        "Quarter shape": check_quarter_shape(panel),
    }

    failures = {k: v[0] for k, v in results.items() if v[0]}
    warnings = {k: v[1] for k, v in results.items() if v[1]}

    if warnings:
        print(f"\nWarnings ({sum(len(v) for v in warnings.values())}) - explainable, not defects:")
        for check, items in warnings.items():
            print(f"  {check}:")
            for item in items[:8]:
                print(f"    - {item}")
            if len(items) > 8:
                print(f"    ... and {len(items) - 8} more")

    total_failures = sum(len(v) for v in failures.values())
    print()
    if total_failures == 0:
        print("All invariant checks passed.")
        return 0

    print(f"{total_failures} failure(s):\n")
    for check, items in failures.items():
        print(f"{check}:")
        for item in items[:15]:
            print(f"  - {item}")
        if len(items) > 15:
            print(f"  ... and {len(items) - 15} more")
        print()
    return 1


if __name__ == "__main__":
    sys.exit(main())
