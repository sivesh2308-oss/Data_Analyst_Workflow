"""
Sales Analytics Dashboard
--------------------------
A local, no-dependency-on-AI data analytics script.

What it does:
1. Loads a sales CSV file
2. Cleans and validates the data (handles missing/bad rows)
3. Computes key business metrics:
   - Total revenue, total units, average order value
   - Revenue by region and by product
   - Monthly revenue trend + month-over-month growth %
   - 3-period moving average (smooths out noise in the trend)
   - Correlation between units sold and revenue
   - Top 3 best-selling products
4. Saves 3 charts as PNG files (bar, bar, line)
5. Writes a plain-text summary report (report.md)

Run it with:
    python analyze_sales.py sales_data.csv
"""

import sys
import pandas as pd
import matplotlib.pyplot as plt


def load_and_clean(filepath):
    """Load the CSV and clean it up."""
    df = pd.read_csv(filepath)

    # Convert types, coercing bad values to NaN instead of crashing
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["units"] = pd.to_numeric(df["units"], errors="coerce")
    df["revenue"] = pd.to_numeric(df["revenue"], errors="coerce")

    before = len(df)
    df = df.dropna(subset=["date", "units", "revenue"])
    after = len(df)

    if before != after:
        print(f"Dropped {before - after} invalid row(s) during cleaning.")

    df["month"] = df["date"].dt.to_period("M")
    return df


def compute_metrics(df):
    """Compute all the summary numbers we care about."""
    metrics = {}

    metrics["total_revenue"] = df["revenue"].sum()
    metrics["total_units"] = df["units"].sum()
    metrics["avg_order_value"] = df["revenue"].mean()
    metrics["row_count"] = len(df)

    # Revenue grouped by region / product
    metrics["by_region"] = df.groupby("region")["revenue"].sum().sort_values(ascending=False)
    metrics["by_product"] = df.groupby("product")["revenue"].sum().sort_values(ascending=False)

    # Monthly trend + month-over-month growth
    monthly = df.groupby("month")["revenue"].sum().sort_index()
    metrics["monthly"] = monthly
    metrics["mom_growth"] = monthly.pct_change().mul(100).round(1)

    # 3-period moving average (smooths short-term noise in the monthly trend)
    metrics["moving_avg"] = monthly.rolling(window=3, min_periods=1).mean()

    # Correlation between units sold and revenue (sanity check on pricing consistency)
    metrics["units_revenue_corr"] = df["units"].corr(df["revenue"])

    # Top 3 products by revenue
    metrics["top_products"] = metrics["by_product"].head(3)

    return metrics


def make_charts(df, metrics, outdir="."):
    """Save 3 charts as PNG files."""

    # 1. Revenue by region
    plt.figure(figsize=(6, 4))
    metrics["by_region"].plot(kind="bar", color="#3B82F6")
    plt.title("Revenue by Region")
    plt.ylabel("Revenue")
    plt.tight_layout()
    plt.savefig(f"{outdir}/revenue_by_region.png")
    plt.close()

    # 2. Revenue by product
    plt.figure(figsize=(6, 4))
    metrics["by_product"].plot(kind="bar", color="#10B981")
    plt.title("Revenue by Product")
    plt.ylabel("Revenue")
    plt.tight_layout()
    plt.savefig(f"{outdir}/revenue_by_product.png")
    plt.close()

    # 3. Monthly trend with moving average
    plt.figure(figsize=(6, 4))
    monthly = metrics["monthly"]
    ma = metrics["moving_avg"]
    plt.plot(monthly.index.astype(str), monthly.values, marker="o", label="Monthly Revenue")
    plt.plot(ma.index.astype(str), ma.values, marker="o", linestyle="--", label="3-mo Moving Avg")
    plt.title("Monthly Revenue Trend")
    plt.ylabel("Revenue")
    plt.legend()
    plt.tight_layout()
    plt.savefig(f"{outdir}/monthly_trend.png")
    plt.close()

    print("Saved charts: revenue_by_region.png, revenue_by_product.png, monthly_trend.png")


def write_report(metrics, outdir="."):
    """Write a plain-text summary report — purely from computed numbers, no AI."""
    lines = []
    lines.append("# Sales Analytics Report\n")
    lines.append(f"- Rows analyzed: {metrics['row_count']}")
    lines.append(f"- Total revenue: {metrics['total_revenue']:.0f}")
    lines.append(f"- Total units sold: {metrics['total_units']:.0f}")
    lines.append(f"- Average order value: {metrics['avg_order_value']:.2f}")
    lines.append(f"- Correlation (units vs revenue): {metrics['units_revenue_corr']:.2f}\n")

    lines.append("## Revenue by Region")
    for region, val in metrics["by_region"].items():
        lines.append(f"- {region}: {val:.0f}")

    lines.append("\n## Top 3 Products by Revenue")
    for product, val in metrics["top_products"].items():
        lines.append(f"- {product}: {val:.0f}")

    lines.append("\n## Monthly Revenue & Month-over-Month Growth")
    for month, rev in metrics["monthly"].items():
        growth = metrics["mom_growth"].get(month)
        growth_str = f"{growth:+.1f}%" if pd.notna(growth) else "n/a"
        lines.append(f"- {month}: {rev:.0f} (growth: {growth_str})")

    report_text = "\n".join(lines)
    with open(f"{outdir}/report.md", "w") as f:
        f.write(report_text)

    print(f"\n{report_text}\n")
    print("Full report saved to report.md")


def main():
    filepath = sys.argv[1] if len(sys.argv) > 1 else "sales_data.csv"
    print(f"Loading {filepath} ...")
    df = load_and_clean(filepath)
    metrics = compute_metrics(df)
    make_charts(df, metrics)
    write_report(metrics)


if __name__ == "__main__":
    main()
