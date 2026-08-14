"""
Reshapes the raw SEC facts into a clean quarterly panel and loads it into
SQLite.

Usage:
    python src/build_db.py

This is where most of the real-world messiness in SEC data gets handled:

1. INSTANT vs DURATION facts. Balance-sheet concepts are point-in-time
   (no `start`); income-statement and cash-flow concepts cover a period.
   They cannot be treated the same way.

2. YEAR-TO-DATE cash flows. Retailers report cash-flow statements
   cumulatively from the fiscal-year start, so a Q3 10-Q's operating cash
   flow covers ~39 weeks, not 13. Filtering to "facts about 90 days long"
   -- which an earlier version of this pipeline did -- throws away three
   quarters of every year. Instead, facts sharing a `start` are sorted by
   `end` and differenced, which recovers the discrete quarter.

3. NO DISCRETE Q4. 10-Ks report the full year only. Q4 falls out of the
   same differencing step: FY total minus the 9-month year-to-date figure.

4. RESTATEMENTS. The same period is often reported twice (once in the
   10-Q, again restated in the next 10-K). The most recently FILED value
   for a period wins.

5. TAXONOMY DRIFT. The concept a company uses changes over time (Target
   left `Revenues` in FY2015). Metrics are coalesced across their candidate
   tags period-by-period rather than by picking one tag up front.
"""
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

from config import (
    COMPANIES,
    FLOW_METRICS,
    MATURITY_TAGS,
    QUARTER_MAX_DAYS,
    QUARTER_MIN_DAYS,
    TAG_FALLBACKS,
)

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"
DB_PATH = Path(__file__).parent.parent / "db" / "credit_risk.db"

SCHEMA = """
DROP TABLE IF EXISTS companies;
DROP TABLE IF EXISTS financials;
DROP TABLE IF EXISTS debt_maturity;
DROP TABLE IF EXISTS data_quality;

CREATE TABLE companies (
    ticker        TEXT PRIMARY KEY,
    cik           TEXT,
    company_name  TEXT,
    fetched_at    TEXT
);

-- One row per company / period / metric. Long format so new metrics never
-- require a schema change.
CREATE TABLE financials (
    ticker            TEXT NOT NULL,
    metric            TEXT NOT NULL,
    tag_used          TEXT,
    fact_type         TEXT,     -- 'instant' (stock) or 'duration' (flow)
    fiscal_year       INTEGER,
    fiscal_quarter    TEXT,     -- Q1..Q4
    period_start_date TEXT,     -- NULL for instant facts
    period_end_date   TEXT NOT NULL,
    form              TEXT,     -- 10-Q / 10-K the value came from
    filed_date        TEXT,
    is_derived        INTEGER,  -- 1 = de-cumulated from a year-to-date fact
    value             REAL,
    PRIMARY KEY (ticker, metric, period_end_date)
);

CREATE INDEX idx_fin_ticker_period ON financials (ticker, period_end_date);

-- Metric 8: contractual debt maturity ladder, as tagged in the latest 10-K.
CREATE TABLE debt_maturity (
    ticker          TEXT,
    bucket          TEXT,
    period_end_date TEXT,
    filed_date      TEXT,
    value           REAL
);

-- Per company/metric extraction audit: which tag won, how much history it
-- covers, how stale it is. "No data" must be visibly different from "zero".
CREATE TABLE data_quality (
    ticker         TEXT,
    metric         TEXT,
    tags_used      TEXT,
    quarters_found INTEGER,
    first_period   TEXT,
    last_period    TEXT,
    derived_share  REAL
);
"""


def _dedupe_by_filing(facts: list[dict]) -> dict[tuple, dict]:
    """Collapse restatements: keep the most recently filed value for each
    (start, end) period. Ties break on accession number so the result is
    deterministic."""
    best: dict[tuple, dict] = {}
    for f in facts:
        key = (f.get("start"), f["end"])
        prior = best.get(key)
        stamp = (f.get("filed", ""), f.get("accn", ""))
        if prior is None or stamp > (prior.get("filed", ""), prior.get("accn", "")):
            best[key] = f
    return best


def _days(start: str, end: str) -> int | None:
    try:
        return (date.fromisoformat(end) - date.fromisoformat(start)).days
    except (ValueError, TypeError):
        return None


