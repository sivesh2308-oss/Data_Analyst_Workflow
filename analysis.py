"""
analysis.py
------------
Reusable analytics functions — the same "what would a data analyst check first"
checklist, used by both the command-line script and the web app.

Sections:
1. Data quality profiling   (do this FIRST on any new file)
2. Descriptive statistics
3. Outlier detection (IQR method)
4. Core business metrics (revenue, growth, region/product breakdowns)
5. Pareto analysis (80/20 rule)
6. Seasonality (day-of-week pattern)
7. Correlation
"""

import pandas as pd
from file_io import clean_numeric


# ---------- 1. Data quality profiling ----------

def data_quality_report(raw_df):
    """
    The first thing an analyst checks on any new file: is the data trustworthy?
    Returns a dict describing missing values, duplicates, and dtypes.
    """
    report = {
        "row_count": len(raw_df),
        "column_count": len(raw_df.columns),
        "missing_by_column": raw_df.isna().sum().to_dict(),
        "duplicate_rows": int(raw_df.duplicated().sum()),
        "dtypes": raw_df.dtypes.astype(str).to_dict(),
    }
    return report


REQUIRED_FIELDS = ["date", "region", "product", "units", "revenue"]


def read_raw(filepath_or_buffer):
    """
    Step 1: just read the file and profile it. No assumptions about column
    names yet — this is what lets the app support files that don't already
    use our exact column names.
    """
    df = pd.read_csv(filepath_or_buffer)
    quality = data_quality_report(df)
    return df, quality


def missing_required_columns(df):
    """Which of our required fields are NOT already present as column names."""
    return [f for f in REQUIRED_FIELDS if f not in df.columns]


def apply_column_mapping(df, mapping):
    """
    Step 2: rename the user's actual columns to our required field names.
    mapping is a dict like {"date": "order_date", "revenue": "total_amount"}.
    Only the fields present in mapping are renamed/kept.
    """
    rename_map = {v: k for k, v in mapping.items() if v}
    renamed = df.rename(columns=rename_map)
    keep_cols = [c for c in REQUIRED_FIELDS if c in renamed.columns]
    return renamed[keep_cols].copy()


def clean(df):
    """
    Step 3: clean an already column-mapped dataframe (must already have our
    required column names). Coerces bad values to NaN, drops unusable rows.

    Note: this does NOT drop duplicate rows here. Once a file is reduced to
    just (date, region, product, units, revenue), two genuinely different
    transactions can share identical values by coincidence (e.g. two
    different customers buying the same product, same quantity, same store,
    same day) — dropping those as "duplicates" would silently delete real
    sales. True duplicate detection should happen on the raw file (all
    original columns, including any ID field), not on this reduced view.
    """
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["units"] = clean_numeric(df["units"])
    df["revenue"] = clean_numeric(df["revenue"])

    df = df.dropna(subset=["date", "units", "revenue"])
    df["month"] = df["date"].dt.to_period("M")
    df["day_of_week"] = df["date"].dt.day_name()

    return df


def load_and_clean(filepath_or_buffer):
    """
    Convenience wrapper for files that ALREADY use our exact column names
    (e.g. the CLI script and the sample data). The web app uses read_raw +
    apply_column_mapping + clean instead, so it can handle other layouts.
    """
    df, quality = read_raw(filepath_or_buffer)
    missing = missing_required_columns(df)
    if missing:
        raise ValueError(
            f"This file is missing required column(s): {missing}. "
            f"Use the web app's column-mapping step, or rename these columns "
            f"in the CSV to match: {REQUIRED_FIELDS}"
        )
    df = clean(df)
    return df, quality


# ---------- 2. Descriptive statistics ----------

def descriptive_stats(df, columns=("units", "revenue")):
    """Standard describe() table — mean, std, min, quartiles, max."""
    return df[list(columns)].describe().round(2)


# ---------- 3. Outlier detection (IQR method) ----------

def detect_outliers_iqr(df, column="revenue"):
    """
    Flags rows outside 1.5x the interquartile range — the standard, robust
    way analysts flag suspicious values without assuming a normal distribution.
    """
    q1 = df[column].quantile(0.25)
    q3 = df[column].quantile(0.75)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    outliers = df[(df[column] < lower) | (df[column] > upper)]
    return outliers, {"q1": q1, "q3": q3, "iqr": iqr, "lower_bound": lower, "upper_bound": upper}


# ---------- 4. Core business metrics ----------

def compute_metrics(df):
    metrics = {}
    metrics["total_revenue"] = df["revenue"].sum()
    metrics["total_units"] = df["units"].sum()
    metrics["avg_order_value"] = df["revenue"].mean()
    metrics["row_count"] = len(df)

    metrics["by_region"] = df.groupby("region")["revenue"].sum().sort_values(ascending=False)
    metrics["by_product"] = df.groupby("product")["revenue"].sum().sort_values(ascending=False)

    monthly = df.groupby("month")["revenue"].sum().sort_index()
    metrics["monthly"] = monthly
    metrics["mom_growth"] = monthly.pct_change().mul(100).round(1)
    metrics["moving_avg"] = monthly.rolling(window=3, min_periods=1).mean()

    if len(monthly) >= 2 and monthly.iloc[0] > 0:
        periods = len(monthly) - 1
        metrics["overall_growth_pct"] = ((monthly.iloc[-1] / monthly.iloc[0]) ** (1 / periods) - 1) * 100
    else:
        metrics["overall_growth_pct"] = None

    metrics["units_revenue_corr"] = df["units"].corr(df["revenue"])
    metrics["top_products"] = metrics["by_product"].head(3)

    return metrics


# ---------- 5. Pareto analysis (80/20 rule) ----------

def pareto_analysis(df, group_col="product", value_col="revenue"):
    """
    Classic analyst question: what % of products/regions drive 80% of revenue?
    Returns a dataframe sorted by revenue with cumulative % column.
    """
    grouped = df.groupby(group_col)[value_col].sum().sort_values(ascending=False)
    cum_pct = (grouped.cumsum() / grouped.sum() * 100).round(1)
    result = pd.DataFrame({value_col: grouped, "cumulative_pct": cum_pct})
    n_items_for_80pct = (cum_pct <= 80).sum() + 1
    return result, n_items_for_80pct


# ---------- 6. Seasonality (day-of-week pattern) ----------

def day_of_week_pattern(df):
    """Average revenue by day of week — reveals weekly seasonality."""
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    pattern = df.groupby("day_of_week")["revenue"].mean().reindex(order)
    return pattern.dropna()


# ---------- 7. Correlation ----------

def correlation_matrix(df, columns=("units", "revenue")):
    return df[list(columns)].corr().round(2)
