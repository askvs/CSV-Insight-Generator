# Re-export notebook functions for backward compatibility
from .notebooks.generator import _to_source_lines, generate_jupyter_notebook
from .notebooks.notebook_builder import create_chart_output_cells, to_source_lines

__all__ = [
    "_to_source_lines",
    "create_chart_output_cells",
    "generate_jupyter_notebook",
    "to_source_lines",
]
