"""
Central configuration for the credit-risk system.

Everything a reviewer might ask "why that number?" about lives here as a
named constant, not buried in an if-statement downstream.
"""

# ---------------------------------------------------------------------------
# Coverage universe
# ---------------------------------------------------------------------------
# US retail / consumer-discretionary issuers. Deliberately mixes clearly-strong
# balance sheets (TJX, ROST, BURL) with clearly-stressed ones (KSS, M, BBWI, W)
# so the watchlist has real dispersion instead of 12 similar names.
#
# Banks/insurers are excluded on purpose: standard credit ratios don't mean
# what the textbook says on a financial-institution balance sheet.
#
# CIKs are resolved at runtime from SEC's company_tickers.json, so only the
# ticker needs to be right. Tickers that no longer resolve are a hard error,
# not a silent skip (JWN/GPS/FL were silently dropped by an earlier version).
COMPANIES = [
    "TGT",    # Target
    "TJX",    # TJX Companies
    "ROST",   # Ross Stores
    "BURL",   # Burlington Stores
    "DKS",    # Dick's Sporting Goods
    "BBY",    # Best Buy
    "GAP",    # Gap Inc. (ticker changed from GPS)
    "ANF",    # Abercrombie & Fitch
    "KSS",    # Kohl's
    "M",      # Macy's
    "BBWI",   # Bath & Body Works
    "W",      # Wayfair
]

# Business context for the credit memo. This is ANALYST-SUPPLIED, not derived
# from filings -- a memo needs to say what the company does and where its
# credit risk actually comes from, and no ratio carries that. Deliberately
# qualitative: anything countable (revenue, leverage, store economics) is
# pulled from the data instead, so nothing here can go stale and contradict
# the numbers next to it.
COMPANY_PROFILES = {
    "TGT": "A national mass merchant selling general merchandise and food through "
           "owned and leased large-format stores, with a growing same-day fulfilment "
           "business. Scale and an investment-grade balance sheet are the credit "
           "strengths; discretionary-heavy mix is the cyclical exposure.",
    "TJX": "The largest off-price apparel and home-fashion retailer, buying "
           "opportunistically and selling below department-store prices. Off-price "
           "tends to gain share when consumers trade down, which makes the model "
           "counter-cyclical relative to the rest of the sector.",
    "ROST": "An off-price apparel and home retailer operating domestically under "
            "Ross Dress for Less and dd's DISCOUNTS. Similar counter-cyclical "
            "characteristics to TJX, with a narrower, US-only footprint.",
    "BURL": "An off-price retailer pursuing an aggressive store-opening programme. "
            "The growth strategy is capital-hungry, so free cash flow is thinner "
            "than at the more mature off-price names despite similar margins.",
    "DKS": "The largest US sporting-goods retailer, recently enlarged by a major "
           "acquisition that materially changed the earnings and debt profile. "
           "Integration execution is the dominant near-term credit variable.",
    "BBY": "A consumer-electronics retailer whose demand is tied to product "
           "replacement cycles and big-ticket discretionary spending. Carries very "
           "little funded debt, but the category is structurally competitive and "
           "exposed to online price transparency.",
    "GAP": "A specialty apparel retailer operating a portfolio of brands across "
           "price points. Credit quality rests on brand relevance, which is harder "
           "to underwrite than a balance sheet and can turn quickly.",
    "ANF": "A specialty apparel retailer that completed a turnaround and repaid its "
           "funded debt. Debt-free today, but apparel demand is fashion-driven and "
           "the earnings base is small relative to the rest of the portfolio.",
    "KSS": "A mid-tier, largely off-mall department store. Faces the structural "
           "pressures of the department-store channel; owns a substantial share of "
           "its real estate, which supports recovery values.",
    "M": "A department-store operator across mainline, luxury and beauty banners, "
         "with a significant owned real-estate portfolio. The retail business is in "
         "secular decline; asset value is a meaningful part of the credit story.",
    "BBWI": "A specialty retailer of personal care and home fragrance, separated "
            "from its former parent in 2021. High margins and strong cash "
            "conversion, but the separation left it with a leveraged capital "
            "structure and negative book equity.",
    "W": "An online retailer of furniture and home goods, operating an asset-light "
         "drop-ship model. Long loss-making and only recently approaching "
         "profitability; the capital structure includes convertible notes and book "
         "equity is deeply negative.",
}

