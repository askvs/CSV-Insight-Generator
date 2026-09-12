# Helper functions for dataset profiling
import numpy as np
import pandas as pd


# Safely count unique values even if column contains unhashable objects
def safe_nunique(series: pd.Series) -> int:
    try:
        return int(series.nunique())
    except TypeError:
        return int(series.map(lambda x: str(x) if isinstance(x, (dict, list, set)) else x).nunique())


# Safely get a sample list of unique values
def safe_unique_list(series: pd.Series, limit: int = 30) -> list[str]:
    try:
        return [str(x) for x in series.dropna().unique()[:limit]]
    except TypeError:
        cleaned = series.map(lambda x: str(x) if isinstance(x, (dict, list, set)) else x)
        return [str(x) for x in cleaned.dropna().unique()[:limit]]


# Safely round float numbers to avoid long decimal places
def safe_round(value, decimals=3):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "N/A"
    try:
        return round(float(value), decimals)
    except (TypeError, ValueError):
        return value


# Downcast numeric columns to save memory
def downcast_numerics(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.select_dtypes(include=["int"]).columns:
        df[col] = pd.to_numeric(df[col], downcast="integer")
    for col in df.select_dtypes(include=["float"]).columns:
        df[col] = pd.to_numeric(df[col], downcast="float")
    return df
