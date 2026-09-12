# Re-export analytics functions for backward compatibility
from .analytics.loader import (
    load_csv,
    load_dataset,
    load_json_data,
    load_multiple_files,
)
from .analytics.profiler import (
    TOP_N_COLUMNS,
    _downcast_numerics,
    _pick_interesting_columns,
    _profile_column,
    _safe_nunique,
    _safe_round,
    _safe_unique_list,
    pick_interesting_columns,
    print_profile,
    profile_column,
    profile_dataframe,
    profile_datasets,
)
from .analytics.profiler_utils import (
    downcast_numerics,
    safe_nunique,
    safe_round,
    safe_unique_list,
)

__all__ = [
    "TOP_N_COLUMNS",
    "_downcast_numerics",
    "_pick_interesting_columns",
    "_profile_column",
    "_safe_nunique",
    "_safe_round",
    "_safe_unique_list",
    "downcast_numerics",
    "load_csv",
    "load_dataset",
    "load_json_data",
    "load_multiple_files",
    "pick_interesting_columns",
    "print_profile",
    "profile_column",
    "profile_dataframe",
    "profile_datasets",
    "safe_nunique",
    "safe_round",
    "safe_unique_list",
]
