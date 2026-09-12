# Re-export sandbox functions for backward compatibility
from .execution.chart_extractor import (
    _extract_all_chart_pngs,
    _extract_chart_png,
    extract_all_chart_pngs,
    extract_chart_png,
)
from .execution.code_sanitizer import sanitize_and_repair_code
from .execution.sandbox import (
    _clean_var_name,
    clean_var_name,
    create_namespace,
    execute_python,
)

__all__ = [
    "_clean_var_name",
    "_extract_all_chart_pngs",
    "_extract_chart_png",
    "clean_var_name",
    "create_namespace",
    "execute_python",
    "extract_all_chart_pngs",
    "extract_chart_png",
    "sanitize_and_repair_code",
]