# SEC requires a descriptive User-Agent with real contact information on every
# request; without one, data.sec.gov returns 403.
#
# It is resolved at runtime rather than committed, so a public repository never
# carries a personal email address. In order of precedence:
#   1. the SEC_USER_AGENT environment variable
#   2. a `.sec_user_agent` file in the project root (gitignored)
#   3. the placeholder below, which SEC may reject
PLACEHOLDER_USER_AGENT = "Your Name your.email@example.com"


def _resolve_user_agent() -> str:
    from os import environ
    from pathlib import Path

    from_env = environ.get("SEC_USER_AGENT", "").strip()
    if from_env:
        return from_env
    local_file = Path(__file__).parent.parent / ".sec_user_agent"
    if local_file.exists():
        from_file = local_file.read_text().strip()
        if from_file:
            return from_file
    return PLACEHOLDER_USER_AGENT


SEC_USER_AGENT = _resolve_user_agent()
USER_AGENT_IS_PLACEHOLDER = SEC_USER_AGENT == PLACEHOLDER_USER_AGENT

# SEC's published fair-access limit is 10 requests/second. One request per
# company (companyfacts returns every tag at once) keeps us far below it.
SEC_REQUEST_DELAY_SEC = 0.15

# ---------------------------------------------------------------------------
# XBRL concept mapping
# ---------------------------------------------------------------------------
# Companies do not tag the same economics with the same concept, and the tag
# they use CHANGES OVER TIME as the US-GAAP taxonomy evolves. Target, for
# example, stopped tagging `Revenues` in FY2015 and moved to
# `RevenueFromContractWithCustomerExcludingAssessedTax`, and stopped tagging
# `LongTermDebtNoncurrent` in FY2013 in favour of
# `LongTermDebtAndCapitalLeaseObligations`.
#
# So these lists are NOT "pick the first tag that has any data" (that locks
# onto a dead tag and silently produces NaN/zero for the modern periods).
# build_db.py COALESCES them period-by-period: for each fiscal quarter it
# takes the first tag in this list that reports a value for that quarter.
# Order therefore means "preferred definition", not "try first".
TAG_FALLBACKS = {
    # --- Income statement (duration facts) ---
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
    ],
    "operating_income": [
        "OperatingIncomeLoss",
    ],
    # Not every registrant tags an operating-income subtotal at all (Burlington
    # doesn't). Where it's absent, calc_metrics rebuilds EBIT bottom-up as
    # pretax income + interest expense - interest income.
    "pretax_income": [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ],
    # GROSS interest expense (the rating-agency convention for coverage).
    # Sign convention: positive = expense.
    "interest_expense": [
        "InterestExpenseNonoperating",
        "InterestExpense",
        "InterestAndDebtExpense",
        "InterestExpenseDebt",
        "FinancingInterestExpense",
    ],
    "interest_income": [
        "InvestmentIncomeInterest",
        "InterestIncomeOther",
    ],
    # NET interest, where positive = net INCOME (opposite sign to the above,
    # which is why it is a separate metric rather than another fallback).
    # Macy's stopped disclosing gross interest quarterly in FY2023 and now
    # reports only this; calc_metrics uses it as a documented fallback and
    # labels the affected coverage ratios as net-basis.
    "net_interest_income": [
        "InterestIncomeExpenseNonoperatingNet",
        "InterestRevenueExpenseNet",   # TJX reports gross interest annually only
        "InterestIncomeExpenseNet",
    ],
    # --- Cash flow (duration facts, usually reported YEAR-TO-DATE) ---
    "depreciation_amortization": [
        "DepreciationDepletionAndAmortization",
        "DepreciationAmortizationAndAccretionNet",
        "DepreciationAndAmortization",
        "Depreciation",
    ],
    "operating_cash_flow": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
        "PaymentsForCapitalImprovements",
    ],
    # --- Balance sheet (instant facts) ---
    "cash": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ],
    "short_term_investments": [
        "ShortTermInvestments",
        "OtherShortTermInvestments",
        "AvailableForSaleSecuritiesDebtSecuritiesCurrent",
    ],
    "current_assets": ["AssetsCurrent"],
    "current_liabilities": ["LiabilitiesCurrent"],
    "inventory": [
        "InventoryNet",
        "InventoryFinishedGoodsNetOfReserves",   # Gap tags inventory this way
        "InventoryFinishedGoods",
        "RetailRelatedInventoryMerchandise",
    ],
    "total_assets": ["Assets"],
    # Most retailers never tag the `Liabilities` subtotal -- only 1 of 12 names
    # here does. calc_metrics falls back to Total Assets - Total Equity.
    "total_liabilities": ["Liabilities"],
    "retained_earnings": ["RetainedEarningsAccumulatedDeficit"],
    "stockholders_equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    # Preferred the other way round: for the Total Assets - Total Equity
    # identity to hold, equity must include any noncontrolling interest.
    "total_equity_incl_nci": [
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        "StockholdersEquity",
    ],
    # Debt is split into current/noncurrent legs and summed in calc_metrics.
    # The "AndCapitalLeaseObligations" variants already include finance-lease
    # obligations; see DEBT_INCLUDES_FINANCE_LEASES note in the README.
    "debt_noncurrent": [
        "LongTermDebtAndCapitalLeaseObligations",
        "LongTermDebtNoncurrent",
        "UnsecuredLongTermDebtNoncurrent",
        "SecuredLongTermDebt",
    ],
    "debt_current": [
        "LongTermDebtAndCapitalLeaseObligationsCurrent",
        "LongTermDebtCurrent",
        "DebtCurrent",
    ],
    "short_term_borrowings": [
        "ShortTermBorrowings",
        "OtherShortTermBorrowings",
        "CommercialPaper",
    ],
    # Some registrants report only a combined debt figure and no current /
    # noncurrent split (Dick's moved to `UnsecuredDebt` in FY2019). Used ONLY
    # when neither leg is available for a period, so it can't double-count.
    "debt_total_reported": [
        "DebtLongtermAndShorttermCombinedAmount",
        "LongTermDebt",
        "DebtAndCapitalLeaseObligations",
        "UnsecuredDebt",
    ],
    "finance_lease_noncurrent": ["FinanceLeaseLiabilityNoncurrent"],
    "finance_lease_current": ["FinanceLeaseLiabilityCurrent"],
    "operating_lease_liability": [
        "OperatingLeaseLiabilityNoncurrent",
    ],
}