def _is_quarterly(days: int | None) -> bool:
    return days is not None and QUARTER_MIN_DAYS <= days <= QUARTER_MAX_DAYS


def extract_duration_quarters(facts: list[dict]) -> dict[str, dict]:
    """Turn one concept's duration facts into discrete quarterly observations
    keyed by period end date.

    Natively-reported 13-week facts are used as-is. Everything else is
    recovered by differencing year-to-date facts that share a `start`:
    a 26-week fact minus the 13-week fact with the same start is Q2, and the
    52-week 10-K fact minus the 39-week fact is Q4.
    """
    deduped = _dedupe_by_filing(facts)

    native: dict[str, dict] = {}
    by_start: dict[str, list[dict]] = defaultdict(list)
    for (start, end), fact in deduped.items():
        if start is None:
            continue  # instant fact; handled elsewhere
        span = _days(start, end)
        if span is None:
            continue
        if _is_quarterly(span):
            native[end] = {
                "value": fact["val"],
                "start": start,
                "end": end,
                "fy": fact.get("fy"),
                "fp": fact.get("fp"),
                "form": fact.get("form"),
                "filed": fact.get("filed"),
                "derived": False,
            }
        by_start[start].append(fact)

    derived: dict[str, dict] = {}
    for start, group in by_start.items():
        group.sort(key=lambda f: f["end"])
        prev_end, prev_val = start, 0.0
        for idx, fact in enumerate(group):
            span = _days(prev_end, fact["end"])
            step_value = fact["val"] - prev_val
            # Only the differences that land on a ~13-week window are real
            # quarters. A gap (e.g. a missing Q2 year-to-date fact) produces
            # a 26-week difference, which is correctly discarded here rather
            # than silently booked as one quarter.
            if _is_quarterly(span) and fact["end"] not in derived:
                derived[fact["end"]] = {
                    "value": step_value,
                    "start": prev_end,
                    "end": fact["end"],
                    "fy": fact.get("fy"),
                    "fp": fact.get("fp") if idx == 0 else f"Q{idx + 1}",
                    "form": fact.get("form"),
                    "filed": fact.get("filed"),
                    "derived": idx > 0,
                }
            prev_end, prev_val = fact["end"], fact["val"]

    # Native 13-week disclosures beat anything reconstructed by subtraction.
    return {**derived, **native}


def extract_instants(facts: list[dict]) -> dict[str, dict]:
    """Balance-sheet concepts: one value per date, latest filing wins."""
    out: dict[str, dict] = {}
    for (start, end), fact in _dedupe_by_filing(facts).items():
        if start is not None:
            continue
        out[end] = {
            "value": fact["val"],
            "start": None,
            "end": end,
            "fy": fact.get("fy"),
            "fp": fact.get("fp"),
            "form": fact.get("form"),
            "filed": fact.get("filed"),
            "derived": False,
        }
    return out


def _quarter_label(obs: dict) -> str | None:
    fp = obs.get("fp")
    if fp in ("Q1", "Q2", "Q3", "Q4"):
        return fp
    if fp == "FY":
        return "Q4"
    return None


def coalesce_metric(tags: dict, candidates: list[str], is_flow: bool) -> tuple[dict, list[str]]:
    """Merge a metric's candidate concepts into one series.

    Earlier candidates win for any period where several report a value, but
    a later candidate still fills periods the preferred one doesn't cover.
    This is what makes the series survive a mid-history taxonomy change
    instead of going flat the day a company retires a tag.
    """
    series: dict[str, dict] = {}
    used: list[str] = []
    for tag in candidates:
        concept = tags.get(tag)
        if not concept:
            continue
        obs = (extract_duration_quarters if is_flow else extract_instants)(concept["facts"])
        added = 0
        for end, record in obs.items():
            if end not in series:
                series[end] = {**record, "tag": tag}
                added += 1
        if added:
            used.append(tag)
    return series, used


