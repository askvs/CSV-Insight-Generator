# File loading functions for CSV, Excel, and JSON files
import os
import pandas as pd
from .profiler_utils import downcast_numerics


# Read JSON files into a dataframe
def load_json_data(path_or_buffer) -> pd.DataFrame:
    import json

    if hasattr(path_or_buffer, "seek"):
        path_or_buffer.seek(0)

    try:
        data = json.load(path_or_buffer)
        if isinstance(data, list):
            return pd.json_normalize(data)
        if isinstance(data, dict):
            list_keys = [k for k, v in data.items() if isinstance(v, list) and v and isinstance(v[0], dict)]
            if len(list_keys) == 1:
                return pd.json_normalize(data[list_keys[0]])
            return pd.json_normalize(data)
    except Exception:
        pass

    if hasattr(path_or_buffer, "seek"):
        path_or_buffer.seek(0)
    try:
        return pd.read_json(path_or_buffer)
    except ValueError:
        if hasattr(path_or_buffer, "seek"):
            path_or_buffer.seek(0)
        return pd.read_json(path_or_buffer, lines=True)


# Load a single file into a dataframe
def load_dataset(path_or_buffer, filename: str = "", large_threshold: int = 500_000):
    fname = filename or getattr(path_or_buffer, "name", "") or ""
    ext = os.path.splitext(fname)[1].lower()

    try:
        if ext in [".xlsx", ".xls"]:
            excel_data = pd.read_excel(path_or_buffer, sheet_name=None)
            if isinstance(excel_data, dict):
                first_sheet = next(iter(excel_data.keys()))
                df = excel_data[first_sheet]
            else:
                df = excel_data
        elif ext == ".json":
            df = load_json_data(path_or_buffer)
        else:
            df = pd.read_csv(path_or_buffer, low_memory=False)
    except Exception as e:
        format_name = ext.replace(".", "").upper() if ext else "data"
        raise ValueError(f"Could not read {format_name} file: {e}")

    was_truncated = False
    if len(df) > large_threshold:
        df = df.head(large_threshold)
        was_truncated = True

    df = downcast_numerics(df)
    return df, was_truncated


# Helper for backward compatibility when loading a single CSV
def load_csv(path_or_buffer, large_threshold: int = 500_000):
    return load_dataset(path_or_buffer, filename="data.csv", large_threshold=large_threshold)


# Load multiple files or multi-sheet Excel files into a dictionary of dataframes
def load_multiple_files(files_or_buffers, large_threshold: int = 500_000) -> dict[str, tuple[pd.DataFrame, bool]]:
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
                        results[clean_key] = (downcast_numerics(sheet_df), was_trunc)
                    continue
            except Exception:
                pass

        if hasattr(item, "seek"):
            item.seek(0)
        df, was_trunc = load_dataset(item, filename=fname, large_threshold=large_threshold)
        results[fname] = (df, was_trunc)

    return results
