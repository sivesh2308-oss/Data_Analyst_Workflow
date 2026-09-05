"""
mcp_server.py
--------------
Exposes the Data Analyst Workflow engine (file_io.py, generic_analysis.py)
as MCP tools. Numbers here are always real pandas computation — the LLM
client only ever reads results, never computes them.
"""

from mcp.server.fastmcp import FastMCP
import pandas as pd

from file_io import read_any_file, get_excel_sheet_names
from generic_analysis import (
    infer_column_types,
    overview,
    numeric_summary,
    detect_outliers_iqr,
    categorical_summary,
    detect_date_ambiguity,
    datetime_trend,
    duplicate_report,
    missing_value_report,
    invalid_value_report,
    find_case_variants,
    find_fuzzy_variants,
    compute_kpis,
    build_report_text,
    forecast_linear,
)

mcp = FastMCP("data-analyst-workflow")

# in-memory store: dataframe_id -> DataFrame
_dataframes: dict[str, pd.DataFrame] = {}


def _get_df(dataframe_id: str) -> pd.DataFrame:
    if dataframe_id not in _dataframes:
        raise ValueError(f"No loaded file with id '{dataframe_id}'. Call load_file first.")
    return _dataframes[dataframe_id]


@mcp.tool()
def load_file(file_path: str) -> dict:
    """Load a CSV/Excel file with the project's robust reader (encoding
    fallback, delimiter sniffing, junk-row removal). Returns a dataframe_id
    to use in every other tool call, plus any cleanup notes."""
    with open(file_path, "rb") as f:  # read_any_file checks .name for .xlsx/.xls
        df, notes = read_any_file(f)
    _dataframes[file_path] = df
    return {
        "dataframe_id": file_path,
        "rows": len(df),
        "columns": list(df.columns),
        "cleanup_notes": notes,
    }


@mcp.tool()
def get_column_types(dataframe_id: str) -> dict:
    """Classify each column as numeric / datetime / categorical / text —
    always shown for confirmation, never silently assumed downstream."""
    return infer_column_types(_get_df(dataframe_id))


@mcp.tool()
def get_overview(dataframe_id: str) -> dict:
    """Shape, duplicate rows, missing values, memory usage."""
    return overview(_get_df(dataframe_id))


@mcp.tool()
def get_numeric_summary(dataframe_id: str, column: str) -> dict:
    """Mean/median/std/min/max/skew for one numeric column."""
    result = numeric_summary(_get_df(dataframe_id), column)
    return result or {"error": f"'{column}' has no valid numeric values"}


@mcp.tool()
def get_outliers(dataframe_id: str, column: str) -> dict:
    """IQR-based outlier count and bounds for a numeric column. Flags only —
    never removes or corrects data automatically."""
    count, bounds = detect_outliers_iqr(_get_df(dataframe_id), column)
    return {"outlier_count": count, "lower_bound": bounds[0], "upper_bound": bounds[1]}


@mcp.tool()
def get_categorical_summary(dataframe_id: str, column: str, top_n: int = 10) -> dict:
    """Top N most frequent values in a categorical column."""
    return categorical_summary(_get_df(dataframe_id), column, top_n).to_dict()


@mcp.tool()
def check_date_ambiguity(dataframe_id: str, column: str) -> dict:
    """Checks whether a date column is genuinely ambiguous (e.g. 03-01-2025)
    and needs the user to pick day-first vs month-first — never auto-guessed."""
    is_ambiguous = detect_date_ambiguity(_get_df(dataframe_id)[column])
    return {"column": column, "ambiguous": is_ambiguous}


@mcp.tool()
def get_data_quality_report(dataframe_id: str, numeric_columns: list[str]) -> dict:
    """Duplicate rows, missing-value report, and suspicious negative values
    (price/qty/sales columns) in one call."""
    df = _get_df(dataframe_id)
    dup_count, _ = duplicate_report(df)
    missing = missing_value_report(df)
    invalid = invalid_value_report(df, numeric_columns)
    return {
        "duplicate_rows": dup_count,
        "missing_by_column": missing.to_dict(orient="index"),
        "suspicious_negative_values": invalid,
    }


@mcp.tool()
def get_category_variants(dataframe_id: str, column: str) -> dict:
    """Case/whitespace duplicate spellings (auto-mergeable) plus fuzzy-typo
    suggestions (require explicit human confirmation before merging)."""
    df = _get_df(dataframe_id)
    return {
        "case_whitespace_variants": find_case_variants(df, column),
        "fuzzy_typo_suggestions": find_fuzzy_variants(df, column),
    }


@mcp.tool()
def get_kpis(dataframe_id: str, amount_col: str, date_col: str = None,
             category_col: str = None, dayfirst: bool = False) -> dict:
    """Core KPIs (total/average/median/min/max, monthly trend, category
    breakdown) — amount/date/category columns must be user-confirmed first,
    never guessed silently."""
    kpis = compute_kpis(_get_df(dataframe_id), amount_col, date_col, category_col, dayfirst)
    if "monthly_trend" in kpis:
        kpis["monthly_trend"] = {str(k): v for k, v in kpis["monthly_trend"].items()}
    if "by_category" in kpis:
        kpis["by_category"] = kpis["by_category"].to_dict()
    return kpis


@mcp.tool()
def get_forecast(dataframe_id: str, amount_col: str, date_col: str,
                  dayfirst: bool = False, periods_ahead: int = 3) -> dict:
    """Naive linear trend projection — clearly not a real model, labeled
    as a rough 'if this keeps up' estimate."""
    trend = datetime_trend(_get_df(dataframe_id), date_col, amount_col)
    forecast = forecast_linear(trend, periods_ahead)
    return {str(k): round(v, 2) for k, v in forecast.items()}


@mcp.tool()
def generate_report(dataframe_id: str, filename: str, amount_col: str,
                     date_col: str = None, category_col: str = None,
                     dayfirst: bool = False) -> str:
    """Full Markdown report — every number computed directly, no AI text."""
    df = _get_df(dataframe_id)
    ov = overview(df)
    kpis = compute_kpis(df, amount_col, date_col, category_col, dayfirst)
    return build_report_text(filename, ov, [], kpis, amount_col, date_col, category_col)


if __name__ == "__main__":
    mcp.run()