# Data-Analyst-Workflow

A local Python script that analyzes sales data and produces charts + a written summary report — no external services or APIs, runs fully offline.

## What it does

- Loads a sales CSV and cleans it (handles missing/invalid rows)
- Computes:
  - Total revenue, total units, average order value
  - Revenue broken down by region and by product
  - Monthly revenue trend and month-over-month growth %
  - 3-month moving average (smooths short-term noise)
  - Correlation between units sold and revenue
  - Top 3 best-selling products
- Saves 3 charts (`revenue_by_region.png`, `revenue_by_product.png`, `monthly_trend.png`)
- Writes a plain-text summary (`report.md`)

## Tech stack

Python, Pandas, Matplotlib

## How to run

```bash
pip install pandas matplotlib
python analyze_sales.py sales_data.csv
```

Replace `sales_data.csv` with your own file — it just needs columns: `date, region, product, units, revenue`.

## Sample output

See `report.md` and the generated PNG charts after running.

## Web app version (recommended)

Run it as an interactive local dashboard instead of a script:

```bash
pip install pandas matplotlib streamlit
streamlit run app.py
```

This opens automatically at `http://localhost:8501` in your browser. It includes:
- **Data quality report** — missing values, duplicates, dtypes (always check this first)
- **Descriptive statistics** — mean/median/std/quartiles
- **Filters** — by region, product, date range
- **Pareto analysis** — which products drive 80% of revenue
- **Outlier detection** — IQR method
- **Day-of-week seasonality**
- **Correlation matrix**
- **CSV export** of filtered data

## Project structure

- `analyze_sales.py` — original CLI script for sales data (charts + report.md)
- `analysis.py` — shared analytics functions for **transaction-level sales data** (date, region, product, units, revenue)
- `app.py` — Streamlit web app for sales data (interactive, recommended)
- `sales_data.csv` — sample sales data

- `product_analysis.py` — analytics functions for **product-level catalog data** (price, rating, category, reviews — e.g. an Amazon product export)
- `product_app.py` — Streamlit web app for product/rating/pricing data
- `product_sample.csv` — sample product data

- `generic_analysis.py` — column-type inference, cleaning (duplicates/missing/invalid values), auto KPI detection, and report generation for **any** data
- `auto_explorer.py` — Streamlit app implementing the full analyst workflow: **Upload → Clean → KPI Insights → Report**, on any CSV or Excel file, with manual override for every auto-detected column

## Why three apps?

A sales-transaction file tells you *what sold, when, and for how much*.
A product catalog tells you *what exists, its price, and its rating*.
There's no single fixed schema that fits both — and no tool can invent a
"revenue trend" from data that never recorded one. Rather than force one
tool to fake numbers that aren't in the data, this repo has:

1. **`auto_explorer.py`** — the front door, and the one that follows the real analyst
   workflow: **Upload → Clean (duplicates, missing values, suspicious negatives) →
   KPI Insights (auto-detected amount/date/category, always shown and editable) →
   Downloadable Markdown report.** Every KPI number is computed directly from your
   data — nothing is AI-generated. The one thing it can't do automatically is know
   which column *means* "revenue" with certainty — that's a business judgment call,
   so it guesses from column names and always shows you the guess to confirm or change.
2. **`app.py`** — for sales/transaction data, once you map columns to
   date/region/product/units/revenue, you get business metrics (growth,
   Pareto, seasonality) that require knowing what the columns *mean*.
3. **`product_app.py`** — same idea, for product/rating/pricing data.

## Run the auto explorer (works on any file)

```bash
pip install pandas matplotlib streamlit
streamlit run auto_explorer.py
```

## Run the product analyzer

```bash
pip install pandas matplotlib streamlit
streamlit run product_app.py
```



## Compatible file types

All three apps accept **CSV or Excel (.xlsx/.xls)**. File loading is handled by
`file_io.py`, tested against real messy files including: non-UTF-8 encodings,
semicolon- or tab-delimited exports (common outside the US), title/metadata
rows before the real header, trailing "Total" summary rows, and BOM characters
from Excel's "CSV UTF-8" export. It tries the standard parse first and only
falls back to sniffing delimiter/header when the standard parse actually looks
wrong -- so well-formed files (including ones with commas inside quoted text,
like review content) are never second-guessed.

Numeric cleaning (`file_io.clean_numeric`) handles currency symbols, thousands
separators, and percent signs (`₹1,299`, `$1,257`, `45%`) consistently across
all three apps -- one shared implementation, not three separate ones, so a fix
in one place fixes it everywhere.

The sales app's column-mapping step also supports **deriving revenue from
Price x Quantity** when a file has no single revenue/total column (common in
per-item sales logs, e.g. a coffee shop's unit_price + transaction_qty).

## What "universal" actually means here

Every file-reading and cleaning fix above was driven by a real file breaking
it first -- not designed in the abstract. The honest limit: the app can
reliably parse and clean *any* CSV/Excel structure, but it can't guarantee
which column means "revenue" without either matching a known name or a human
confirming it -- that's a business judgment call, not a parsing problem, and
`auto_explorer.py` always shows its guess for you to confirm or override
rather than deciding silently.
