# Data Analyst Workflow

**Live app:** https://data-analyst-workflow.streamlit.app/
**Repo:** https://github.com/sivesh2308-oss/Data_Analyst_Workflow

A Streamlit tool that runs the actual data analyst workflow — **Upload → Clean → KPI Insights → Report** — on any CSV or Excel file, not just one fixed format. Built and hardened by testing against real messy datasets (Amazon product exports, Kaggle sales data, a coffee shop POS export, a wide-format stats file) rather than designed in the abstract.

## What it does

- **Reads almost anything**: CSV or Excel, auto-detects delimiter (comma/semicolon/tab), handles non-UTF-8 encodings, skips junk title rows before the real header, strips currency symbols and thousands separators (`₹1,299`, `$1,257`, `45%`)
- **Cleans data like an analyst would**: flags duplicates, missing values, and suspicious negative values in price/quantity/sales columns; standardizes inconsistent category spelling (`South` / `south` / `SOUth` → one value automatically; typo-like variants such as `Sout` flagged for manual confirmation, never auto-merged)
- **Detects KPIs, but never guesses silently**: auto-suggests which column is "amount," "date," and "category" by name — always shown for you to confirm or override, because that's a business judgment call, not something a tool can know for certain
- **Handles ambiguous dates**: `03-01-2025` could be Jan 3 or Mar 1 — you're prompted to resolve it instead of getting a silently wrong answer
- **Forecasts**: simple linear trend projection on monthly totals (clearly labeled as a naive projection, not a real forecasting model)
- **Compares two files**: upload a second period and see totals/averages/category breakdowns side by side with deltas
- **Remembers your column choices**: downloadable `mapping.json` so re-uploading a similar file next time doesn't require re-mapping from scratch
- **Generates a real report**: downloadable Markdown report — every number in it is computed directly from your data, nothing is AI-generated text

## Why this matters more than it sounds

Most "analyze my CSV" demos work great on one clean sample file and break on the first real file someone uploads. This one was built the other way around: I fed it a coffee shop POS export, an Amazon product dataset, a Superstore sales file, and a wide-format stats file — and fixed the real bugs each one surfaced (a datetime column silently miscast as nanosecond integers, non-UTF-8 encoding crashes, quote-aware CSV parsing so review text with commas doesn't corrupt column detection, and more). The full list of what broke and how it was fixed is in the commit history.

## Tech stack

Python · Pandas · Streamlit · Matplotlib · openpyxl

## Run it locally

```bash
git clone https://github.com/sivesh2308-oss/Data_Analyst_Workflow.git
cd Data_Analyst_Workflow
pip install -r requirements.txt
streamlit run auto_explorer.py
```

Opens at `http://localhost:8501`. Upload any sales-shaped CSV or Excel file — there's no built-in sample data, since the whole point of this tool is handling files it's never seen before. Don't have a file handy? The UCI "Online Retail II" dataset (archive.ics.uci.edu) is a good real-world stress test — messy encoding, returns, missing customer IDs and all.

## Project structure

| File | Purpose |
|---|---|
| `auto_explorer.py` | Main app — the full analyst workflow, works on any file |
| `generic_analysis.py` | Column-type inference, cleaning, KPI auto-detection, forecasting, report generation |
| `file_io.py` | Robust file reading — encoding fallback, delimiter detection, junk-row skipping |
| `ui_theme.py` | Shared visual identity used across all apps |
| `app.py` | Specialized dashboard for sales/transaction data (date, region, product, units, revenue) |
| `product_app.py` | Specialized dashboard for product/rating/pricing data (e.g. Amazon exports) |
| `analysis.py`, `product_analysis.py` | Business-metric logic behind the two specialized dashboards |
| `analyze_sales.py` | Original command-line version (no server needed) |

## Design note: why three apps instead of one

A sales-transaction file tells you *what sold, when, and for how much*. A product catalog tells you *what exists, its price, and its rating*. There's no single schema that fits both, and no tool can invent a "revenue trend" from data that never recorded one. `auto_explorer.py` is the general-purpose front door — it profiles and cleans anything. `app.py` and `product_app.py` layer business-specific metrics on top once you confirm what the columns mean.

## What "works on any file" actually means here

It reliably parses and cleans arbitrary CSV/Excel structure. It cannot guarantee which column means "revenue" without either a name match or your confirmation — that's a judgment call, not a parsing problem, so the app always shows its guess instead of deciding silently.
