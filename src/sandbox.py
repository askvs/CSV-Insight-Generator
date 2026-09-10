import builtins as _builtins
import io
import json
import os
import re
import sys
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

try:
    import plotly
    import plotly.express as px
    import plotly.graph_objects as go
    import plotly.io as pio
except ImportError:
    plotly = px = go = pio = None

# Allowed modules for sandbox imports
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


def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    """Restricted __import__ function permitting data science libraries while blocking system modules."""
    root_pkg = name.split(".")[0]
    if name not in ALLOWED_MODULES and root_pkg not in ALLOWED_MODULES:
        raise ImportError(f"Import of module '{name}' is not permitted in the sandbox.")
    return _builtins.__import__(name, globals, locals, fromlist, level)


# 1. Allowed built-in functions
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
    "True": True,
    "False": False,
    "None": None,
}


def _clean_var_name(name: str) -> str:
    """Converts a filename or table title to a valid python variable name."""
    base = os.path.splitext(name)[0]
    clean = re.sub(r"[^a-zA-Z0-9_]", "_", base).strip("_").lower()
    if not clean or clean[0].isdigit():
        clean = f"df_{clean}"
    return clean


def create_namespace(df_or_dfs: pd.DataFrame | dict[str, pd.DataFrame] | None) -> dict:
    """
    Create a fresh namespace dictionary for a session.
    Supports single DataFrame or dictionary of multiple DataFrames.
    Populates `df`, `dfs`, clean table aliases, `pd`, `np`, `plt`, `px`, `go`, and safe builtins.
    """
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
            # Bind the first dataset as default 'df'
            primary_df = next(iter(df_or_dfs.values()))
            namespace["df"] = primary_df

            # Auto-bind clean variable names for each dataset (e.g., 'orders' and 'df_orders')
            for fname, d in df_or_dfs.items():
                vname = _clean_var_name(fname)
                namespace[vname] = d
                namespace[f"df_{vname}"] = d
        else:
            namespace["df"] = None
    else:
        namespace["df"] = df_or_dfs
        namespace["dfs"] = {"dataset": df_or_dfs} if df_or_dfs is not None else {}

    return namespace


def sanitize_and_repair_code(code: str) -> str:
    """Sanitizes Python code and repairs trailing unterminated string literals or EOF cuts."""
    if not code or not isinstance(code, str):
        return ""

    code = code.strip()

    # Strip markdown code fences if wrapped
    if code.startswith("```python"):
        code = code[len("```python") :].strip()
    elif code.startswith("```"):
        code = code[3:].strip()
    if code.endswith("```"):
        code = code[:-3].strip()

    # If raw JSON string was passed instead of pure python code
    if code.startswith('{"code"') or code.startswith("{\n  \"code\"") or '"code":' in code[:30]:
        try:
            parsed = json.loads(code)
            if isinstance(parsed, dict) and "code" in parsed:
                code = parsed["code"]
        except Exception:
            match = re.search(r'"code"\s*:\s*"([\s\S]*)$', code)
            if match:
                val = match.group(1)
                val = re.sub(r'"\s*\}?\s*$', "", val)
                val = (
                    val.replace("\\n", "\n")
                    .replace('\\"', '"')
                    .replace("\\t", "\t")
                    .replace("\\\\", "\\")
                )
                code = val.strip()

    # Attempt compilation; if trailing unterminated string literal / EOF, repair by dropping cut-off line
    lines = code.splitlines()
    for _ in range(5):
        try:
            compile("\n".join(lines), "<string>", "exec")
            return "\n".join(lines)
        except SyntaxError as e:
            err_msg = str(e)
            if (
                "unterminated string literal" in err_msg
                or "unexpected EOF" in err_msg
                or "EOF while scanning" in err_msg
            ):
                if lines:
                    lines.pop()
                else:
                    break
            else:
                break

    return code


def execute_python(code: str, namespace: dict) -> dict:
    """
    Execute python code string inside `namespace`.

    Returns dict:
      {
        "success": bool,
        "stdout": str,        # any print() outputs
        "result": str|None,   # string representation of last expression if any
        "chart_png": bytes,   # PNG image bytes if matplotlib figure was generated (or static plotly export)
        "plotly_fig": Any,    # Plotly Figure object if generated
        "has_chart": bool,    # True if either matplotlib or plotly figure was generated
        "error": str|None,    # error message / traceback if execution failed
      }
    """
    # Prepared output structure
    output: dict[str, Any] = {
        "success": False,
        "stdout": "",
        "result": None,
        "chart_png": None,
        "plotly_fig": None,
        "has_chart": False,
        "error": None,
    }

    # Intercept print statements
    stdout_buffer = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = stdout_buffer

    # Fail-safe chart capture hooks in case code calls plt.show() or plt.close()
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
        # When plt.show() is called, grab the active figures, save them, and close them
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

    # Snapshot existing plotly figures in namespace so earlier turns' figures aren't falsely captured
    existing_plotly_ids = {
        id(v)
        for v in namespace.values()
        if _is_plotly_fig(v)
    }

    # Plotly interception hook
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
        # Clear any existing matplotlib figures before running
        orig_close("all")

        # Sanitize and repair code if cut off or malformed
        sanitized_code = sanitize_and_repair_code(code)

        # Execute code in persistent namespace
        exec(sanitized_code, namespace)

        # Retrieve any captured stdout prints
        captured_stdout = stdout_buffer.getvalue().strip()
        output["stdout"] = captured_stdout

        # Check all variables in namespace for Plotly figures (prioritizing common names)
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

        # Pre-cache static PNG bytes on all captured Plotly figures for fast, reliable PDF export
        for pfig in captured_plotly_figs:
            if not getattr(pfig, "_png_bytes", None):
                try:
                    pfig._png_bytes = pfig.to_image(format="png", width=900, height=450)
                except Exception:
                    pass

        # Check if matplotlib charts were generated
        extracted_pngs = captured_chart_pngs or _extract_all_chart_pngs()

        # Build list of all charts (both Plotly and Matplotlib)
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
        # Capture error & traceback formatted string for the LLM self-correction
        output["error"] = f"{type(e).__name__}: {e!s}"
        extracted_pngs = captured_chart_pngs or _extract_all_chart_pngs()
        all_captured = []
        all_captured.extend(captured_plotly_figs)
        all_captured.extend(extracted_pngs)
        output["all_charts"] = all_captured
        output["chart_png"] = extracted_pngs[0] if extracted_pngs else None
        output["plotly_fig"] = captured_plotly_figs[0] if captured_plotly_figs else None
        output["has_chart"] = bool(all_captured)
        orig_close("all")

    finally:
        # Restore normal functions and stdout stream
        plt.close = orig_close
        plt.show = orig_show
        if pio is not None and orig_pio_show is not None:
            pio.show = orig_pio_show
        sys.stdout = old_stdout

    return output


def _extract_all_chart_pngs() -> list[bytes]:
    """Save all active matplotlib figures to PNG bytes and close them."""
    fig_nums = list(plt.get_fignums())
    if not fig_nums:
        return []

    pngs = []
    for num in fig_nums:
        try:
            fig = plt.figure(num)
            buf = io.BytesIO()
            fig.savefig(buf, format="png", bbox_inches="tight", dpi=100)
            buf.seek(0)
            pngs.append(buf.getvalue())
        except Exception:
            pass
    plt.close("all")
    return pngs


def _extract_chart_png() -> bytes | None:
    """If matplotlib has active figures, save the first one to PNG bytes."""
    all_pngs = _extract_all_chart_pngs()
    return all_pngs[0] if all_pngs else None

