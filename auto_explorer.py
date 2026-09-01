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
from ui_theme import apply_theme, metric_card, style_axes, COLORS, CHART_PALETTE
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
    find_case_variants,
    standardize_case_whitespace,
    find_fuzzy_variants,
    apply_category_merge,
    detect_date_ambiguity,
    forecast_linear,
    _try_numeric,
)
import json

st.set_page_config(page_title="Data Analyst Workflow", layout="wide")
apply_theme()
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
with c1: metric_card("Rows", f"{ov['rows']:,}", accent="indigo")
with c2: metric_card("Columns", ov["columns"], accent="indigo")
with c3: metric_card("Duplicate rows", ov["duplicate_rows"], accent="coral" if ov["duplicate_rows"] else "teal")
with c4: metric_card("Missing values", ov["missing_total"], accent="coral" if ov["missing_total"] else "teal")
with c5: metric_card("Size (MB)", ov["memory_mb"], accent="amber")

with st.expander("Detected column types"):
    st.dataframe(pd.DataFrame({"column": types.keys(), "type": types.values()}), hide_index=True)

# ================= STEP 2: CLEANING =================
st.header("2. Data Cleaning")

# --- 2a. Standardize category spelling (BEFORE duplicate detection, since two
# rows differing only by 'South' vs 'south' won't be caught as duplicates
# until the spelling is unified first) ---
st.subheader("2a. Standardize category spelling")

variant_findings = {}
for col in categorical_cols:
    variants = find_case_variants(raw_df, col)
    if variants:
        variant_findings[col] = variants

standardized_df = raw_df.copy()
if variant_findings:
    st.write("Found inconsistent spelling (case/whitespace only) in these columns:")
    for col, variants in variant_findings.items():
        with st.expander(f"'{col}': {len(variants)} inconsistent value(s)"):
            for _, spellings in variants.items():
                detail = ", ".join(f"'{v}' ({c}x)" for v, c in spellings.items())
                st.write(f"- {detail}")

    standardize_cols = st.multiselect(
        "Standardize case/whitespace in these columns",
        options=list(variant_findings.keys()),
        default=list(variant_findings.keys()),
    )
    case_choice = st.radio("Standardize to:", ["Title Case", "UPPERCASE", "lowercase"], horizontal=True)
    case_map = {"Title Case": "title", "UPPERCASE": "upper", "lowercase": "lower"}
    for col in standardize_cols:
        standardized_df = standardize_case_whitespace(standardized_df, col, target_case=case_map[case_choice])
    if standardize_cols:
        st.success(f"Standardized: {', '.join(standardize_cols)}")
else:
    st.caption("No case/whitespace inconsistencies detected in categorical columns.")

# Fuzzy typo review -- shown AFTER case standardization, so only genuine
# possible typos remain (not just case differences). Never auto-merged --
# two real categories can look similar, so each merge needs confirmation.
any_fuzzy_found = False
for col in categorical_cols:
    suggestions = find_fuzzy_variants(standardized_df, col)
    if suggestions:
        any_fuzzy_found = True
        with st.expander(f"Possible typos in '{col}' -- review before merging"):
            for canonical, matches in suggestions.items():
                c1, c2 = st.columns([3, 1])
                c1.write(f"{', '.join(matches)}  ->  merge into **'{canonical}'**?")
                if c2.checkbox("Merge", key=f"merge_{col}_{canonical}"):
                    standardized_df = apply_category_merge(standardized_df, col, {m: canonical for m in matches})
if not any_fuzzy_found and categorical_cols:
    st.caption("No likely typo-based duplicates detected beyond case/whitespace.")

# --- 2b. Duplicates, missing values, invalid values ---
st.subheader("2b. Duplicates, missing values, invalid values")

dup_count, dup_rows = duplicate_report(standardized_df)
missing_df = missing_value_report(standardized_df)
invalid_findings = invalid_value_report(standardized_df, numeric_cols)

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
    options=list(standardized_df.columns),
    default=[],
)
df, clean_report = clean_pipeline(standardized_df, drop_duplicates=drop_dupes, drop_rows_missing_in=critical_cols or None)

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

# --- Load a previously saved column mapping, if provided ---
loaded_mapping = {}
with st.expander("Reuse a saved column mapping (optional)"):
    mapping_file = st.file_uploader("Upload a mapping.json from a previous session", type=["json"], key="mapping_upload")
    if mapping_file is not None:
        try:
            loaded_mapping = json.load(mapping_file)
            st.success("Mapping loaded -- selections below are pre-filled where the column names match.")
        except Exception as e:
            st.error(f"Could not read this mapping file: {e}")

amount_options = ["-- none --"] + numeric_cols + (["(sum of multiple columns)"] if len(numeric_cols) > 1 else [])
saved_amount = loaded_mapping.get("amount_col")
default_amount = saved_amount if saved_amount in amount_options else guessed_amount
default_amount_idx = amount_options.index(default_amount) if default_amount in amount_options else 0

