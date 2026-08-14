"""
Pulls real financial data from SEC EDGAR's XBRL API.

Usage:
    python src/fetch_data.py            # use cached pulls where they exist
    python src/fetch_data.py --refresh  # force a re-pull for every company

Uses the `companyfacts` endpoint (one request per company returning every
tagged concept) rather than `companyconcept` (one request per tag). That is
~20x fewer requests, and -- more importantly -- it lets the tag-selection
logic see every concept the company has ever reported, so build_db.py can
coalesce across taxonomy changes instead of guessing a tag up front.

Responses are trimmed to the concepts this project actually uses before
caching, so data/raw/ stays small (~100KB/company instead of ~4MB).
"""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from config import (
    COMPANIES,
    MATURITY_TAGS,
    SEC_REQUEST_DELAY_SEC,
    SEC_USER_AGENT,
    TAG_FALLBACKS,
    USER_AGENT_IS_PLACEHOLDER,
)

HEADERS = {"User-Agent": SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"}
RAW_DIR = Path(__file__).parent.parent / "data" / "raw"
TICKER_MAP_PATH = RAW_DIR / "company_tickers.json"
TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

# Every us-gaap concept this project can consume, across all metrics.
WANTED_TAGS = {tag for tags in TAG_FALLBACKS.values() for tag in tags}
WANTED_TAGS |= {tag for tags in MATURITY_TAGS.values() for tag in tags}


def _get(url: str) -> requests.Response:
    """GET with SEC's required headers and rate-limit courtesy delay."""
    resp = requests.get(url, headers=HEADERS, timeout=60)
    time.sleep(SEC_REQUEST_DELAY_SEC)
    return resp


def get_ticker_cik_map(refresh: bool = False) -> dict[str, tuple[str, str]]:
    """Download (or load cached) SEC ticker -> (padded CIK, company name) map."""
    if TICKER_MAP_PATH.exists() and not refresh:
        data = json.loads(TICKER_MAP_PATH.read_text())
    else:
        resp = _get(TICKER_MAP_URL)
        resp.raise_for_status()
        data = resp.json()
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        TICKER_MAP_PATH.write_text(json.dumps(data))
    # {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...}
    return {v["ticker"]: (str(v["cik_str"]).zfill(10), v["title"]) for v in data.values()}


def trim_facts(payload: dict) -> dict:
    """Keep only the us-gaap concepts this project uses, and only their USD
    units. Everything else in companyfacts (shares, per-share, dei, hundreds
    of unused tags) is dropped before caching."""
    us_gaap = payload.get("facts", {}).get("us-gaap", {})
    kept = {}
    for tag in WANTED_TAGS:
        concept = us_gaap.get(tag)
        if not concept:
            continue
        usd = concept.get("units", {}).get("USD")
        if not usd:
            continue
        kept[tag] = {"label": concept.get("label"), "facts": usd}
    return kept


def fetch_company(ticker: str, cik: str, name: str) -> dict:
    """Fetch and trim all usable facts for one company."""
    resp = _get(COMPANYFACTS_URL.format(cik=cik))
    if resp.status_code == 404:
        raise RuntimeError(f"SEC has no companyfacts for {ticker} (CIK {cik})")
    resp.raise_for_status()
    tags = trim_facts(resp.json())

    fact_count = sum(len(v["facts"]) for v in tags.values())
    print(f"  {ticker}: {len(tags)} concepts, {fact_count:,} facts")

    missing = [m for m, cands in TAG_FALLBACKS.items() if not any(c in tags for c in cands)]
    if missing:
        print(f"  {ticker}: NO TAG FOUND for -> {', '.join(missing)}")

    return {
        "ticker": ticker,
        "cik": cik,
        "company_name": name,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tags": tags,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true",
                        help="re-pull every company even if a cached file exists")
    args = parser.parse_args()

    if USER_AGENT_IS_PLACEHOLDER:
        # Fail fast and loudly: SEC blocks requests without real contact
        # details, and a 403 halfway through a run is a confusing way to
        # discover that.
        print("ERROR: SEC_USER_AGENT is still the placeholder.\n"
              "SEC requires real contact information on every request. Set it with:\n"
              '  export SEC_USER_AGENT="Your Name your.email@example.com"\n'
              "or write that same string to a .sec_user_agent file in the project root.")
        return 1

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    ticker_map = get_ticker_cik_map(refresh=args.refresh)

    unresolved = [t for t in COMPANIES if t not in ticker_map]
    if unresolved:
        # A ticker that no longer resolves means the company was acquired,
        # went private, or was renamed. Silently skipping it (as an earlier
        # version did) quietly shrinks the coverage universe.
        print(f"ERROR: these tickers are not in SEC's ticker file: {', '.join(unresolved)}")
        print("They were likely delisted, renamed, or acquired. Fix COMPANIES in config.py.")
        return 1

    fetched = skipped = 0
    for ticker in COMPANIES:
        cik, name = ticker_map[ticker]
        out_path = RAW_DIR / f"{ticker}.json"

        if out_path.exists() and not args.refresh:
            print(f"{ticker}: cached, skipping (--refresh to re-pull)")
            skipped += 1
            continue

        print(f"Fetching {ticker} - {name} (CIK {cik})")
        try:
            payload = fetch_company(ticker, cik, name)
        except (requests.RequestException, RuntimeError) as exc:
            print(f"  ERROR fetching {ticker}: {exc}")
            return 1
        out_path.write_text(json.dumps(payload))
        fetched += 1

    print(f"\nDone. {fetched} fetched, {skipped} from cache -> {RAW_DIR}")
    print("Next: python src/build_db.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