# Metric 8 (debt maturity profile). The PLAN assumed this needed manual
# reading of the 10-K footnote; in practice most registrants DO tag the
# five-year maturity ladder, so it is pulled straight from XBRL where
# available and left blank (not zero) where it isn't.
MATURITY_TAGS = {
    "maturity_year_1": ["LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths"],
    "maturity_year_2": ["LongTermDebtMaturitiesRepaymentsOfPrincipalInYearTwo"],
    "maturity_year_3": ["LongTermDebtMaturitiesRepaymentsOfPrincipalInYearThree"],
    "maturity_year_4": ["LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFour"],
    "maturity_year_5": ["LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFive"],
    "maturity_thereafter": ["LongTermDebtMaturitiesRepaymentsOfPrincipalAfterYearFive"],
}

# Which metrics are stocks (balance-sheet, point-in-time) vs flows (income /
# cash-flow, accumulate over a period). Flows get TTM-summed; stocks never do.
FLOW_METRICS = [
    "revenue", "operating_income", "pretax_income", "interest_expense",
    "interest_income", "net_interest_income", "depreciation_amortization",
    "operating_cash_flow", "capex",
]

# ---------------------------------------------------------------------------
# Period-derivation tolerances
# ---------------------------------------------------------------------------
# A retail "quarter" is 13 weeks (91 days), but 53-week fiscal years produce
# one 14-week (98-day) quarter, and fiscal calendars drift a few days.
QUARTER_MIN_DAYS = 80
QUARTER_MAX_DAYS = 100
# How many trailing quarters to keep in the trend outputs.
TREND_QUARTERS = 8
# A maturity ladder older than this is a historical artefact, not a current
# refinancing profile, and is discarded rather than reported. Kohl's last
# tagged a maturity bucket in 2011; read literally it implied 100% of today's
# debt matures within a year.
MATURITY_LADDER_MAX_AGE_DAYS = 550
# The ladder must also cover enough of the balance sheet to be meaningful:
# a single tagged bucket is not a maturity profile.
MATURITY_LADDER_MIN_BUCKETS = 3
# ...and it must still describe the CURRENT debt stack. The ladder is a
# year-end disclosure; if the company has since repaid or issued, its buckets
# no longer sum to the debt on today's balance sheet. Ross's FY2025 ladder
# showed $500m due within a year that it had already repaid by Q1, which read
# as a refinancing wall that no longer exists. Require the ladder to reconcile
# to reported debt within this tolerance before deriving anything from it.
MATURITY_LADDER_RECONCILE_TOLERANCE = 0.25
# Share of total debt maturing within 12 months that constitutes a
# refinancing concentration worth flagging.
REFI_CONCENTRATION_PCT = 0.25
# A TTM figure needs 4 consecutive quarters; a quarter-end gap larger than
# this (in days) means the series is broken and TTM must not be computed.
MAX_QUARTER_GAP_DAYS = 115

