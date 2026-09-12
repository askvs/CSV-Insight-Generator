# Profile dataset columns and build summary statistics
import json
import pandas as pd
from .profiler_utils import downcast_numerics, safe_nunique, safe_round, safe_unique_list

# Maximum number of detailed columns to include in the profile
TOP_N_COLUMNS = 30


# Rank and pick the most useful columns for data analysis
def pick_interesting_columns(df: pd.DataFrame, top_n: int) -> list:
    scores = {}
    for col in df.columns:
        s = df[col]
        score = 0.0
        n_unique = safe_nunique(s)

        if not pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_datetime64_any_dtype(s):
            if 2 <= n_unique <= 60:
                score += 4.5
            elif n_unique > 60:
                score += 1.0

        if pd.api.types.is_numeric_dtype(s):
            score += 3.0
            if 2 <= n_unique <= 50:
                score += 1.5

        if pd.api.types.is_datetime64_any_dtype(s):
            score += 3.0

        null_frac = s.isna().mean()
        score += (1.0 - null_frac) * 2.0
        scores[col] = score

    ranked = sorted(scores, key=lambda col: scores[col], reverse=True)
    return ranked[:top_n]


# Calculate statistics for a single column
def profile_column(series: pd.Series) -> dict:
    n_uniq = safe_nunique(series)
    info = {
        "dtype": str(series.dtype),
        "null_count": int(series.isna().sum()),
        "null_pct": float(round(series.isna().mean() * 100, 1)),
        "n_unique": n_uniq,
    }

    if pd.api.types.is_numeric_dtype(series):
        desc = series.describe()
        info["stats"] = {
            "mean": safe_round(desc.get("mean")),
            "std": safe_round(desc.get("std")),
            "min": safe_round(desc.get("min")),
            "25%": safe_round(desc.get("25%")),
            "50%": safe_round(desc.get("50%")),
            "75%": safe_round(desc.get("75%")),
            "max": safe_round(desc.get("max")),
        }
    elif pd.api.types.is_datetime64_any_dtype(series):
        non_null = series.dropna()
        if len(non_null) > 0:
            info["stats"] = {
                "min": str(non_null.min()),
                "max": str(non_null.max()),
            }
    else:
        top_values = series.value_counts().head(8)
        info["top_values_by_row_count"] = {
            str(k): int(v) for k, v in top_values.items()
        }
        if n_uniq <= 30:
            info["categories"] = safe_unique_list(series, 30)

        if series.dtype == object:
            sample = series.dropna().head(1000)
            if len(sample) > 0:
                info["avg_str_len"] = round(sample.astype(str).str.len().mean(), 1)

    return info


# Build a complete profile summary for a single dataframe
def profile_dataframe(df: pd.DataFrame, was_truncated: bool = False) -> dict:
    n_rows, n_cols = df.shape

    total_cells = n_rows * n_cols
    total_missing = int(df.isna().sum().sum()) if total_cells > 0 else 0
    total_missing_pct = round((total_missing / total_cells) * 100, 1) if total_cells > 0 else 0.0

    profile = {
        "shape": {"rows": n_rows, "columns": n_cols},
        "memory_mb": round(
            df.memory_usage(deep=True).sum() / 1_048_576, 2
        ),
        "truncated": was_truncated,
        "missing_values": {
            "total_missing": total_missing,
            "total_cells": total_cells,
            "total_missing_percentage": total_missing_pct,
        },
    }

    if n_cols <= TOP_N_COLUMNS:
        detailed_cols = list(df.columns)
        brief_cols = []
    else:
        detailed_cols = pick_interesting_columns(df, TOP_N_COLUMNS)
        brief_cols = [c for c in df.columns if c not in detailed_cols]

    profile["columns"] = {}
    for col in detailed_cols:
        profile["columns"][col] = profile_column(df[col])

    if brief_cols:
        profile["other_columns"] = []
        for c in brief_cols:
            n_unq = safe_nunique(df[c])
            col_info = {"name": c, "dtype": str(df[c].dtype), "n_unique": n_unq}
            if n_unq <= 30:
                col_info["unique_values"] = safe_unique_list(df[c], 30)
            profile["other_columns"].append(col_info)

    return profile


# Build profiles for multiple dataframes and find common join keys
def profile_datasets(dfs: dict[str, pd.DataFrame], was_truncated_dict: dict[str, bool] | None = None) -> dict:
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


# Print the profile summary in formatted JSON
def print_profile(profile: dict):
    print(json.dumps(profile, indent=2, default=str))


# Backward compatibility aliases
_downcast_numerics = downcast_numerics
_safe_nunique = safe_nunique
_safe_unique_list = safe_unique_list
_safe_round = safe_round
_pick_interesting_columns = pick_interesting_columns
_profile_column = profile_column