kcol1, kcol2, kcol3 = st.columns(3)
with kcol1:
    amount_choice = st.selectbox("Amount / revenue column", amount_options, index=default_amount_idx)
with kcol2:
    date_options = ["-- none --"] + datetime_cols
    saved_date = loaded_mapping.get("date_col")
    date_default_idx = date_options.index(saved_date) if saved_date in date_options else (1 if datetime_cols else 0)
    date_choice = st.selectbox("Date column (optional)", date_options, index=date_default_idx)
with kcol3:
    cat_guess = guess_category_column(categorical_cols)
    cat_options = ["-- none --"] + categorical_cols
    saved_cat = loaded_mapping.get("category_col")
    cat_default = saved_cat if saved_cat in cat_options else cat_guess
    cat_default_idx = cat_options.index(cat_default) if cat_default in cat_options else 0
    cat_choice = st.selectbox("Category column (optional)", cat_options, index=cat_default_idx)

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

dayfirst = False
if date_col:
    is_ambiguous = detect_date_ambiguity(working_df[date_col])
    if is_ambiguous:
        st.warning(
            f"'{date_col}' has ambiguous date formats (e.g. 03-01-2025 could mean "
            f"Jan 3 or Mar 1) -- this can't be auto-detected reliably. Confirm the format:"
        )
    date_format_choice = st.radio(
        "Date format",
        ["Month first (US, e.g. 03-01-2025 = Jan 3)", "Day first (e.g. 03-01-2025 = 3 Jan)"],
        horizontal=True,
        key="date_format_choice",
    )
    dayfirst = date_format_choice.startswith("Day first")

if not amount_col:
    st.warning("No amount column selected -- pick one above (or a column combo) to see KPIs. Not every file has a single 'total' field; some (like this one might) need you to choose which numeric column(s) represent the value you care about.")
else:
    kpis = compute_kpis(working_df, amount_col, date_col, category_col, dayfirst=dayfirst)

    k1, k2, k3, k4 = st.columns(4)
    with k1: metric_card("Total", f"{kpis['total']:,.0f}", accent="indigo")
    with k2: metric_card("Average", f"{kpis['average']:,.2f}", accent="teal")
    with k3: metric_card("Median", f"{kpis['median']:,.2f}", accent="teal")
    with k4: metric_card("Records", f"{kpis['count']:,}", accent="amber")

    if "avg_monthly_growth_pct" in kpis:
        st.metric("Avg monthly growth", f"{kpis['avg_monthly_growth_pct']:+.1f}%")
        fig, ax = plt.subplots(figsize=(8, 3.5))
        kpis["monthly_trend"].plot(marker="o", ax=ax, color=COLORS["indigo"], linewidth=2.2, label="Actual")
        ax.set_title(f"{amount_col} over time")
        style_axes(ax)
        ax.legend(frameon=False)
        st.pyplot(fig)

        with st.expander("Forecast next few months (simple linear trend -- not a guarantee)"):
            periods_ahead = st.slider("Months to project forward", 1, 6, 3)
            forecast = forecast_linear(kpis["monthly_trend"], periods_ahead=periods_ahead)
            if not forecast.empty:
                fig, ax = plt.subplots(figsize=(8, 3.5))
                kpis["monthly_trend"].plot(marker="o", ax=ax, color=COLORS["indigo"], linewidth=2.2, label="Actual")
                forecast.plot(marker="o", ax=ax, color=COLORS["amber"], linestyle="--", linewidth=2, label="Projected")
                ax.set_title(f"{amount_col}: actual + linear projection")
                style_axes(ax)
                ax.legend(frameon=False)
                st.pyplot(fig)
                st.caption(
                    "This is a naive straight-line projection based on the recent trend -- "
                    "real business data rarely moves in a perfectly straight line. Treat it "
                    "as a rough 'if this keeps up' estimate, not a forecast to bet on."
                )
                st.dataframe(forecast.rename("projected").to_frame())
            else:
                st.info("Need at least 2 months of data to project a trend.")

    if "by_category" in kpis:
        st.subheader(f"Breakdown by {category_col}")
        fig, ax = plt.subplots(figsize=(8, 3.5))
        top_cats = kpis["by_category"].head(15)
        bar_colors = [CHART_PALETTE[i % len(CHART_PALETTE)] for i in range(len(top_cats))]
        top_cats.plot(kind="bar", ax=ax, color=bar_colors)
        ax.set_title(f"{amount_col} by {category_col}")
        style_axes(ax)
        st.pyplot(fig)
        st.caption(f"{kpis['pareto_n_for_80pct']} categories drive ~80% of total {amount_col}.")
        st.dataframe(kpis["by_category"])

    with st.expander("Outlier check on amount column"):
        count, bounds = detect_outliers_iqr(working_df, amount_col)
        st.write(f"{count} outlier(s) outside normal range ({bounds[0]} to {bounds[1]})")

    mapping_to_save = json.dumps({
        "amount_col": amount_col,
        "date_col": date_col,
        "category_col": category_col,
        "dayfirst": dayfirst,
    }, indent=2)
    st.download_button(
        "Download this column mapping (reuse next time you upload a similar file)",
        mapping_to_save.encode("utf-8"),
        file_name="mapping.json",
        mime="application/json",
    )

