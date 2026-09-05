import builtins as _builtins
import io
import json
import re
import sys
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Allowed modules for sandbox imports
ALLOWED_MODULES = {
    "pandas",
    "numpy",
    "matplotlib",
    "matplotlib.pyplot",
    "matplotlib.dates",
    "matplotlib.ticker",
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


def create_namespace(df: pd.DataFrame) -> dict:
    """
    Create a fresh namespace dictionary for a session.
    Populates `df`, `pd`, `np`, `plt`, and safe builtins.
    """
    namespace = {
        "__builtins__": SAFE_BUILTINS,
        "df": df,
        "pd": pd,
        "np": np,
        "plt": plt,
    }
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
        "chart_png": bytes,   # PNG image bytes if matplotlib figure was generated
        "error": str|None,    # error message / traceback if execution failed
      }
    """
    # Prepared output structure
    output: dict[str, Any] = {
        "success": False,
        "stdout": "",
        "result": None,
        "chart_png": None,
        "error": None,
    }

    # Intercept print statements
    stdout_buffer = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = stdout_buffer

    # Fail-safe chart capture hooks in case code calls plt.show() or plt.close()
    captured_chart_png: bytes | None = None
    orig_close = plt.close
    orig_show = plt.show

    def intercept_close(*args, **kwargs):
        nonlocal captured_chart_png
        if not captured_chart_png and plt.get_fignums():
            buf = io.BytesIO()
            plt.savefig(buf, format="png", bbox_inches="tight", dpi=100)
            buf.seek(0)
            captured_chart_png = buf.getvalue()
        return orig_close(*args, **kwargs)

    def intercept_show(*args, **kwargs):
        nonlocal captured_chart_png
        if not captured_chart_png and plt.get_fignums():
            buf = io.BytesIO()
            plt.savefig(buf, format="png", bbox_inches="tight", dpi=100)
            buf.seek(0)
            captured_chart_png = buf.getvalue()

    plt.close = intercept_close
    plt.show = intercept_show

    try:
        # Clear any existing figures before running
        orig_close("all")

        # Sanitize and repair code if cut off or malformed
        sanitized_code = sanitize_and_repair_code(code)

        # Execute code in persistent namespace
        exec(sanitized_code, namespace)

        # Retrieve any captured stdout prints
        captured_stdout = stdout_buffer.getvalue().strip()
        output["stdout"] = captured_stdout

        # Check if a matplotlib chart was generated
        output["chart_png"] = captured_chart_png or _extract_chart_png()

        output["success"] = True

    except Exception as e:
        # Capture error & traceback formatted string for the LLM self-correction
        output["error"] = f"{type(e).__name__}: {e!s}"
        # If chart was captured before the error occurred, retain it
        output["chart_png"] = captured_chart_png or _extract_chart_png()
        orig_close("all")

    finally:
        # Restore normal functions and stdout stream
        plt.close = orig_close
        plt.show = orig_show
        sys.stdout = old_stdout

    return output


def _extract_chart_png() -> bytes | None:
    """If matplotlib has active figures, save to PNG bytes and close all figures."""
    fig_nums = plt.get_fignums()
    if not fig_nums:
        return None

    img_buf = io.BytesIO()
    plt.savefig(img_buf, format="png", bbox_inches="tight", dpi=100)
    plt.close("all")
    img_buf.seek(0)
    return img_buf.getvalue()

