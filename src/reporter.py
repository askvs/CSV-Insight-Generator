# Re-export reporting functions for backward compatibility
from .reporting.chart_generator import generate_fallback_chart
from .reporting.generator import (
    _clean_inline,
    _format_code_line,
    _format_markdown_for_reportlab,
    _generate_fallback_chart,
    _safe_paragraph,
    _sanitize_text_for_pdf,
    generate_pdf_report,
)
from .reporting.markdown_parser import format_markdown_for_reportlab
from .reporting.pdf_canvas import NumberedCanvas
from .reporting.pdf_formatting import (
    clean_inline,
    format_code_line,
    safe_paragraph,
    sanitize_text_for_pdf,
)

__all__ = [
    "NumberedCanvas",
    "_clean_inline",
    "_format_code_line",
    "_format_markdown_for_reportlab",
    "_generate_fallback_chart",
    "_safe_paragraph",
    "_sanitize_text_for_pdf",
    "clean_inline",
    "format_code_line",
    "format_markdown_for_reportlab",
    "generate_fallback_chart",
    "generate_pdf_report",
    "safe_paragraph",
    "sanitize_text_for_pdf",
]
