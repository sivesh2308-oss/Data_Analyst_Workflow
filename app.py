"""
app.py
-------
Interactive local web app version of the Sales Analytics project, built with
Streamlit. Run it with:

    streamlit run app.py

It opens automatically at http://localhost:8501 in your browser.
This follows the order a data analyst actually works through a new file:
1. Data quality check
2. Descriptive stats
3. Business metrics + filters
4. Deeper analysis: Pareto, outliers, seasonality, correlation
"""

import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from ui_theme import apply_theme, metric_card, style_axes, COLORS, CHART_PALETTE

from file_io import read_any_file, SUPPORTED_TYPES
from analysis import (
    missing_required_columns,
    apply_column_mapping,
    clean,
    REQUIRED_FIELDS,
    descriptive_stats,
    detect_outliers_iqr,
    compute_metrics,
    pareto_analysis,
    day_of_week_pattern,
    correlation_matrix,
)

st.set_page_config(page_title="Sales Analytics Dashboard", layout="wide")
apply_theme()

st.title("Sales Analytics Dashboard")
st.caption("Upload a sales file (CSV or Excel) and explore it the way an analyst would.")

uploaded_file = st.sidebar.file_uploader("Upload file", type=SUPPORTED_TYPES)
use_sample = st.sidebar.checkbox("Use sample data instead", value=uploaded_file is None)

if use_sample:
    source = "sales_data.csv"
elif uploaded_file is not None:
    source = uploaded_file
else:
    st.info("Upload a CSV/Excel file or check 'Use sample data' in the sidebar to get started.")
    st.stop()

raw_df, read_notes = read_any_file(source)
for note in read_notes:
    st.sidebar.caption(f"ℹ️ {note}")
quality = {
    "row_count": len(raw_df),
    "duplicate_rows": int(raw_df.duplicated().sum()),
    "missing_by_column": raw_df.isna().sum().to_dict(),
}
missing = missing_required_columns(raw_df)

if missing:
    st.warning(
        f"This file doesn't already use the expected column names. "
        f"Map your columns to the required fields below, then continue."
    )
    st.caption(f"Required fields: {', '.join(REQUIRED_FIELDS)}")

    column_options = ["-- not available --"] + list(raw_df.columns)
    mapping = {}
    map_fields = [f for f in REQUIRED_FIELDS if f != "revenue"]
    cols = st.columns(len(map_fields))
    for i, field in enumerate(map_fields):
        default_idx = column_options.index(field) if field in raw_df.columns else 0
        chosen = cols[i].selectbox(field, column_options, index=default_idx, key=f"map_{field}")
        mapping[field] = None if chosen == "-- not available --" else chosen

    # Revenue gets special treatment: some files (e.g. a per-item sales log)
    # never store total revenue directly, only unit price and quantity sold.
    st.markdown("**Revenue**")
    revenue_mode = st.radio(
        "How is revenue represented in your file?",
        ["A single revenue/sales total column", "Computed as Price × Quantity"],
        horizontal=True,
    )
    if revenue_mode == "A single revenue/sales total column":
        default_idx = column_options.index("revenue") if "revenue" in raw_df.columns else 0
        chosen = st.selectbox("revenue", column_options, index=default_idx, key="map_revenue")
        mapping["revenue"] = None if chosen == "-- not available --" else chosen
        derive_revenue = None
    else:
        rc1, rc2 = st.columns(2)
        price_col = rc1.selectbox("Price column", ["-- select --"] + list(raw_df.columns), key="price_col")
        qty_col = rc2.selectbox("Quantity column", ["-- select --"] + list(raw_df.columns), key="qty_col")
        derive_revenue = (price_col, qty_col) if price_col != "-- select --" and qty_col != "-- select --" else None
        mapping["revenue"] = None

    still_missing = [f for f, v in mapping.items() if v is None and f != "revenue"]
    if still_missing or (mapping.get("revenue") is None and derive_revenue is None):
        if still_missing:
            st.error(f"Can't proceed — missing required field(s): {still_missing}.")
        else:
            st.error("Can't proceed — select a revenue column, or a price and quantity column to compute it from.")
        st.stop()

    mapped_df = apply_column_mapping(raw_df, {k: v for k, v in mapping.items() if k != "revenue"})
    if derive_revenue:
        price_col, qty_col = derive_revenue
        price_vals = pd.to_numeric(raw_df[price_col].astype(str).str.replace(r"[^\d.\-]", "", regex=True), errors="coerce")
        qty_vals = pd.to_numeric(raw_df[qty_col], errors="coerce")
        mapped_df["revenue"] = price_vals * qty_vals
    else:
        mapped_df["revenue"] = raw_df[mapping["revenue"]]

    df = clean(mapped_df)
    st.success("Columns mapped successfully. Showing analysis below.")
