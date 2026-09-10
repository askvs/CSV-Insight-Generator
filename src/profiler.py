import os
import numpy as np
import pandas as pd

# 1. Multi-Format Dataset Loader (CSV, Excel, Parquet, JSON)


def load_dataset(path_or_buffer, filename: str = "", large_threshold: int = 500_000):
    """
    Load any supported data file (CSV, Excel, Parquet, JSON) into a pandas DataFrame.
    
    Supports:
      - .csv: Comma-separated values
      - .xlsx, .xls: Excel spreadsheets (handles active or single sheets)
      - .parquet: Columnar parquet storage
      - .json: Structured records or tabular JSON
    
    Returns: (df, was_truncated)
    """
    # Detect file extension
    fname = filename or getattr(path_or_buffer, "name", "") or ""
    ext = os.path.splitext(fname)[1].lower()

    try:
        if ext in [".xlsx", ".xls"]:
            # If Excel, read first sheet by default (or active sheet)
            excel_data = pd.read_excel(path_or_buffer, sheet_name=None)
            if isinstance(excel_data, dict):
                first_sheet = next(iter(excel_data.keys()))
                df = excel_data[first_sheet]
            else:
                df = excel_data
        elif ext == ".parquet":
            df = pd.read_parquet(path_or_buffer)
        elif ext == ".json":
            try:
                df = pd.read_json(path_or_buffer)
            except ValueError:
                # Try reading line-delimited JSON
                if hasattr(path_or_buffer, "seek"):
                    path_or_buffer.seek(0)
                df = pd.read_json(path_or_buffer, lines=True)
        else:
            # Default to CSV parser
            df = pd.read_csv(path_or_buffer, low_memory=False)
    except Exception as e:
        format_name = ext.replace(".", "").upper() if ext else "data"
        raise ValueError(f"Could not read {format_name} file: {e}")

    was_truncated = False
    if len(df) > large_threshold:
        df = df.head(large_threshold)
        was_truncated = True

    df = _downcast_numerics(df)
    return df, was_truncated


def load_csv(path_or_buffer, large_threshold: int = 500_000):
    """Backwards-compatible wrapper for load_dataset."""
    return load_dataset(path_or_buffer, filename="data.csv", large_threshold=large_threshold)


def load_multiple_files(files_or_buffers, large_threshold: int = 500_000) -> dict[str, tuple[pd.DataFrame, bool]]:
    """
    Load multiple uploaded files or file buffers into a dictionary of DataFrames.
    
    If an Excel file contains multiple sheets, each sheet is loaded as a separate table.
    
    Returns: dict mapping dataset_name -> (DataFrame, was_truncated)
    """
    results: dict[str, tuple[pd.DataFrame, bool]] = {}

    for item in files_or_buffers:
        fname = getattr(item, "name", "") or f"dataset_{len(results) + 1}.csv"
        ext = os.path.splitext(fname)[1].lower()
        base_name = os.path.splitext(fname)[0]

        if ext in [".xlsx", ".xls"]:
            try:
                excel_sheets = pd.read_excel(item, sheet_name=None)
                if isinstance(excel_sheets, dict) and len(excel_sheets) > 1:
                    for s_name, sheet_df in excel_sheets.items():
                        clean_key = f"{base_name}_{s_name}".strip()
                        was_trunc = False
                        if len(sheet_df) > large_threshold:
                            sheet_df = sheet_df.head(large_threshold)
                            was_trunc = True
                        results[clean_key] = (_downcast_numerics(sheet_df), was_trunc)
                    continue
            except Exception:
                pass  # fallback to standard loader below

        if hasattr(item, "seek"):
            item.seek(0)
        df, was_trunc = load_dataset(item, filename=fname, large_threshold=large_threshold)
        results[fname] = (df, was_trunc)

    return results


def _downcast_numerics(df):
    """Downcast int and float columns to their smallest safe dtype."""
    for col in df.select_dtypes(include=["int"]).columns:
        df[col] = pd.to_numeric(df[col], downcast="integer")
    for col in df.select_dtypes(include=["float"]).columns:
        df[col] = pd.to_numeric(df[col], downcast="float")
    return df


# 2. Build profile dictionary

# When a dataset has more columns than this, we only include detailed stats
# for the top-N most "interesting" columns and summarize the rest briefly.
TOP_N_COLUMNS = 20


def profile_dataframe(df, was_truncated=False):
    """
    Build a compact profile dictionary from a DataFrame.

    The profile includes:
      - shape (rows, columns)
      - memory usage
      - per-column stats (dtype, nulls, unique count, and type-specific stats)
      - for wide datasets: detailed stats for top-N columns, brief for the rest

    Returns: dict
    """
    n_rows, n_cols = df.shape

    profile = {
        "shape": {"rows": n_rows, "columns": n_cols},
        "memory_mb": round(
            df.memory_usage(deep=True).sum() / 1_048_576, 2
        ),  # bytes into Megabytes
        "truncated": was_truncated,
    }

    # Decide which columns get full detail vs. brief summary
    if n_cols <= TOP_N_COLUMNS:
        detailed_cols = list(df.columns)
        brief_cols = []
    else:
        detailed_cols = _pick_interesting_columns(df, TOP_N_COLUMNS)
        brief_cols = [c for c in df.columns if c not in detailed_cols]

    # Build detailed column profiles
    profile["columns"] = {}
    for col in detailed_cols:
        profile["columns"][col] = _profile_column(df[col])

    # Brief summaries for the rest (wide datasets)
    if brief_cols:
        profile["other_columns"] = [
            {"name": c, "dtype": str(df[c].dtype)} for c in brief_cols
        ]

    return profile