# ---------------------------------------------------------------------------
# Credit policy thresholds (ASSUMPTIONS -- not real negotiated covenants)
# ---------------------------------------------------------------------------
# Real credit agreements are private. These are illustrative values in the
# range typically seen in public retail term-loan/revolver agreements and
# rating-agency criteria. Every memo or validation doc built on this output
# must state them as assumptions.
DEBT_EBITDA_COVENANT = 4.5      # typical retail total-leverage maintenance test
MIN_INTEREST_COVERAGE = 2.0     # typical minimum EBITDA/interest test
MIN_CURRENT_RATIO = 1.0
MIN_FCF_TO_DEBT = 0.05          # below 5% FCF/debt = weak deleveraging capacity

# Altman Z: this pipeline uses the Z"-Score (the non-manufacturer /
# service-company revision), not the original 1968 manufacturing Z.
# The original Z's 0.6 * (Market Cap / Total Liabilities) term needs share
# prices that XBRL doesn't carry, and its asset-turnover term systematically
# flatters high-turnover retailers. Z" drops the turnover term and uses BOOK
# equity, so it is fully computable from filings and is the variant Altman
# himself recommends for non-manufacturers.
#   Z" = 6.56*(WC/TA) + 3.26*(RE/TA) + 6.72*(EBIT/TA) + 1.05*(BookEquity/TL)
ALTMAN_ZPP_DISTRESS = 1.1       # below = distress zone
ALTMAN_ZPP_SAFE = 2.6           # above = safe zone; between = grey zone

