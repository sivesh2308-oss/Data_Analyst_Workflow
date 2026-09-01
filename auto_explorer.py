"""
auto_explorer.py
------------------
General-purpose data analyst workflow tool: Upload -> Clean -> KPI Insights -> Report.
Works on any CSV or XLSX file -- no schema assumptions.

Every KPI shown here depends on which columns represent "amount", "date", and
"category" -- the app guesses based on column names, but ALWAYS shows and
lets you override the guess, because that judgment call is business-specific
and a tool can't know it for certain. The math itself is exact once those
columns are chosen; the column choice is the one thing that needs a human.

Run with:
    streamlit run auto_explorer.py
"""

import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

from file_io import read_any_file, SUPPORTED_TYPES
from generic_analysis import (
    infer_column_types,
    overview,
    numeric_summary,
    detect_outliers_iqr,
    categorical_summary,
    datetime_trend,
    correlation_matrix,
    duplicate_report,
    missing_value_report,
    invalid_value_report,
    clean_pipeline,
    guess_amount_column,
    guess_qty_price_columns,
    guess_category_column,
    compute_kpis,
    build_report_text,
    _try_numeric,
)

st.set_page_config(page_title="Data Analyst Workflow", layout="wide")
st.title("Data Analyst Workflow")
st.caption("Upload -> Clean -> KPI Insights -> Report. Works on any CSV or Excel file.")

uploaded_file = st.sidebar.file_uploader("Upload CSV or Excel", type=SUPPORTED_TYPES)
if uploaded_file is None:
    st.info("Upload a file to begin.")
    st.stop()

sheet_name = None
if uploaded_file.name.lower().endswith((".xlsx", ".xls")):
    from file_io import get_excel_sheet_names
    sheets = get_excel_sheet_names(uploaded_file)
    uploaded_file.seek(0)
    if len(sheets) > 1:
        sheet_name = st.sidebar.selectbox("Sheet", sheets)
    else:
        sheet_name = sheets[0]

with st.spinner("Reading file..."):
    try:
        raw_df, read_notes = read_any_file(uploaded_file, sheet_name=sheet_name)
        for note in read_notes:
            st.info(f"File reading note: {note}")
    except Exception as e:
        st.error(f"Could not read this file: {e}")
        st.stop()

types = infer_column_types(raw_df)
numeric_cols = [c for c, t in types.items() if t == "numeric"]
categorical_cols = [c for c, t in types.items() if t == "categorical"]
datetime_cols = [c for c, t in types.items() if t == "datetime"]
text_cols = [c for c, t in types.items() if t == "text"]

# ================= STEP 1: OVERVIEW =================
st.header("1. Data Overview")
ov = overview(raw_df)
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Rows", ov["rows"])
c2.metric("Columns", ov["columns"])
c3.metric("Duplicate rows", ov["duplicate_rows"])
c4.metric("Missing values", ov["missing_total"])
c5.metric("Size (MB)", ov["memory_mb"])

with st.expander("Detected column types"):
    st.dataframe(pd.DataFrame({"column": types.keys(), "type": types.values()}), hide_index=True)

# ================= STEP 2: CLEANING =================
st.header("2. Data Cleaning")

dup_count, dup_rows = duplicate_report(raw_df)
missing_df = missing_value_report(raw_df)
invalid_findings = invalid_value_report(raw_df, numeric_cols)

col1, col2, col3 = st.columns(3)
col1.metric("Duplicate rows found", dup_count)
col2.metric("Columns with missing values", len(missing_df))
col3.metric("Suspicious negative values", sum(invalid_findings.values()) if invalid_findings else 0)

if not missing_df.empty:
    with st.expander("Missing values by column"):
        st.dataframe(missing_df)

if invalid_findings:
    with st.expander("Suspicious negative values (in columns like price/quantity/sales)"):
        st.write(invalid_findings)
        st.caption("Negative values here usually mean returns, refunds, or data entry errors -- review before trusting totals.")

st.subheader("Apply cleaning")
drop_dupes = st.checkbox("Remove duplicate rows", value=True)
critical_cols = st.multiselect(
    "Drop rows with missing values in these columns (leave empty to keep all rows)",
    options=list(raw_df.columns),
    default=[],
)
df, clean_report = clean_pipeline(raw_df, drop_duplicates=drop_dupes, drop_rows_missing_in=critical_cols or None)

clean_notes = []
if clean_report["duplicates_removed"] > 0:
    clean_notes.append(f"Removed {clean_report['duplicates_removed']} duplicate row(s)")
if clean_report["rows_dropped_for_missing_critical_fields"] > 0:
    clean_notes.append(f"Dropped {clean_report['rows_dropped_for_missing_critical_fields']} row(s) missing values in {critical_cols}")
if not clean_notes:
    clean_notes.append("No changes needed -- no duplicates removed, no rows dropped")

st.success(f"Cleaned: {clean_report['starting_rows']} rows -> {clean_report['ending_rows']} rows")
for note in clean_notes:
    st.write(f"- {note}")