def extract_maturity_ladder(tags: dict) -> list[dict]:
    """Metric 8: the five-year debt maturity ladder as disclosed in the most
    recent 10-K that tagged it.

    Every bucket must come from the SAME balance-sheet date. Taking each
    bucket's own latest value independently silently splices filings years
    apart: Kohl's only ever tagged a next-twelve-months figure, back in 2011,
    which then reads as "100% of debt due within a year".
    """
    # The ladder is disclosed as of one date; find the newest such date.
    dates = {fact["end"]
             for candidates in MATURITY_TAGS.values()
             for tag in candidates if tag in tags
             for fact in tags[tag]["facts"]}
    if not dates:
        return []
    as_of = max(dates)

    rows = []
    for bucket, candidates in MATURITY_TAGS.items():
        for tag in candidates:
            concept = tags.get(tag)
            if not concept:
                continue
            matches = [f for f in concept["facts"] if f["end"] == as_of]
            if not matches:
                continue
            best = max(matches, key=lambda f: (f.get("filed", ""), f.get("accn", "")))
            rows.append({
                "bucket": bucket,
                "period_end_date": as_of,
                "filed_date": best.get("filed"),
                "value": best["val"],
            })
            break
    return rows


def main() -> int:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)

    total_rows = 0
    loaded = 0
    for ticker in COMPANIES:
        raw_path = RAW_DIR / f"{ticker}.json"
        if not raw_path.exists():
            print(f"WARNING: no raw data for {ticker}; run fetch_data.py first")
            continue

        payload = json.loads(raw_path.read_text())
        tags = payload["tags"]
        conn.execute(
            "INSERT INTO companies VALUES (?, ?, ?, ?)",
            (ticker, payload["cik"], payload["company_name"], payload["fetched_at"]),
        )

        for metric, candidates in TAG_FALLBACKS.items():
            is_flow = metric in FLOW_METRICS
            series, used = coalesce_metric(tags, candidates, is_flow)
            if not series:
                conn.execute(
                    "INSERT INTO data_quality VALUES (?, ?, ?, 0, NULL, NULL, NULL)",
                    (ticker, metric, ""),
                )
                continue

            rows = [
                (
                    ticker, metric, rec["tag"],
                    "duration" if is_flow else "instant",
                    rec.get("fy"), _quarter_label(rec),
                    rec.get("start"), end,
                    rec.get("form"), rec.get("filed"),
                    int(rec["derived"]), rec["value"],
                )
                for end, rec in sorted(series.items())
            ]
            conn.executemany(
                "INSERT OR REPLACE INTO financials VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows
            )
            total_rows += len(rows)

            ends = sorted(series)
            derived_share = sum(r["derived"] for r in series.values()) / len(series)
            conn.execute(
                "INSERT INTO data_quality VALUES (?,?,?,?,?,?,?)",
                (ticker, metric, ",".join(used), len(series), ends[0], ends[-1],
                 round(derived_share, 3)),
            )

        for row in extract_maturity_ladder(tags):
            conn.execute(
                "INSERT INTO debt_maturity VALUES (?,?,?,?,?)",
                (ticker, row["bucket"], row["period_end_date"], row["filed_date"], row["value"]),
            )

        gaps = [m for m, c in TAG_FALLBACKS.items()
                if not conn.execute(
                    "SELECT 1 FROM financials WHERE ticker=? AND metric=? LIMIT 1",
                    (ticker, m)).fetchone()]
        note = f"  no data: {', '.join(gaps)}" if gaps else "  all metrics present"
        print(f"{ticker:5s} loaded{note}")
        loaded += 1

    conn.commit()

    # Coverage report: the most recent quarter each company has a full set of
    # inputs for. A metric missing here becomes a NaN downstream, never a zero.
    print(f"\nLoaded {total_rows:,} facts for {loaded} companies -> {DB_PATH}")
    stale = conn.execute("""
        SELECT ticker, metric, last_period FROM data_quality
        WHERE quarters_found > 0
          AND last_period < (SELECT MAX(last_period) FROM data_quality)
        ORDER BY last_period
    """).fetchall()
    stale = [s for s in stale if s[2] < "2025-01-01"]
    if stale:
        print("\nStale concepts (last reported before 2025 -- excluded from current metrics):")
        for ticker, metric, last in stale:
            print(f"  {ticker:5s} {metric:26s} last reported {last}")

    conn.close()
    print("\nNext: python src/calc_metrics.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
