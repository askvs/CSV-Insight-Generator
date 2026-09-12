# CSV Insight Agent package entry point
from .agent import CSVInsightAgent

# Analytics package imports
from .analytics import (
    TOP_N_COLUMNS,
    downcast_numerics,
    load_csv,
    load_dataset,
    load_json_data,
    load_multiple_files,
    pick_interesting_columns,
    print_profile,
    profile_column,
    profile_dataframe,
    profile_datasets,
    safe_nunique,
    safe_round,
    safe_unique_list,
)

# Execution sandbox package imports
from .execution import (
    clean_var_name,
    create_namespace,
    execute_python,
    extract_all_chart_pngs,
    extract_chart_png,
    sanitize_and_repair_code,
)

# Notebooks package imports
from .notebooks import (
    create_chart_output_cells,
    generate_jupyter_notebook,
    to_source_lines,
)

# Reporting package imports
from .reporting import (
    NumberedCanvas,
    clean_inline,
    format_code_line,
    format_markdown_for_reportlab,
    generate_fallback_chart,
    generate_pdf_report,
    safe_paragraph,
    sanitize_text_for_pdf,
)

__all__ = [
    "CSVInsightAgent",
    "NumberedCanvas",
    "TOP_N_COLUMNS",
    "clean_inline",
    "clean_var_name",
    "create_chart_output_cells",
    "create_namespace",
    "downcast_numerics",
    "execute_python",
    "extract_all_chart_pngs",
    "extract_chart_png",
    "format_code_line",
    "format_markdown_for_reportlab",
    "generate_fallback_chart",
    "generate_jupyter_notebook",
    "generate_pdf_report",
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
    "safe_paragraph",
    "safe_round",
    "safe_unique_list",
    "sanitize_and_repair_code",
    "sanitize_text_for_pdf",
    "to_source_lines",
]
