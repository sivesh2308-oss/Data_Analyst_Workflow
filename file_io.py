"""
file_io.py
-----------
Shared, robust file loading used by all three apps. Handles real-world file
issues that plain pd.read_csv trips on:

- Excel files (.xlsx, .xls), not just CSV
- BOM characters at the start of a file (common from Excel "CSV UTF-8" exports)
  which otherwise corrupt the first column name, e.g. "ï»¿Retailer" instead
  of "Retailer"
- Non-UTF-8 encodings (falls back to latin1 if utf-8 fails)
"""

import io
import csv
import pandas as pd


_CANDIDATE_DELIMITERS = [",", ";", "\t", "|"]


def _decode_sample(raw_bytes, max_lines=25):
    """Decode enough of the file to sniff structure, trying encodings in order."""
    for enc in ["utf-8-sig", "cp1252", "latin1"]:
        try:
            text = raw_bytes.decode(enc)
            return text.splitlines()[:max_lines], enc
        except UnicodeDecodeError:
            continue
    text = raw_bytes.decode("latin1", errors="replace")
    return text.splitlines()[:max_lines], "latin1"


def _field_count(line, delimiter):
    """Quote-aware field count for one line -- a comma inside a quoted text
    field (e.g. a review: "Great, really great!") must NOT count as a real
    delimiter, or files with free text get misread as having far more
    columns than they do."""
    try:
        row = next(csv.reader([line], delimiter=delimiter))
        return len(row)
    except Exception:
        return 0


