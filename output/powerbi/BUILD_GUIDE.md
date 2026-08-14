# Power BI build guide

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
  Add an X-axis constant line at **4.5** (the assumed covenant)
  and a Y-axis constant line at **2.0** (the coverage floor).
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
  Y = `Stressed Debt to EBITDA`, with a constant line at 4.5.

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