# ================= STEP 4: COMPARE WITH ANOTHER FILE =================
st.header("4. Compare with another file (optional)")
st.caption("E.g. compare this month's export against last month's, or two regions exported separately.")

compare_file = st.file_uploader("Upload a second file to compare against", type=SUPPORTED_TYPES, key="compare_upload")
if compare_file is not None and amount_col:
    try:
        compare_sheet = None
        if compare_file.name.lower().endswith((".xlsx", ".xls")):
            from file_io import get_excel_sheet_names
            c_sheets = get_excel_sheet_names(compare_file)
            compare_file.seek(0)
            compare_sheet = c_sheets[0] if len(c_sheets) == 1 else st.selectbox("Sheet (comparison file)", c_sheets)

        compare_df, compare_notes = read_any_file(compare_file, sheet_name=compare_sheet)
        for note in compare_notes:
            st.caption(f"Comparison file note: {note}")

        compare_types = infer_column_types(compare_df)
        compare_numeric = [c for c, t in compare_types.items() if t == "numeric"]
        compare_datetime = [c for c, t in compare_types.items() if t == "datetime"]
        compare_categorical = [c for c, t in compare_types.items() if t == "categorical"]

        cc1, cc2, cc3 = st.columns(3)
        with cc1:
            c_amount_default = amount_col if amount_col in compare_numeric else (compare_numeric[0] if compare_numeric else None)
            c_amount = st.selectbox("Amount column (comparison file)", compare_numeric,
                                     index=compare_numeric.index(c_amount_default) if c_amount_default in compare_numeric else 0)
        with cc2:
            c_date_options = ["-- none --"] + compare_datetime
            c_date = st.selectbox("Date column (comparison file, optional)", c_date_options)
        with cc3:
            c_cat_options = ["-- none --"] + compare_categorical
            c_cat_default = category_col if category_col in compare_categorical else None
            c_cat = st.selectbox("Category column (comparison file, optional)", c_cat_options,
                                  index=c_cat_options.index(c_cat_default) if c_cat_default in c_cat_options else 0)

        c_date_col = None if c_date == "-- none --" else c_date
        c_cat_col = None if c_cat == "-- none --" else c_cat

        compare_kpis = compute_kpis(compare_df, c_amount, c_date_col, c_cat_col, dayfirst=dayfirst)

        st.subheader("Side-by-side comparison")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total (file 1)", f"{kpis['total']:,.0f}")
        m2.metric("Total (file 2)", f"{compare_kpis['total']:,.0f}",
                   delta=f"{compare_kpis['total'] - kpis['total']:,.0f}")
        m3.metric("Average (file 1)", f"{kpis['average']:,.2f}")
        m4.metric("Average (file 2)", f"{compare_kpis['average']:,.2f}",
                   delta=f"{compare_kpis['average'] - kpis['average']:,.2f}")

        if "by_category" in kpis and "by_category" in compare_kpis:
            st.subheader("Category breakdown comparison")
            combined = pd.DataFrame({
                "file_1": kpis["by_category"],
                "file_2": compare_kpis["by_category"],
            }).fillna(0)
            combined["change"] = combined["file_2"] - combined["file_1"]
            st.dataframe(combined)
    except Exception as e:
        st.error(f"Could not process the comparison file: {e}")
elif compare_file is not None and not amount_col:
    st.info("Select an amount column for the main file (in section 3) before comparing.")

# ================= STEP 5: DEEPER EXPLORATION (any column) =================
with st.expander("5. Explore any other column"):
    if numeric_cols:
        sel = st.selectbox("Numeric column", numeric_cols, key="explore_numeric")
        stats = numeric_summary(working_df, sel)
        if stats:
            st.write(stats)
            fig, ax = plt.subplots()
            ax.hist(_try_numeric(working_df[sel]).dropna(), bins=25, color=COLORS["indigo"], edgecolor="white")
            style_axes(ax)
            st.pyplot(fig)
    if categorical_cols:
        sel2 = st.selectbox("Categorical column", categorical_cols, key="explore_cat")
        st.dataframe(categorical_summary(working_df, sel2))
    if len(numeric_cols) >= 2:
        st.write("Correlation matrix:")
        st.dataframe(correlation_matrix(working_df, numeric_cols))

# ================= STEP 6: REPORT =================
st.header("6. Report")
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
