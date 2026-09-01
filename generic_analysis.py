"""
generic_analysis.py
---------------------
Fully generic exploratory data analysis (EDA) functions. Unlike analysis.py
and product_analysis.py (which expect specific business columns like
"revenue" or "rating"), this module makes NO assumptions about what the
columns mean. It infers column TYPES (numeric, categorical, datetime, text/id)
and runs the appropriate generic analysis on each.

This is what "works on any file" actually looks like: it can describe and
profile any dataset, but it cannot know business meaning (that still needs
a human, or the column-mapping step in the specialized apps).
"""

import pandas as pd
from file_io import clean_numeric as _try_numeric


# _try_numeric is imported from file_io.clean_numeric above (single source of truth).

def infer_column_types(df, categorical_max_unique=50, categorical_max_ratio=0.5, text_length_threshold=40):
    """
    Classify each column as one of: 'numeric', 'datetime', 'categorical', 'text'.

    Heuristics (the same basic approach real auto-EDA tools use):
    - numeric: already numeric dtype, or values parse as numbers directly or
      after stripping currency/percent/comma formatting
    - datetime: values parse as dates (skipped for columns that look like long
      free text, both for speed and to avoid false positives like review text)
    - categorical: relatively few unique values relative to row count
    - text: everything else (free text, IDs, URLs, high-cardinality strings)
    """
    types = {}
    n = len(df)

    for col in df.columns:
        series = df[col].dropna()
        if series.empty:
            types[col] = "text"
            continue

        # Native datetime dtype must be checked BEFORE numeric — pd.to_numeric()
        # on a datetime64 column silently converts it to nanosecond timestamps,
        # which would otherwise get misclassified as "numeric".
        if pd.api.types.is_datetime64_any_dtype(series):
            types[col] = "datetime"
            continue

        if pd.api.types.is_numeric_dtype(series):
            types[col] = "numeric"
            continue

        avg_len = series.astype(str).str.len().mean()

        # Long free-text columns (reviews, descriptions, URLs) — skip expensive
        # numeric/datetime probing, classify straight to text.
        if avg_len > text_length_threshold:
            types[col] = "text"
            continue

        numeric_try = _try_numeric(series)
        if numeric_try.notna().mean() > 0.9:
            types[col] = "numeric"
            continue

        try:
            sample = series.sample(min(len(series), 200), random_state=0)
            datetime_try = pd.to_datetime(sample, errors="coerce", format="mixed")
            if datetime_try.notna().mean() > 0.9:
                types[col] = "datetime"
                continue
        except Exception:
            pass

        unique_count = series.nunique()
        unique_ratio = unique_count / n if n else 1
        if unique_count <= categorical_max_unique and unique_ratio <= categorical_max_ratio:
            types[col] = "categorical"
        else:
            types[col] = "text"

    return types


def overview(df):
    return {
        "rows": len(df),
        "columns": len(df.columns),
        "duplicate_rows": int(df.duplicated().sum()),
        "missing_total": int(df.isna().sum().sum()),
        "missing_by_column": {k: int(v) for k, v in df.isna().sum().items() if v > 0},
        "memory_mb": round(df.memory_usage(deep=True).sum() / (1024 * 1024), 2),
    }


def numeric_summary(df, column):
    s = _try_numeric(df[column].dropna())
    s = s.dropna()
    if s.empty:
        return None
    return {
        "count": len(s),
        "mean": round(s.mean(), 2),
        "median": round(s.median(), 2),
        "std": round(s.std(), 2),
        "min": round(s.min(), 2),
        "max": round(s.max(), 2),
        "skew": round(s.skew(), 2),
    }


def detect_outliers_iqr(df, column):
    s = _try_numeric(df[column].dropna())
    s = s.dropna()
    if s.empty:
        return 0, (None, None)
    q1, q3 = s.quantile(0.25), s.quantile(0.75)
    iqr = q3 - q1
    lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    outlier_count = int(((s < lower) | (s > upper)).sum())
    return outlier_count, (round(lower, 2), round(upper, 2))


def categorical_summary(df, column, top_n=10):
    counts = df[column].value_counts().head(top_n)
    return counts


