# Secure Python execution sandbox for running generated data analysis code
import builtins as _builtins
import io
import os
import re
import sys
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .chart_extractor import extract_all_chart_pngs, extract_chart_png
from .code_sanitizer import sanitize_and_repair_code

try:
    import plotly
    import plotly.express as px
    import plotly.graph_objects as go
    import plotly.io as pio
except ImportError:
    plotly = px = go = pio = None

# List of permitted modules inside the code execution sandbox
ALLOWED_MODULES = {
    "pandas",
    "numpy",
    "matplotlib",
    "matplotlib.pyplot",
    "matplotlib.dates",
    "matplotlib.ticker",
    "plotly",
    "plotly.express",
    "plotly.graph_objects",
    "plotly.subplots",
    "plotly.io",
    "math",
    "datetime",
    "time",
    "re",
    "json",
    "random",
    "collections",
    "itertools",
    "functools",
    "statistics",
    "openpyxl",
}


# Restrict imports to safe data science libraries only
def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    root_pkg = name.split(".")[0]
    if name not in ALLOWED_MODULES and root_pkg not in ALLOWED_MODULES:
        raise ImportError(f"Import of module '{name}' is not permitted in the sandbox.")
    return _builtins.__import__(name, globals, locals, fromlist, level)


# Safe built-in functions dictionary permitted in the sandbox
SAFE_BUILTINS = {
    "__import__": safe_import,
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "float": float,
    "format": format,
    "int": int,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "print": print,
    "range": range,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
    "isinstance": isinstance,
    "issubclass": issubclass,
    "type": type,
    "map": map,
    "filter": filter,
    "hasattr": hasattr,
    "getattr": getattr,
    "iter": iter,
    "next": next,
    "chr": chr,
    "ord": ord,
    "True": True,
    "False": False,
    "None": None,
}


# Convert dataset filenames to safe Python variable names
def clean_var_name(name: str) -> str:
    base = os.path.splitext(name)[0]
    clean = re.sub(r"[^a-zA-Z0-9_]", "_", base).strip("_").lower()
    if not clean or clean[0].isdigit():
        clean = f"df_{clean}"
    return clean


# Build a clean isolated namespace dictionary for running user analysis code
def create_namespace(df_or_dfs: pd.DataFrame | dict[str, pd.DataFrame] | None) -> dict:
    namespace: dict[str, Any] = {
        "__builtins__": SAFE_BUILTINS,
        "pd": pd,
        "np": np,
        "plt": plt,
    }

    if px is not None:
        namespace["px"] = px
        namespace["go"] = go
        namespace["pio"] = pio

    if isinstance(df_or_dfs, dict):
        namespace["dfs"] = df_or_dfs
        if df_or_dfs:
            primary_df = next(iter(df_or_dfs.values()))
            namespace["df"] = primary_df

            for fname, d in df_or_dfs.items():
                vname = clean_var_name(fname)
                namespace[vname] = d
                namespace[f"df_{vname}"] = d
        else:
            namespace["df"] = None
    else:
        namespace["df"] = df_or_dfs
        namespace["dfs"] = {"dataset": df_or_dfs} if df_or_dfs is not None else {}

    return namespace


