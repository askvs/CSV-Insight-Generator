import numpy as np
import pandas as pd

# 1. Load CSV with smart defaults


def load_csv(path_or_buffer, large_threshold=500_000):
    """
    Load a CSV into a pandas DataFrame.
    - Tries normal loading first.
    - If the file has more rows than large_threshold, falls back to
      chunked reading (reads first large_threshold rows only for profiling).
    - Downcasts numeric columns to save memory.

    Returns: (df, was_truncated)
        df             — the loaded DataFrame
        was_truncated  — True if we only loaded a sample of a huge file
    """
    # First, try normal load
    try:
        df = pd.read_csv(path_or_buffer, low_memory=False)
    except Exception as e:
        raise ValueError(f"Could not read the CSV file: {e}")

    was_truncated = False

    # If too large, keep only the first `large_threshold` rows for profiling
    if len(df) > large_threshold:
        df = df.head(large_threshold)
        was_truncated = True

    # Downcast numeric columns to save memory
    df = _downcast_numerics(df)

    return df, was_truncated


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
