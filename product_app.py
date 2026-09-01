"""
product_app.py
----------------
Interactive dashboard for PRODUCT / RATING / PRICING data (e.g. an Amazon
product export) -- a different data shape than the sales transaction app
(app.py). Run with:

    streamlit run product_app.py
"""

import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

from file_io import read_any_file, SUPPORTED_TYPES
from product_analysis import (
    data_quality_report,
    missing_required_columns,
    apply_column_mapping,
    clean,
    REQUIRED_FIELDS,
    descriptive_stats,
    detect_outliers_iqr,
    category_summary,
    top_reviewed_products,
    top_discounted_products,
    price_rating_correlation,
)

st.set_page_config(page_title="Product Ratings & Pricing Analyzer", layout="wide")

st.title("Product Ratings & Pricing Analyzer")
st.caption("For product-catalog data with price, rating, and category info (e.g. an Amazon product export) -- not transaction/sales data.")

uploaded_file = st.sidebar.file_uploader("Upload file", type=SUPPORTED_TYPES)
use_sample = st.sidebar.checkbox("Use sample data instead", value=uploaded_file is None)

if use_sample:
    source = "product_sample.csv"
elif uploaded_file is not None:
    source = uploaded_file
else:
    st.info("Upload a CSV/Excel file or check 'Use sample data' in the sidebar to get started.")
    st.stop()

raw_df, read_notes = read_any_file(source)
for note in read_notes:
    st.sidebar.caption(f"ℹ️ {note}")
quality = data_quality_report(raw_df)
missing = missing_required_columns(raw_df)

if missing:
    st.warning("This file doesn't already use the expected column names. Map your columns below.")
    st.caption(f"Required fields: {', '.join(REQUIRED_FIELDS)}")
    column_options = ["-- not available --"] + list(raw_df.columns)
    mapping = {}
    cols = st.columns(4)
    for i, field in enumerate(REQUIRED_FIELDS):
        default_idx = column_options.index(field) if field in raw_df.columns else 0
        chosen = cols[i % 4].selectbox(field, column_options, index=default_idx, key=f"pmap_{field}")
        mapping[field] = None if chosen == "-- not available --" else chosen

    still_missing = [f for f, v in mapping.items() if v is None]
    if still_missing:
        st.error(
            f"Can't proceed -- this analysis needs: {still_missing}. "
            f"Your file has no equivalent column(s) for these. This isn't a bug -- "
            f"price/rating analysis genuinely can't run without this data being present."
        )
        st.stop()

    mapped_df = apply_column_mapping(raw_df, mapping)
    df = clean(mapped_df)
    st.success("Columns mapped successfully.")
else:
    df = clean(raw_df[REQUIRED_FIELDS])

if df.empty:
    st.error("After cleaning, no valid rows remained. Check that price/rating columns contain usable values.")
    st.stop()

st.sidebar.header("Filters")
categories = sorted(df["top_category"].dropna().unique())
selected_categories = st.sidebar.multiselect("Category", categories, default=categories)
min_rating = st.sidebar.slider("Minimum rating", 0.0, 5.0, 0.0, 0.1)

filtered = df[df["top_category"].isin(selected_categories) & (df["rating"] >= min_rating)]

if filtered.empty:
    st.warning("No rows match the current filters.")
    st.stop()

with st.expander("1 - Data quality report", expanded=False):
    c1, c2, c3 = st.columns(3)
    c1.metric("Rows in raw file", quality["row_count"])
    c2.metric("Duplicate rows removed", quality["duplicate_rows"])
    c3.metric("Rows after cleaning", len(df))

st.subheader("Key metrics")
k1, k2, k3, k4 = st.columns(4)
k1.metric("Products", len(filtered))
k2.metric("Avg price", f"{filtered['discounted_price'].mean():,.0f}")
k3.metric("Avg rating", f"{filtered['rating'].mean():.2f}")
k4.metric("Avg discount", f"{filtered['discount_percentage'].mean():.1f}%")

with st.expander("2 - Descriptive statistics"):
    st.dataframe(descriptive_stats(filtered))

st.subheader("Price and rating distribution")
col1, col2 = st.columns(2)
with col1:
    fig, ax = plt.subplots()
    ax.hist(filtered["discounted_price"], bins=20, color="#3B82F6")
    ax.set_title("Price Distribution")
    st.pyplot(fig)
with col2:
    fig, ax = plt.subplots()
    ax.hist(filtered["rating"], bins=15, color="#10B981")
    ax.set_title("Rating Distribution")
    st.pyplot(fig)

st.subheader("Category breakdown")
cat_summary = category_summary(filtered)
fig, ax = plt.subplots(figsize=(8, 4))
cat_summary["product_count"].head(10).plot(kind="bar", ax=ax, color="#F59E0B")
ax.set_title("Product Count by Category (Top 10)")
st.pyplot(fig)
st.dataframe(cat_summary)

with st.expander("3 - Discount % vs Rating correlation"):
    st.dataframe(price_rating_correlation(filtered))
    fig, ax = plt.subplots()
    ax.scatter(filtered["discount_percentage"], filtered["rating"], alpha=0.4, color="#8B5CF6")
    ax.set_xlabel("Discount %")
    ax.set_ylabel("Rating")
    ax.set_title("Discount % vs Rating")
    st.pyplot(fig)

with st.expander("4 - Outlier detection (IQR on price)"):
    outliers, bounds = detect_outliers_iqr(filtered, "discounted_price")
    st.write(f"Normal range: {bounds['lower_bound']:.0f} to {bounds['upper_bound']:.0f}")
    st.dataframe(outliers[["product_name", "discounted_price", "rating"]] if not outliers.empty else outliers)

with st.expander("5 - Most-reviewed products"):
    st.dataframe(top_reviewed_products(filtered))

with st.expander("6 - Most-discounted products"):
    st.dataframe(top_discounted_products(filtered))

st.subheader("Export")
st.download_button(
    "Download filtered data as CSV",
    filtered.to_csv(index=False).encode("utf-8"),
    file_name="filtered_products.csv",
    mime="text/csv",
)
