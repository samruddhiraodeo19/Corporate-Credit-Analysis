"""
Runs the full pipeline end to end.

Usage:
    python src/run_pipeline.py             # use cached SEC pulls
    python src/run_pipeline.py --refresh   # re-pull everything from SEC first

Stages:
    fetch_data    pull raw XBRL facts from SEC EDGAR (cached in data/raw/)
    build_db      reshape into a clean quarterly panel in SQLite
    validate      reconcile the panel back to the raw filings
    calc_metrics  compute the credit metric suite
    stress_test   run the baseline plus six stress scenarios
    watchlist     apply level, trend and stress triggers
    build_excel   assemble the Excel underwriting model
    build_powerbi export the star-schema dataset + DAX for Power BI
    build_dashboard render the same three pages as a viewable HTML dashboard
    build_memo    generate a credit memo for each watchlist name
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

SRC_DIR = Path(__file__).parent
STEPS = [
    ("fetch_data.py", "Pulling filings from SEC EDGAR"),
    ("build_db.py", "Normalising into a quarterly panel"),
    ("validate.py", "Reconciling the panel against raw filings"),
    ("calc_metrics.py", "Calculating credit metrics"),
    ("stress_test.py", "Running stress scenarios"),
    ("watchlist.py", "Applying watchlist triggers"),
    ("build_excel.py", "Building the Excel underwriting model"),
    ("build_powerbi.py", "Exporting the Power BI dataset"),
    ("build_dashboard.py", "Rendering the HTML dashboard"),
    ("build_memo.py", "Writing the credit memos"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true",
                        help="force a fresh pull from SEC instead of using data/raw/ cache")
    args = parser.parse_args()

    started = time.time()
    for index, (step, description) in enumerate(STEPS, start=1):
        print(f"\n{'=' * 70}\n[{index}/{len(STEPS)}] {description}  ({step})\n{'=' * 70}")
        command = [sys.executable, str(SRC_DIR / step)]
        if step == "fetch_data.py" and args.refresh:
            command.append("--refresh")
        if step == "build_memo.py":
            # A full run covers the whole watchlist; the bare script defaults
            # to a single name for interactive use.
            command.append("--all")
        result = subprocess.run(command)
        if result.returncode != 0:
            print(f"\n{step} failed (exit code {result.returncode}). Stopping.")
            return result.returncode

    elapsed = time.time() - started
    print(f"\n{'=' * 70}")
    print(f"Pipeline complete in {elapsed:.0f}s. Deliverables in output/:")
    print("  credit_underwriting_model.xlsx  the Excel model (start here)")
    print("  memos/                          credit memo per watchlist name")
    print("  dashboard.html                  interactive dashboard (open in a browser)")
    print("  powerbi/                        star-schema dataset, DAX, build guide")
    print("  watchlist.csv                   flagged names and why")
    print("  metrics_summary.csv             latest metrics per company")
    print("  metrics_all_periods.csv         full quarterly history")
    print("  stress_test_results.csv         every company x scenario")
    print("  trends.csv                      8-quarter series for BI tools")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