# Safely execute python code and capture console prints and generated charts
def execute_python(code: str, namespace: dict) -> dict:
    output: dict[str, Any] = {
        "success": False,
        "stdout": "",
        "result": None,
        "chart_png": None,
        "plotly_fig": None,
        "has_chart": False,
        "error": None,
    }

    stdout_buffer = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = stdout_buffer

    captured_chart_pngs: list[bytes] = []
    orig_close = plt.close
    orig_show = plt.show

    def intercept_close(*args, **kwargs):
        if plt.get_fignums():
            for fnum in list(plt.get_fignums()):
                try:
                    buf = io.BytesIO()
                    fig = plt.figure(fnum)
                    fig.savefig(buf, format="png", bbox_inches="tight", dpi=100)
                    buf.seek(0)
                    captured_chart_pngs.append(buf.getvalue())
                except Exception:
                    pass
        return orig_close(*args, **kwargs)

    def intercept_show(*args, **kwargs):
        fignums = list(plt.get_fignums())
        if fignums:
            for fnum in fignums:
                try:
                    buf = io.BytesIO()
                    fig = plt.figure(fnum)
                    fig.savefig(buf, format="png", bbox_inches="tight", dpi=100)
                    buf.seek(0)
                    captured_chart_pngs.append(buf.getvalue())
                    orig_close(fnum)
                except Exception:
                    pass

    plt.close = intercept_close
    plt.show = intercept_show

    def _is_plotly_fig(obj: Any) -> bool:
        return (
            obj is not None
            and hasattr(obj, "to_dict")
            and hasattr(obj, "data")
            and hasattr(obj, "layout")
        )

    existing_plotly_ids = {
        id(v)
        for v in namespace.values()
        if _is_plotly_fig(v)
    }

    captured_plotly_figs: list[Any] = []
    orig_pio_show = getattr(pio, "show", None) if pio is not None else None

    if pio is not None and orig_pio_show is not None:
        def intercept_pio_show(fig=None, *args, **kwargs):
            nonlocal captured_plotly_figs
            if _is_plotly_fig(fig) and not any(id(fig) == id(x) for x in captured_plotly_figs):
                captured_plotly_figs.append(fig)
            return None

        pio.show = intercept_pio_show

    try:
        orig_close("all")

        sanitized_code = sanitize_and_repair_code(code)

        exec(sanitized_code, namespace)

        captured_stdout = stdout_buffer.getvalue().strip()
        output["stdout"] = captured_stdout

        for cand_name in ["fig", "fig1", "fig2", "fig3", "figure", "chart", "plot"]:
            cand = namespace.get(cand_name)
            if (
                _is_plotly_fig(cand)
                and id(cand) not in existing_plotly_ids
                and not any(id(cand) == id(x) for x in captured_plotly_figs)
            ):
                captured_plotly_figs.append(cand)

        for k, v in namespace.items():
            if k not in ("px", "go", "pio", "plt", "pd", "np", "df", "dfs") and _is_plotly_fig(v):
                if id(v) not in existing_plotly_ids and not any(id(v) == id(x) for x in captured_plotly_figs):
                    captured_plotly_figs.append(v)

        for pfig in captured_plotly_figs:
            if not getattr(pfig, "_png_bytes", None):
                try:
                    pfig._png_bytes = pfig.to_image(format="png", width=900, height=450)
                except Exception:
                    pass

        extracted_pngs = captured_chart_pngs or extract_all_chart_pngs()

        all_captured: list[Any] = []
        all_captured.extend(captured_plotly_figs)
        all_captured.extend(extracted_pngs)

        output["all_charts"] = all_captured
        output["plotly_fig"] = captured_plotly_figs[0] if captured_plotly_figs else None
        output["chart_png"] = (
            extracted_pngs[0]
            if extracted_pngs
            else (getattr(captured_plotly_figs[0], "_png_bytes", None) if captured_plotly_figs else None)
        )
        output["has_chart"] = bool(all_captured)
        output["success"] = True

    except Exception as e:
        output["error"] = f"{type(e).__name__}: {e!s}"
        extracted_pngs = captured_chart_pngs or extract_all_chart_pngs()
        all_captured = []
        all_captured.extend(captured_plotly_figs)
        all_captured.extend(extracted_pngs)
        output["all_charts"] = all_captured
        output["chart_png"] = extracted_pngs[0] if extracted_pngs else None
        output["plotly_fig"] = captured_plotly_figs[0] if captured_plotly_figs else None
        output["has_chart"] = bool(all_captured)
        orig_close("all")

    finally:
        plt.close = orig_close
        plt.show = orig_show
        if pio is not None and orig_pio_show is not None:
            pio.show = orig_pio_show
        sys.stdout = old_stdout

    return output


# Backward compatibility aliases
_clean_var_name = clean_var_name
_extract_all_chart_pngs = extract_all_chart_pngs
_extract_chart_png = extract_chart_png