else:
    df = clean(raw_df[REQUIRED_FIELDS])

st.sidebar.header("Filters")
regions = st.sidebar.multiselect("Region", sorted(df["region"].unique()), default=list(df["region"].unique()))
products = st.sidebar.multiselect("Product", sorted(df["product"].unique()), default=list(df["product"].unique()))
date_min, date_max = df["date"].min(), df["date"].max()
date_range = st.sidebar.date_input("Date range", value=(date_min, date_max))

filtered = df[df["region"].isin(regions) & df["product"].isin(products)]
if len(date_range) == 2:
    start, end = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
    filtered = filtered[(filtered["date"] >= start) & (filtered["date"] <= end)]

if filtered.empty:
    st.warning("No rows match the current filters.")
    st.stop()

with st.expander("1 - Data quality report (checked before any analysis)", expanded=False):
    c1, c2, c3 = st.columns(3)
    c1.metric("Rows in raw file", quality["row_count"])
    c2.metric("Duplicate rows removed", quality["duplicate_rows"])
    c3.metric("Rows after cleaning", len(df))
    missing = {k: v for k, v in quality["missing_by_column"].items() if v > 0}
    if missing:
        st.write("Missing values by column:", missing)
    else:
        st.write("No missing values found.")

metrics = compute_metrics(filtered)
st.subheader("Key metrics")
k1, k2, k3, k4 = st.columns(4)
k1.metric("Total revenue", f"{metrics['total_revenue']:,.0f}")
k2.metric("Total units", f"{metrics['total_units']:,.0f}")
k3.metric("Avg order value", f"{metrics['avg_order_value']:,.0f}")
growth = metrics["overall_growth_pct"]
k4.metric("Avg monthly growth", f"{growth:+.1f}%" if growth is not None else "n/a")

with st.expander("2 - Descriptive statistics"):
    st.dataframe(descriptive_stats(filtered))

st.subheader("Revenue breakdown")
col1, col2 = st.columns(2)
with col1:
    fig, ax = plt.subplots()
    metrics["by_region"].plot(kind="bar", ax=ax, color=[CHART_PALETTE[i % len(CHART_PALETTE)] for i in range(len(metrics["by_region"]))])
    style_axes(ax)
    ax.set_title("Revenue by Region")
    st.pyplot(fig)
with col2:
    fig, ax = plt.subplots()
    metrics["by_product"].plot(kind="bar", ax=ax, color=[CHART_PALETTE[i % len(CHART_PALETTE)] for i in range(len(metrics["by_product"]))])
    style_axes(ax)
    ax.set_title("Revenue by Product")
    st.pyplot(fig)

st.subheader("Monthly trend")
fig, ax = plt.subplots()
monthly = metrics["monthly"]
ma = metrics["moving_avg"]
ax.plot(monthly.index.astype(str), monthly.values, marker="o", label="Monthly Revenue")
ax.plot(ma.index.astype(str), ma.values, marker="o", linestyle="--", label="3-mo Moving Avg")
ax.set_ylabel("Revenue")
ax.legend()
st.pyplot(fig)

with st.expander("3 - Pareto analysis (which products drive 80% of revenue)"):
    pareto_df, n_items = pareto_analysis(filtered, group_col="product")
    st.write(f"**{n_items} product(s)** account for roughly 80% of total revenue.")
    st.dataframe(pareto_df)

with st.expander("4 - Outlier detection (IQR method on revenue)"):
    outliers, bounds = detect_outliers_iqr(filtered, "revenue")
    st.write(f"Normal range: {bounds['lower_bound']:.0f} to {bounds['upper_bound']:.0f}")
    if outliers.empty:
        st.write("No outliers detected.")
    else:
        st.dataframe(outliers)

with st.expander("5 - Day-of-week pattern"):
    dow = day_of_week_pattern(filtered)
    fig, ax = plt.subplots()
    dow.plot(kind="bar", ax=ax, color=COLORS["amber"])
    style_axes(ax)
    ax.set_title("Average Revenue by Day of Week")
    st.pyplot(fig)

with st.expander("6 - Correlation matrix"):
    st.dataframe(correlation_matrix(filtered))

st.subheader("Export")
st.download_button(
    "Download filtered data as CSV",
    filtered.to_csv(index=False).encode("utf-8"),
    file_name="filtered_sales_data.csv",
    mime="text/csv",
)