def profile_datasets(dfs: dict[str, pd.DataFrame], was_truncated_dict: dict[str, bool] | None = None) -> dict:
    """
    Profile multiple DataFrames and identify cross-table relationships.
    
    Returns a unified profile dictionary containing:
      - is_multi_dataset: bool
      - summary: overall stats across all tables
      - datasets: {dataset_name: single_profile_dict}
      - common_keys_for_joins: shared column names that can be used to join tables
      - (if single dataset, also includes top-level shape, columns, memory_mb for full backward compatibility)
    """
    if was_truncated_dict is None:
        was_truncated_dict = {}

    if not dfs:
        return {"shape": {"rows": 0, "columns": 0}, "memory_mb": 0.0, "datasets": {}}

    if len(dfs) == 1:
        name, single_df = next(iter(dfs.items()))
        single_prof = profile_dataframe(single_df, was_truncated=was_truncated_dict.get(name, False))
        p = dict(single_prof)
        p["dataset_name"] = name
        p["is_multi_dataset"] = False
        p["datasets"] = {name: single_prof}
        return p

    datasets_profile = {}
    col_to_datasets: dict[str, list[str]] = {}
    total_rows = 0
    total_memory = 0.0

    for name, df_item in dfs.items():
        trunc = was_truncated_dict.get(name, False)
        sub_prof = profile_dataframe(df_item, was_truncated=trunc)
        datasets_profile[name] = sub_prof
        total_rows += len(df_item)
        total_memory += sub_prof.get("memory_mb", 0.0)

        for col in df_item.columns:
            clean_c = str(col).strip().lower()
            if clean_c not in col_to_datasets:
                col_to_datasets[clean_c] = []
            col_to_datasets[clean_c].append(name)

    # Detect shared columns across tables for joins
    shared_keys = []
    for c, ds_list in col_to_datasets.items():
        if len(ds_list) > 1:
            shared_keys.append({"column": c, "tables": ds_list})

    multi_profile = {
        "is_multi_dataset": True,
        "summary": {
            "total_datasets": len(dfs),
            "dataset_names": list(dfs.keys()),
            "total_rows": total_rows,
            "total_memory_mb": round(total_memory, 2),
        },
        "datasets": datasets_profile,
        "common_keys_for_joins": shared_keys,
        "shape": {"rows": total_rows, "columns": sum(len(d.columns) for d in dfs.values())},
        "memory_mb": round(total_memory, 2),
        "truncated": any(was_truncated_dict.values()),
    }

    return multi_profile


def _pick_interesting_columns(df, top_n):
    """
    Rank columns by "interestingness" and return the top-N names.

    Scoring (simple heuristic):
      - Numeric columns score higher (more analysis potential)
      - Columns with fewer nulls score higher
      - Datetime-like columns score higher
      - Columns with moderate unique counts score higher than near-constant
        or near-unique columns
    """
    scores = {}
    for col in df.columns:
        s = df[col]
        score = 0.0

        # Prefer numeric
        if pd.api.types.is_numeric_dtype(s):
            score += 3.0
        # Prefer datetime
        if pd.api.types.is_datetime64_any_dtype(s):
            score += 2.0

        # Penalise high null %
        null_frac = s.isna().mean()
        score += (1.0 - null_frac) * 2.0

        # Prefer moderate cardinality (not 1, not all-unique)
        n_unique = s.nunique()
        if 2 <= n_unique <= 50:
            score += 2.0
        elif 50 < n_unique <= 500:
            score += 1.0

        scores[col] = score

    ranked = sorted(scores, key=lambda col: scores[col], reverse=True)
    return ranked[:top_n]


def _profile_column(series):
    """Return a stats dict for one column."""
    info = {
        "dtype": str(series.dtype),
        "null_count": int(series.isna().sum()),
        "null_pct": round(series.isna().mean() * 100, 1),
        "n_unique": int(series.nunique()),
    }

    # --- Numeric columns ---
    if pd.api.types.is_numeric_dtype(series):
        desc = series.describe()
        info["stats"] = {
            "mean": _safe_round(desc.get("mean")),
            "std": _safe_round(desc.get("std")),
            "min": _safe_round(desc.get("min")),
            "25%": _safe_round(desc.get("25%")),
            "50%": _safe_round(desc.get("50%")),
            "75%": _safe_round(desc.get("75%")),
            "max": _safe_round(desc.get("max")),
        }

    # --- Datetime columns ---
    elif pd.api.types.is_datetime64_any_dtype(series):
        non_null = series.dropna()
        if len(non_null) > 0:
            info["stats"] = {
                "min": str(non_null.min()),
                "max": str(non_null.max()),
            }

    # --- Categorical / text columns ---
    else:
        top_values = series.value_counts().head(5)
        info["top_values_by_row_count"] = {
            str(k): int(v) for k, v in top_values.items()
        }
        # Average string length (useful indicator)
        if series.dtype == object:
            sample = series.dropna().head(1000)
            if len(sample) > 0:
                info["avg_str_len"] = round(sample.astype(str).str.len().mean(), 1)

    return info


def _safe_round(value, decimals=3):
    """Round a value if it's a number, otherwise return as-is."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "N/A"
    try:
        return round(float(value), decimals)
    except (TypeError, ValueError):
        return value


# 3. print helper (for testing / debugging)


def print_profile(profile):
    """Print the profile in a human-readable way."""
    import json

    print(json.dumps(profile, indent=2, default=str))