# ---------------------------------------------------------------------------
# Scorecard bands -> PD proxy and internal credit grade
# ---------------------------------------------------------------------------
# Rules-based scorecard, NOT a calibrated PD model: it was not fit to any
# historical default data. Points run 0 (best) to 2 (worst) per factor; the
# weighted average maps to a letter grade and a Low/Medium/High band.
#
# Each entry: (metric, direction, [good_threshold, weak_threshold], weight)
# direction "lower_better" -> value <= good scores 0, <= weak scores 1, else 2
# direction "higher_better" -> value >= good scores 0, >= weak scores 1, else 2
SCORECARD = [
    ("debt_to_ebitda",     "lower_better",  [2.0, 4.0],   0.25),
    ("net_debt_to_ebitda", "lower_better",  [1.5, 3.5],   0.10),
    ("interest_coverage",  "higher_better", [6.0, 3.0],   0.20),
    ("fcf_to_debt",        "higher_better", [0.20, 0.08], 0.15),
    ("current_ratio",      "higher_better", [1.5, 1.0],   0.10),
    ("quick_ratio",        "higher_better", [0.8, 0.4],   0.05),
    ("altman_z_double_prime", "higher_better", [ALTMAN_ZPP_SAFE, ALTMAN_ZPP_DISTRESS], 0.15),
]

# Weighted score (0=best, 2=worst) -> internal grade. Cutoffs are the
# scorecard's own calibration, chosen so a zero-debt investment-grade retailer
# lands in A/AA and a covenant-breaching name lands in B/CCC.
GRADE_BANDS = [
    (0.15, "AA"),
    (0.40, "A"),
    (0.75, "BBB"),
    (1.10, "BB"),
    (1.50, "B"),
    (9.99, "CCC"),
]

# Grades at or below this are sub-investment-grade for reporting purposes.
INVESTMENT_GRADE_FLOOR = "BBB"
GRADE_ORDER = ["AA", "A", "BBB", "BB", "B", "CCC"]

# PD-proxy band from the same weighted score. Relative risk ranking only --
# these are NOT probabilities.
PD_BANDS = [(0.40, "Low"), (1.00, "Medium"), (9.99, "High")]

# A score built on too few available metrics isn't trustworthy. Below this
# share of scorecard weight, the grade is suppressed rather than reported --
# the old version scored missing data as 0 points, which handed "A" grades to
# companies whose debt simply hadn't been extracted.
MIN_SCORECARD_COVERAGE = 0.60

# ---------------------------------------------------------------------------
# Stress scenario assumptions
# ---------------------------------------------------------------------------
FLOATING_RATE_DEBT_PCT = 0.50   # assumed share of debt priced off a floating index
INVENTORY_STRESS_PCT = 0.30     # assumed inventory build in the inventory scenario
# In the inventory scenario the build is assumed to be cash-funded (cash down,
# inventory up, total current assets unchanged) rather than debt-funded.
INVENTORY_BUILD_IS_CASH_FUNDED = True
# Share of an EBITDA decline that flows through to free cash flow. Not 100%:
# a revenue decline releases working capital (inventory and payables shrink),
# which partly cushions cash flow in the first year of a downturn.
EBITDA_TO_FCF_PASSTHROUGH = 0.80
# Assumed cash tax rate, used to convert the pre-tax EBITDA shock into an
# after-tax cash-flow shock.
CASH_TAX_RATE = 0.25

# ---------------------------------------------------------------------------
# Early-warning (trend) triggers -- the "early warning" half of the system
# ---------------------------------------------------------------------------
# Level tests catch companies that are already impaired. These catch companies
# still inside their covenants but moving the wrong way fast.
EW_LEVERAGE_RISE_TURNS = 0.75      # Debt/EBITDA up this many turns YoY
EW_MARGIN_DROP_BPS = 150           # operating margin down this many bps YoY
EW_EBITDA_DECLINE_PCT = 0.15       # TTM EBITDA down this much YoY
EW_COVERAGE_DROP_PCT = 0.25        # interest coverage down this much YoY
EW_WORKING_CAPITAL_DROP_PCT = 0.20 # working capital down this much YoY
EW_CASH_BURN_QUARTERS = 2          # consecutive quarters of negative FCF