def datetime_trend(df, date_column, value_column=None):
    """Row count over time, or sum of value_column over time if numeric column given."""
    dates = pd.to_datetime(df[date_column], errors="coerce")
    temp = df.copy()
    temp["_date"] = dates
    temp = temp.dropna(subset=["_date"])
    temp["_period"] = temp["_date"].dt.to_period("M")

    if value_column and pd.api.types.is_numeric_dtype(pd.to_numeric(temp[value_column], errors="coerce")):
        temp["_value"] = pd.to_numeric(temp[value_column], errors="coerce")
        trend = temp.groupby("_period")["_value"].sum()
    else:
        trend = temp.groupby("_period").size()

    return trend


def correlation_matrix(df, numeric_columns):
    if len(numeric_columns) < 2:
        return None
    cleaned = {col: _try_numeric(df[col]) for col in numeric_columns}
    numeric_df = pd.DataFrame(cleaned)
    return numeric_df.corr().round(2)


# ---------- Cleaning: duplicates, missing values, invalid values ----------

def duplicate_report(df):
    dup_mask = df.duplicated()
    return int(dup_mask.sum()), df[dup_mask]


def missing_value_report(df):
    counts = df.isna().sum()
    pct = (counts / len(df) * 100).round(1)
    report = pd.DataFrame({"missing_count": counts, "missing_pct": pct})
    return report[report["missing_count"] > 0].sort_values("missing_count", ascending=False)


_NEGATIVE_SUSPECT_KEYWORDS = ["price", "qty", "quantity", "unit", "sales", "revenue",
                              "amount", "total", "units", "cost"]


def invalid_value_report(df, numeric_cols):
    """
    Flags numeric columns where negative values are suspicious (price, quantity,
    sales, etc. shouldn't normally be negative — profit/discount CAN be negative
    legitimately, so those are excluded from this check by name).
    Returns a dict: column -> count of negative rows, only for suspect columns.
    """
    exclude_keywords = ["profit", "discount", "growth", "change", "margin"]
    findings = {}
    for col in numeric_cols:
        name_lower = col.lower()
        if any(k in name_lower for k in exclude_keywords):
            continue
        if any(k in name_lower for k in _NEGATIVE_SUSPECT_KEYWORDS):
            s = _try_numeric(df[col]).dropna()
            neg_count = int((s < 0).sum())
            if neg_count > 0:
                findings[col] = neg_count
    return findings


def clean_pipeline(df, drop_duplicates=True, drop_rows_missing_in=None):
    """
    Apply cleaning steps and return (cleaned_df, report_dict) so every change
    is visible and reversible — nothing is silently dropped.
    """
    report = {"starting_rows": len(df)}
    cleaned = df.copy()

    if drop_duplicates:
        before = len(cleaned)
        cleaned = cleaned.drop_duplicates()
        report["duplicates_removed"] = before - len(cleaned)
    else:
        report["duplicates_removed"] = 0

    if drop_rows_missing_in:
        before = len(cleaned)
        cleaned = cleaned.dropna(subset=drop_rows_missing_in)
        report["rows_dropped_for_missing_critical_fields"] = before - len(cleaned)
    else:
        report["rows_dropped_for_missing_critical_fields"] = 0

    report["ending_rows"] = len(cleaned)
    return cleaned, report


# ---------- KPI auto-detection ----------

_AMOUNT_KEYWORDS = ["revenue", "sales", "total sales", "amount", "total", "profit"]
_QTY_KEYWORDS = ["qty", "quantity", "units", "units sold"]
_PRICE_KEYWORDS = ["price", "unit price", "rate"]
_CATEGORY_KEYWORDS = ["category", "product", "region", "segment", "type", "state", "city", "store"]


def guess_amount_column(numeric_cols):
    """Best-guess which numeric column represents a monetary amount, by name."""
    for keyword in _AMOUNT_KEYWORDS:
        for col in numeric_cols:
            if keyword in col.lower():
                return col
    return None


def guess_qty_price_columns(numeric_cols):
    qty_col = next((c for c in numeric_cols if any(k in c.lower() for k in _QTY_KEYWORDS)), None)
    price_col = next((c for c in numeric_cols if any(k in c.lower() for k in _PRICE_KEYWORDS)), None)
    return qty_col, price_col