def _detect_delimiter_and_header(lines):
    """
    Figure out which delimiter the file actually uses, and how many leading
    rows (titles, generation timestamps, blank rows) come before the real
    header row. Only meant to be used as a FALLBACK when the default comma
    parse already looks wrong -- see _looks_sane() in read_any_file.
    """
    non_empty = [l for l in lines if l.strip()]
    if not non_empty:
        return ",", 0

    best_delim, best_score, best_field_count = ",", -1, 1
    for delim in _CANDIDATE_DELIMITERS:
        counts = [_field_count(l, delim) for l in non_empty]
        nonzero = [c for c in counts if c > 1]
        if not nonzero:
            continue
        from collections import Counter
        mode_count, mode_freq = Counter(nonzero).most_common(1)[0]
        score = mode_freq * mode_count
        if score > best_score:
            best_delim, best_score, best_field_count = delim, score, mode_count

    header_idx = 0
    for i, line in enumerate(lines):
        try:
            fields = next(csv.reader([line], delimiter=best_delim))
        except Exception:
            continue
        if len(fields) != best_field_count:
            continue
        non_empty_fields = sum(1 for f in fields if f.strip())
        if non_empty_fields >= max(1, len(fields) // 2):
            header_idx = i
            break

    return best_delim, header_idx


def _looks_sane(df):
    """Quick sanity check on a parsed dataframe: did the default comma parse
    actually work, or does it look like the wrong delimiter/header was used?
    Used to decide whether to even attempt the fallback detection -- this is
    what prevents the fallback from overriding files that already parse
    correctly (the earlier version of this logic caused a real regression
    on quote-heavy CSVs before this safeguard was added)."""
    if df.shape[1] <= 1:
        return False
    unnamed_ratio = sum(1 for c in df.columns if str(c).startswith("Unnamed")) / len(df.columns)
    if unnamed_ratio > 0.5:
        return False
    return True


def _drop_junk_rows(df):
    """
    Drop rows that are entirely empty, and rows that look like a trailing
    summary line (e.g. "Total,,,,5050" -- mostly empty with one label cell
    and one number). Left in, these silently inflate sums and skew KPIs.
    Returns (cleaned_df, dropped_count).
    """
    before = len(df)
    df = df.dropna(how="all")

    summary_keywords = ("total", "grand total", "subtotal", "sum", "summary")

    def looks_like_summary_row(row):
        non_null = row.dropna()
        if len(non_null) > 3:
            return False
        text_cells = non_null.astype(str).str.lower()
        return any(any(kw in cell for kw in summary_keywords) for cell in text_cells)

    if len(df) > 0:
        summary_mask = df.apply(looks_like_summary_row, axis=1)
        df = df[~summary_mask]

    return df, before - len(df)


def get_excel_sheet_names(source):
    """Return sheet names for an uploaded Excel file without fully loading it."""
    return pd.ExcelFile(source).sheet_names


def read_any_file(source, sheet_name=None):
    """
    Read a CSV or Excel file from a path or an uploaded file-like object.
    Returns (dataframe, notes) where notes is a list of human-readable strings
    describing any auto-detection/cleanup that happened -- so nothing is
    silently guessed without the user being able to see what was assumed.

    Strategy for CSV: try the standard parse (comma, header=0) first, across
    encodings. Only if that produces something that looks wrong (one giant
    column, mostly "Unnamed" headers) does it fall back to sniffing the
    delimiter and skipping leading title/metadata rows. This order matters --
    an earlier version of this always ran the sniffing logic, which broke
    normal quote-heavy CSVs by miscounting commas inside quoted text fields.
    """
    name = getattr(source, "name", str(source))
    is_excel = name.lower().endswith((".xlsx", ".xls"))
    notes = []

    if is_excel:
        df = pd.read_excel(source, sheet_name=sheet_name if sheet_name else 0)
    else:
        raw_bytes = source.read()

        df = None
        used_encoding = None
        last_error = None
        for enc in ["utf-8-sig", "cp1252", "latin1"]:
            try:
                df = pd.read_csv(io.BytesIO(raw_bytes), encoding=enc)
                used_encoding = enc
                break
            except UnicodeDecodeError as e:
                last_error = e
                continue
            except pd.errors.ParserError as e:
                # File doesn't parse as standard comma-CSV at all (e.g. rows
                # before the header have a different field count) -- fall
                # through to the sniffing logic below instead of failing.
                last_error = e
                used_encoding = enc
                break

        if df is None and used_encoding is None:
            raise ValueError(f"Could not decode this file with any common encoding: {last_error}")

        if df is None or not _looks_sane(df):
            sample_lines, detected_encoding = _decode_sample(raw_bytes)
            delimiter, header_idx = _detect_delimiter_and_header(sample_lines)
            try:
                candidate = pd.read_csv(
                    io.BytesIO(raw_bytes),
                    encoding=used_encoding or detected_encoding,
                    sep=delimiter,
                    skiprows=header_idx,
                )
                if _looks_sane(candidate):
                    df = candidate
                    if delimiter != ",":
                        delim_name = {";": "semicolon", "\t": "tab", "|": "pipe"}.get(delimiter, delimiter)
                        notes.append(f"Detected {delim_name}-delimited file (not comma)")
                    if header_idx > 0:
                        notes.append(f"Skipped {header_idx} row(s) before the real header (titles/metadata)")
            except Exception:
                pass  # keep the original parse (if any) rather than fail outright

        if df is None:
            raise ValueError(f"Could not parse this file as CSV: {last_error}")

        df, dropped = _drop_junk_rows(df)
        if dropped > 0:
            notes.append(f"Dropped {dropped} blank/summary row(s) (e.g. empty rows or trailing 'Total' lines)")

    df.columns = [str(c).strip() for c in df.columns]
    return df, notes


SUPPORTED_TYPES = ["csv", "xlsx", "xls"]


def clean_numeric(series):
    """
    Robust numeric parsing shared across all analysis modules. Tries direct
    conversion first, then strips known currency/formatting characters
    (₹$€£¥, commas, % signs, whitespace) before retrying -- this is what
    correctly parses "2,245" or "₹1,299" or "45%" as numbers.
    Deliberately does NOT strip letters, so alphanumeric IDs like
    "B07JW9H4J1" are correctly left as non-numeric rather than corrupted.
    """
    direct = pd.to_numeric(series, errors="coerce")
    if direct.notna().mean() > 0.9:
        return direct

    stripped = series.astype(str).str.replace(r"[₹$€£¥,%\s]", "", regex=True)
    stripped = stripped.replace("", pd.NA)
    return pd.to_numeric(stripped, errors="coerce")
