# Jupyter notebook cell generator helpers
import base64
import json
from typing import Any


# Split multiline text into lines for Jupyter Notebook JSON format
def to_source_lines(text: str) -> list[str]:
    if not text:
        return []
    return text.splitlines(keepends=True)


# Convert Plotly or Matplotlib charts into Jupyter Notebook cell output objects
def create_chart_output_cells(charts: list[Any]) -> list[dict[str, Any]]:
    code_outputs: list[dict[str, Any]] = []
    for chart in charts:
        if hasattr(chart, "to_json"):
            try:
                plotly_spec = json.loads(chart.to_json())
            except Exception:
                plotly_spec = chart.to_dict()
            code_outputs.append(
                {
                    "output_type": "display_data",
                    "data": {
                        "application/vnd.plotly.v1+json": plotly_spec,
                        "text/plain": ["<Figure object with Plotly interactive visualization>"],
                    },
                    "metadata": {},
                }
            )
        elif hasattr(chart, "to_dict") and hasattr(chart, "data"):
            plotly_spec = chart.to_dict()
            code_outputs.append(
                {
                    "output_type": "display_data",
                    "data": {
                        "application/vnd.plotly.v1+json": plotly_spec,
                        "text/plain": ["<Figure object with Plotly interactive visualization>"],
                    },
                    "metadata": {},
                }
            )
        elif isinstance(chart, bytes):
            b64_png = base64.b64encode(chart).decode("utf-8")
            code_outputs.append(
                {
                    "output_type": "display_data",
                    "data": {
                        "image/png": b64_png,
                        "text/plain": ["<Figure size 900x450 with 1 Axes>"],
                    },
                    "metadata": {},
                }
            )
    return code_outputs