def guess_category_column(categorical_cols):
    for keyword in _CATEGORY_KEYWORDS:
        for col in categorical_cols:
            if keyword in col.lower():
                return col
    return categorical_cols[0] if categorical_cols else None


def compute_kpis(df, amount_col, date_col=None, category_col=None):
    """Core KPI numbers, all computed directly from the data — no assumptions
    beyond which columns represent amount/date/category (shown to the user)."""
    amounts = _try_numeric(df[amount_col]).dropna()
    kpis = {
        "total": round(amounts.sum(), 2),
        "average": round(amounts.mean(), 2),
        "median": round(amounts.median(), 2),
        "count": len(amounts),
        "min": round(amounts.min(), 2),
        "max": round(amounts.max(), 2),
    }

    if date_col:
        temp = df.copy()
        temp["_date"] = pd.to_datetime(temp[date_col], errors="coerce")
        temp["_amount"] = _try_numeric(temp[amount_col])
        temp = temp.dropna(subset=["_date", "_amount"])
        if not temp.empty:
            temp["_period"] = temp["_date"].dt.to_period("M")
            monthly = temp.groupby("_period")["_amount"].sum().sort_index()
            kpis["monthly_trend"] = monthly
            if len(monthly) >= 2 and monthly.iloc[0] != 0:
                periods = len(monthly) - 1
                kpis["avg_monthly_growth_pct"] = round(
                    ((monthly.iloc[-1] / monthly.iloc[0]) ** (1 / periods) - 1) * 100, 2
                )

    if category_col:
        temp = df.copy()
        temp["_amount"] = _try_numeric(temp[amount_col])
        by_cat = temp.groupby(category_col)["_amount"].sum().sort_values(ascending=False)
        kpis["by_category"] = by_cat
        cum_pct = (by_cat.cumsum() / by_cat.sum() * 100).round(1)
        kpis["pareto_n_for_80pct"] = int((cum_pct <= 80).sum()) + 1

    return kpis


def build_report_text(filename, overview_dict, quality_notes, kpis, amount_col, date_col, category_col):
    """Plain, computed markdown report — every number here is a real
    calculation, not AI-generated text."""
    lines = [f"# Data Analysis Report: {filename}", ""]
    lines.append("## Data Overview")
    lines.append(f"- Rows: {overview_dict['rows']}")
    lines.append(f"- Columns: {overview_dict['columns']}")
    lines.append(f"- Duplicate rows found: {overview_dict['duplicate_rows']}")
    lines.append(f"- Missing values (total cells): {overview_dict['missing_total']}")
    lines.append("")

    lines.append("## Cleaning Applied")
    for note in quality_notes:
        lines.append(f"- {note}")
    lines.append("")

    lines.append("## KPI Summary")
    lines.append(f"- Amount column used: **{amount_col}**" + (" (derived: quantity × price)" if amount_col == "revenue_calculated" else ""))
    if date_col:
        lines.append(f"- Date column used: **{date_col}**")
    if category_col:
        lines.append(f"- Category column used: **{category_col}**")
    lines.append(f"- Total: {kpis['total']:,}")
    lines.append(f"- Average: {kpis['average']:,}")
    lines.append(f"- Median: {kpis['median']:,}")
    lines.append(f"- Row count used: {kpis['count']}")
    lines.append(f"- Min / Max: {kpis['min']:,} / {kpis['max']:,}")
    if "avg_monthly_growth_pct" in kpis:
        lines.append(f"- Average monthly growth: {kpis['avg_monthly_growth_pct']:+.1f}%")
    lines.append("")

    if "by_category" in kpis:
        lines.append(f"## Breakdown by {category_col}")
        for cat, val in kpis["by_category"].head(10).items():
            lines.append(f"- {cat}: {val:,.2f}")
        lines.append("")
        lines.append(f"**{kpis['pareto_n_for_80pct']} categories** account for roughly 80% of total {amount_col}.")
        lines.append("")

    if "monthly_trend" in kpis:
        lines.append("## Monthly Trend")
        for period, val in kpis["monthly_trend"].items():
            lines.append(f"- {period}: {val:,.2f}")

    return "\n".join(lines)
