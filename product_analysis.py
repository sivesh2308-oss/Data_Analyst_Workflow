"""
product_analysis.py
---------------------
Analytics functions for PRODUCT-LEVEL data (price, rating, category, reviews)
as opposed to sales.py's TRANSACTION-LEVEL data (date, units, revenue).

Why a separate module instead of forcing one tool to handle both:
A sales transaction file tells you WHAT SOLD, WHEN, and FOR HOW MUCH.
A product catalog like Amazon's tells you WHAT EXISTS, its PRICE, and its
RATING — there's no time dimension and no "revenue" to trend. Trying to
force the sales dashboard onto this data would mean inventing numbers
that aren't there. Different data shape -> different (but related) tool.
"""

import pandas as pd
from file_io import clean_numeric


REQUIRED_FIELDS = ["product_name", "category", "discounted_price", "actual_price",
                    "discount_percentage", "rating", "rating_count"]


def data_quality_report(raw_df):
    return {
        "row_count": len(raw_df),
        "column_count": len(raw_df.columns),
        "missing_by_column": raw_df.isna().sum().to_dict(),
        "duplicate_rows": int(raw_df.duplicated().sum()),
    }


def missing_required_columns(df):
    return [f for f in REQUIRED_FIELDS if f not in df.columns]


def apply_column_mapping(df, mapping):
    rename_map = {v: k for k, v in mapping.items() if v}
    renamed = df.rename(columns=rename_map)
    keep_cols = [c for c in REQUIRED_FIELDS if c in renamed.columns]
    return renamed[keep_cols].copy()


def _clean_percent(series):
    """Strip % sign, e.g. '64%' -> 64.0"""
    return clean_numeric(series)


def clean(df):
    """Clean an already column-mapped product dataframe."""
    df = df.copy()

    df["discounted_price"] = clean_numeric(df["discounted_price"])
    df["actual_price"] = clean_numeric(df["actual_price"])
    df["discount_percentage"] = _clean_percent(df["discount_percentage"])
    df["rating"] = pd.to_numeric(df["rating"], errors="coerce")
    df["rating_count"] = clean_numeric(df["rating_count"])

    # Category columns are often a pipe-delimited hierarchy, e.g.
    # "Electronics|Accessories|Cables" -> take the top-level category
    df["top_category"] = df["category"].astype(str).str.split("|").str[0]

    # Note: no drop_duplicates() here, deliberately. Once reduced to just
    # (product_name, category, price, rating...), two different real
    # products could coincidentally share identical values -- the raw file's
    # duplicate count (computed before column mapping) is the trustworthy signal.
    df = df.dropna(subset=["discounted_price", "rating"])

    return df


def descriptive_stats(df):
    cols = [c for c in ["discounted_price", "actual_price", "discount_percentage", "rating", "rating_count"] if c in df.columns]
    return df[cols].describe().round(2)


def detect_outliers_iqr(df, column="discounted_price"):
    q1 = df[column].quantile(0.25)
    q3 = df[column].quantile(0.75)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    outliers = df[(df[column] < lower) | (df[column] > upper)]
    return outliers, {"q1": q1, "q3": q3, "iqr": iqr, "lower_bound": lower, "upper_bound": upper}


def category_summary(df):
    """Product count, avg price, avg rating per top-level category."""
    summary = df.groupby("top_category").agg(
        product_count=("product_name", "count"),
        avg_price=("discounted_price", "mean"),
        avg_rating=("rating", "mean"),
        avg_discount_pct=("discount_percentage", "mean"),
    ).round(2).sort_values("product_count", ascending=False)
    return summary


def top_reviewed_products(df, n=10):
    return df.sort_values("rating_count", ascending=False)[
        ["product_name", "rating", "rating_count", "discounted_price"]
    ].head(n)


def top_discounted_products(df, n=10):
    return df.sort_values("discount_percentage", ascending=False)[
        ["product_name", "discount_percentage", "actual_price", "discounted_price"]
    ].head(n)


def price_rating_correlation(df):
    cols = ["discounted_price", "discount_percentage", "rating", "rating_count"]
    cols = [c for c in cols if c in df.columns]
    return df[cols].corr().round(2)