# ================= STEP 3: KPI INSIGHTS =================
st.header("3. KPI Insights")
st.caption("These columns are guessed by name -- confirm or change them, since only you know what they actually mean in this data.")

guessed_amount = guess_amount_column(numeric_cols)
qty_guess, price_guess = guess_qty_price_columns(numeric_cols)

amount_options = ["-- none --"] + numeric_cols + (["(sum of multiple columns)"] if len(numeric_cols) > 1 else [])
default_amount_idx = amount_options.index(guessed_amount) if guessed_amount in amount_options else 0

kcol1, kcol2, kcol3 = st.columns(3)
with kcol1:
    amount_choice = st.selectbox("Amount / revenue column", amount_options, index=default_amount_idx)
with kcol2:
    date_choice = st.selectbox("Date column (optional)", ["-- none --"] + datetime_cols,
                                index=(1 if datetime_cols else 0))
with kcol3:
    cat_guess = guess_category_column(categorical_cols)
    cat_options = ["-- none --"] + categorical_cols
    cat_default = cat_options.index(cat_guess) if cat_guess in cat_options else 0
    cat_choice = st.selectbox("Category column (optional)", cat_options, index=cat_default)

amount_col = None
working_df = df.copy()

if amount_choice == "(sum of multiple columns)":
    sum_cols = st.multiselect("Columns to sum into one amount", numeric_cols)
    if sum_cols:
        working_df["amount_combined"] = sum(_try_numeric(working_df[c]) for c in sum_cols)
        amount_col = "amount_combined"
elif amount_choice != "-- none --":
    amount_col = amount_choice
elif qty_guess and price_guess:
    st.info(f"No direct amount column found. Offering to compute one: {qty_guess} x {price_guess}")
    if st.checkbox(f"Compute amount = {qty_guess} x {price_guess}", value=True):
        working_df["revenue_calculated"] = _try_numeric(working_df[qty_guess]) * _try_numeric(working_df[price_guess])
        amount_col = "revenue_calculated"

date_col = None if date_choice == "-- none --" else date_choice
category_col = None if cat_choice == "-- none --" else cat_choice

if not amount_col:
    st.warning("No amount column selected -- pick one above (or a column combo) to see KPIs. Not every file has a single 'total' field; some (like this one might) need you to choose which numeric column(s) represent the value you care about.")
else:
    kpis = compute_kpis(working_df, amount_col, date_col, category_col)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total", f"{kpis['total']:,.0f}")
    k2.metric("Average", f"{kpis['average']:,.2f}")
    k3.metric("Median", f"{kpis['median']:,.2f}")
    k4.metric("Records", kpis["count"])

    if "avg_monthly_growth_pct" in kpis:
        st.metric("Avg monthly growth", f"{kpis['avg_monthly_growth_pct']:+.1f}%")
        fig, ax = plt.subplots(figsize=(8, 3.5))
        kpis["monthly_trend"].plot(marker="o", ax=ax, color="#3B82F6")
        ax.set_title(f"{amount_col} over time")
        st.pyplot(fig)

    if "by_category" in kpis:
        st.subheader(f"Breakdown by {category_col}")
        fig, ax = plt.subplots(figsize=(8, 3.5))
        kpis["by_category"].head(15).plot(kind="bar", ax=ax, color="#10B981")
        st.pyplot(fig)
        st.caption(f"{kpis['pareto_n_for_80pct']} categories drive ~80% of total {amount_col}.")
        st.dataframe(kpis["by_category"])

    with st.expander("Outlier check on amount column"):
        count, bounds = detect_outliers_iqr(working_df, amount_col)
        st.write(f"{count} outlier(s) outside normal range ({bounds[0]} to {bounds[1]})")

# ================= STEP 4: DEEPER EXPLORATION (any column) =================
with st.expander("4. Explore any other column"):
    if numeric_cols:
        sel = st.selectbox("Numeric column", numeric_cols, key="explore_numeric")
        stats = numeric_summary(working_df, sel)
        if stats:
            st.write(stats)
            fig, ax = plt.subplots()
            ax.hist(_try_numeric(working_df[sel]).dropna(), bins=25, color="#8B5CF6")
            st.pyplot(fig)
    if categorical_cols:
        sel2 = st.selectbox("Categorical column", categorical_cols, key="explore_cat")
        st.dataframe(categorical_summary(working_df, sel2))
    if len(numeric_cols) >= 2:
        st.write("Correlation matrix:")
        st.dataframe(correlation_matrix(working_df, numeric_cols))

# ================= STEP 5: REPORT =================
st.header("5. Report")
if amount_col:
    report_text = build_report_text(
        uploaded_file.name, ov, clean_notes, kpis, amount_col, date_col, category_col
    )
    st.text_area("Report preview", report_text, height=300)
    st.download_button("Download report (Markdown)", report_text.encode("utf-8"),
                        file_name="analysis_report.md", mime="text/markdown")
else:
    st.info("Select an amount column above to generate a KPI report.")

st.download_button(
    "Download cleaned data (CSV)",
    working_df.to_csv(index=False).encode("utf-8"),
    file_name="cleaned_data.csv",
    mime="text/csv",
)
