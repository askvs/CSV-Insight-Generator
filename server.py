"""
CSV Insight Agent — Modern Flask Web Application Server

Provides REST APIs and Server-Sent Events (SSE) for:
  - Multi-file dataset ingestion (.csv, .xlsx, .xls, .parquet, .json)
  - Schema profiling & relational key detection
  - Live agent reasoning & sandbox execution streaming
  - Interactive Plotly chart serialization
  - 5-section executive PDF report export
  - Standards-compliant Jupyter Notebook (.ipynb) generation
"""

import base64
import io
import json
import os
import queue
import sys
import threading
import time
import uuid
from datetime import datetime
from typing import Any

# Ensure UTF-8 on Windows consoles
_reconfigure = getattr(sys.stdout, "reconfigure", None)
if callable(_reconfigure):
    try:
        _reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

import pandas as pd
from flask import Flask, Response, jsonify, render_template, request, send_file

try:
    import plotly.io as pio
except ImportError:
    pio = None

from src.agent import CSVInsightAgent
from src.notebook import generate_jupyter_notebook
from src.profiler import (
    load_multiple_files,
    profile_datasets,
)
from src.reporter import generate_pdf_report
from src.sandbox import create_namespace

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = 250 * 1024 * 1024  # 250 MB max upload limit

# ────────────────────────────────────────────────────────────
# In-Memory Session Store
# ────────────────────────────────────────────────────────────
# Maps session_id -> dict with session state
SESSION_STORE: dict[str, dict[str, Any]] = {}
SESSION_LOCK = threading.Lock()


def get_session(session_id: str) -> dict[str, Any]:
    """Retrieve or initialize an in-memory session."""
    with SESSION_LOCK:
        if session_id not in SESSION_STORE:
            SESSION_STORE[session_id] = {
                "dfs": {},
                "df": None,
                "dataset_names": [],
                "dataset_name": "",
                "profile": None,
                "namespace": None,
                "agent": None,
                "history": None,
                "chat_log": [],  # list of message dicts
                "raw_charts": [],  # list of native chart objects for exports
                "is_truncated": False,
                "created_at": time.time(),
                "last_accessed": time.time(),
            }
        else:
            SESSION_STORE[session_id]["last_accessed"] = time.time()
        return SESSION_STORE[session_id]


def get_session_id_from_request() -> str:
    """Extract session ID from header, cookie, or query param, or create new."""
    s_id = (
        request.headers.get("X-Session-ID")
        or request.args.get("session_id")
        or request.cookies.get("session_id")
    )
    if not s_id:
        s_id = str(uuid.uuid4())
    return s_id


class NamedBytesIO(io.BytesIO):
    """BytesIO buffer that preserves the original filename attribute for loaders."""

    def __init__(self, initial_bytes: bytes, filename: str):
        super().__init__(initial_bytes)
        self.name = filename


# ────────────────────────────────────────────────────────────
# Helper Functions
# ────────────────────────────────────────────────────────────
def _serialize_chart_for_client(chart_obj: Any) -> dict[str, Any]:
    """Serializes a chart object (Plotly Figure or PNG bytes) to client-friendly JSON."""
    if hasattr(chart_obj, "to_dict") and hasattr(chart_obj, "data"):
        try:
            fig_dict = chart_obj.to_dict()
            return {"type": "plotly", "figure": fig_dict}
        except Exception:
            pass

    if hasattr(chart_obj, "to_json"):
        try:
            fig_json = json.loads(chart_obj.to_json())
            return {"type": "plotly", "figure": fig_json}
        except Exception:
            pass

    if isinstance(chart_obj, bytes):
        b64 = base64.b64encode(chart_obj).decode("utf-8")
        return {"type": "image", "data": f"data:image/png;base64,{b64}"}

    return {"type": "unknown"}


def _is_substantive_report(content: str) -> bool:
    """Checks if response is an executive report rather than intermediate error."""
    return bool(content and len(content.strip()) > 40 and not content.strip().startswith("⚠️"))


# ────────────────────────────────────────────────────────────
# Web & API Routes
# ────────────────────────────────────────────────────────────
@app.route("/")
def index():
    """Serves the main single-page web interface."""
    return render_template("index.html")


@app.route("/api/session", methods=["GET"])
def get_session_state():
    """Returns the current state, loaded tables info, and chat log for the session."""
    session_id = get_session_id_from_request()
    sess = get_session(session_id)

    dfs = sess.get("dfs") or {}
    loaded = len(dfs) > 0
    profile = sess.get("profile") or {}

    tables_summary = []
    for name, d in dfs.items():
        mem_mb = round(d.memory_usage(deep=True).sum() / 1_048_576, 2)
        tables_summary.append({
            "name": name,
            "rows": len(d),
            "columns": len(d.columns),
            "columns_list": list(d.columns),
            "memory_mb": mem_mb,
        })

    # Return client-safe chat log
    client_chat_log = []
    for entry in sess.get("chat_log", []):
        client_chat_log.append({
            "role": entry.get("role"),
            "content": entry.get("content"),
            "charts": entry.get("client_charts", []),
            "code": entry.get("code", []),
            "timestamp": entry.get("timestamp", ""),
        })

    return jsonify({
        "session_id": session_id,
        "loaded": loaded,
        "is_multi_dataset": profile.get("is_multi_dataset", len(dfs) > 1),
        "dataset_names": sess.get("dataset_names", []),
        "tables": tables_summary,
        "profile": profile,
        "is_truncated": sess.get("is_truncated", False),
        "chat_log": client_chat_log,
    })


@app.route("/api/upload", methods=["POST"])
def upload_datasets():
    """Handles multi-file dataset upload and profiling."""
    session_id = get_session_id_from_request()
    sess = get_session(session_id)

    uploaded_files = request.files.getlist("files")
    if not uploaded_files:
        return jsonify({"error": "No files provided in upload request."}), 400

    buffers = []
    for f in uploaded_files:
        if not f.filename:
            continue
        content = f.read()
        buffers.append(NamedBytesIO(content, f.filename))

    if not buffers:
        return jsonify({"error": "Uploaded files were empty."}), 400

    try:
        loaded_dict = load_multiple_files(buffers)
        dfs = {name: pair[0] for name, pair in loaded_dict.items()}
        truncations = {name: pair[1] for name, pair in loaded_dict.items()}

        if not dfs:
            return jsonify({"error": "Could not parse any dataset tables from uploaded files."}), 400

        profile = profile_datasets(dfs, truncations)
        namespace = create_namespace(dfs)
        agent = CSVInsightAgent()

        with SESSION_LOCK:
            sess["dfs"] = dfs
            sess["df"] = next(iter(dfs.values())) if dfs else None
            sess["dataset_names"] = list(dfs.keys())
            sess["dataset_name"] = (
                ", ".join(dfs.keys()) if len(dfs) > 1 else next(iter(dfs.keys()))
            )
            sess["profile"] = profile
            sess["namespace"] = namespace
            sess["agent"] = agent
            sess["history"] = None
            sess["chat_log"] = []
            sess["raw_charts"] = []
            sess["is_truncated"] = any(truncations.values())

        tables_summary = []
        for name, d in dfs.items():
            mem_mb = round(d.memory_usage(deep=True).sum() / 1_048_576, 2)
            # Sample preview up to 50 rows
            sample_df = d.head(50).fillna("")
            tables_summary.append({
                "name": name,
                "rows": len(d),
                "columns": len(d.columns),
                "columns_list": list(d.columns),
                "memory_mb": mem_mb,
                "preview_rows": sample_df.to_dict(orient="records"),
            })

        return jsonify({
            "success": True,
            "session_id": session_id,
            "dataset_names": sess["dataset_names"],
            "tables": tables_summary,
            "profile": profile,
            "is_multi_dataset": profile.get("is_multi_dataset", len(dfs) > 1),
            "is_truncated": sess["is_truncated"],
        })

    except Exception as e:
        return jsonify({"error": f"Failed to load datasets: {e!s}"}), 500


@app.route("/api/table/<path:table_name>", methods=["GET"])
def get_table_data(table_name: str):
    """Returns paginated preview rows and stats for a specific loaded dataset."""
    session_id = get_session_id_from_request()
    sess = get_session(session_id)

    dfs = sess.get("dfs") or {}
    if table_name not in dfs:
        return jsonify({"error": f"Table '{table_name}' not found in active session."}), 404

    df = dfs[table_name]
    page = max(1, int(request.args.get("page", 1)))
    page_size = min(100, max(5, int(request.args.get("page_size", 25))))
    search = request.args.get("search", "").strip().lower()

    filtered_df = df
    if search:
        mask = df.astype(str).apply(lambda row: row.str.lower().str.contains(search, regex=False)).any(axis=1)
        filtered_df = df[mask]

    total_filtered = len(filtered_df)
    total_pages = max(1, (total_filtered + page_size - 1) // page_size)
    page = min(page, total_pages)

    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    page_slice = filtered_df.iloc[start_idx:end_idx].fillna("")

    return jsonify({
        "table_name": table_name,
        "total_rows": len(df),
        "total_filtered": total_filtered,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "columns": list(df.columns),
        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
        "rows": page_slice.to_dict(orient="records"),
    })


@app.route("/api/chat", methods=["POST"])
def chat_stream():
    """
    Server-Sent Events (SSE) streaming endpoint for agent questions.
    Streams live steps: reasoning -> code generated -> execution -> synthesis -> final answer & charts.
    """
    session_id = get_session_id_from_request()
    sess = get_session(session_id)

    if not sess.get("dfs") or not sess.get("agent"):
        return jsonify({"error": "No datasets loaded. Please upload a dataset first."}), 400

    data = request.get_json(silent=True) or {}
    user_question = data.get("question", "").strip()
    if not user_question:
        return jsonify({"error": "No question provided."}), 400

    # Record user message in chat log
    user_entry = {
        "role": "user",
        "content": user_question,
        "timestamp": datetime.now().strftime("%I:%M %p"),
    }
    sess["chat_log"].append(user_entry)

    event_queue: queue.Queue = queue.Queue()

    def agent_worker():
        def on_agent_status(event: str, d: dict):
            step = d.get("step", 1)
            phase = d.get("phase", "planning")
            is_retry = d.get("is_retry", False)
            model = d.get("model", "")
            short_model = model.split("/")[-1] if model else ""

            if event == "model_calling":
                if is_retry:
                    msg = f"Switching to fallback model: {short_model} (Step {step})..."
                elif phase == "synthesis":
                    msg = f"Synthesizing Executive Report (Step {step})..."
                else:
                    msg = f"Reasoning & Planning Analysis with {short_model} (Step {step})..."
                event_queue.put({"type": "status", "stage": "reasoning", "message": msg, "step": step, "model": short_model})

            elif event == "code_generated":
                code = d.get("code", "")
                event_queue.put({
                    "type": "code",
                    "step": step,
                    "code": code,
                    "message": f"Generated Python script for Step {step}",
                })

            elif event == "code_executing":
                event_queue.put({
                    "type": "status",
                    "stage": "executing",
                    "message": f"Executing Step {step} script in isolated sandbox...",
                    "step": step,
                })

            elif event == "code_executed":
                success = d.get("success", False)
                stdout = d.get("stdout", "")
                has_chart = d.get("has_chart", False)
                is_plotly = d.get("is_plotly", False)
                err = d.get("error", "")
                event_queue.put({
                    "type": "execution",
                    "step": step,
                    "success": success,
                    "stdout": stdout[:800] if stdout else "",
                    "has_chart": has_chart,
                    "is_plotly": is_plotly,
                    "error": err[:300] if err else None,
                })

            elif event == "synthesis_start":
                event_queue.put({
                    "type": "status",
                    "stage": "synthesis",
                    "message": "Formulating 5-section executive intelligence briefing...",
                })

            elif event == "completed":
                event_queue.put({
                    "type": "status",
                    "stage": "completed",
                    "message": "Analysis complete!",
                })

        try:
            agent: CSVInsightAgent = sess["agent"]
            result = agent.run_turn(
                user_question=user_question,
                profile_dict=sess["profile"],
                namespace=sess["namespace"],
                history=sess["history"],
                status_callback=on_agent_status,
            )

            sess["history"] = result.get("history")

            raw_charts = result.get("charts", [])
            client_charts = [_serialize_chart_for_client(c) for c in raw_charts]
            sess["raw_charts"].extend(raw_charts)

            agent_entry = {
                "role": "agent",
                "content": result.get("answer", ""),
                "client_charts": client_charts,
                "code": result.get("executed_code", []),
                "timestamp": datetime.now().strftime("%I:%M %p"),
            }
            sess["chat_log"].append(agent_entry)

            event_queue.put({
                "type": "final_answer",
                "answer": result.get("answer", ""),
                "charts": client_charts,
                "code": result.get("executed_code", []),
            })

        except Exception as e:
            err_msg = f"Analysis error: {e!s}"
            sess["chat_log"].append({
                "role": "agent",
                "content": f"⚠️ {err_msg}",
                "client_charts": [],
                "code": [],
                "timestamp": datetime.now().strftime("%I:%M %p"),
            })
            event_queue.put({"type": "error", "error": err_msg})

        finally:
            event_queue.put(None)

    threading.Thread(target=agent_worker, daemon=True).start()

    def generate_events():
        while True:
            try:
                item = event_queue.get(timeout=45)
                if item is None:
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    break
                yield f"data: {json.dumps(item)}\n\n"
            except queue.Empty:
                yield ": keepalive\n\n"

    return Response(
        generate_events(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.route("/api/export/pdf", methods=["POST", "GET"])
def export_pdf():
    """Generates and downloads the formal 5-section executive PDF report."""
    session_id = get_session_id_from_request()
    sess = get_session(session_id)

    chat_log = sess.get("chat_log", [])
    valid_responses = [
        e for e in chat_log
        if e.get("role") in ("agent", "assistant") and _is_substantive_report(e.get("content", ""))
    ]

    all_questions = []
    agent_answers = []
    all_code = []

    if not valid_responses:
        if not sess.get("dfs"):
            return jsonify({"error": "No completed intelligence analysis or dataset available to generate a PDF report."}), 400
        combined_question = "Comprehensive Dataset Profile & Baseline Audit"
        full_answer = f"# Dataset Baseline Audit\n\nAutomatically audited schemas and baseline feature distributions for {sess.get('dataset_name', 'dataset')}."
    else:
        for entry in chat_log:
            if entry.get("role") == "user":
                all_questions.append(entry.get("content", ""))
            elif entry.get("role") in ("agent", "assistant"):
                if _is_substantive_report(entry.get("content", "")):
                    agent_answers.append(entry.get("content", ""))
                if entry.get("code"):
                    all_code.extend(entry.get("code"))

        combined_question = " | ".join(all_questions) if all_questions else "Comprehensive Dataset Analysis"

        if len(agent_answers) > 1 and len(all_questions) == len(agent_answers):
            parts = [f"# Investigation Part {idx}: {q}\n\n{ans}" for idx, (q, ans) in enumerate(zip(all_questions, agent_answers), 1)]
            full_answer = "\n\n---\n\n".join(parts)
        elif agent_answers:
            full_answer = "\n\n---\n\n".join(agent_answers)
        else:
            full_answer = valid_responses[-1].get("content", "")

    try:
        pdf_bytes = generate_pdf_report(
            dataset_name=sess.get("dataset_name") or "dataset.csv",
            profile_dict=sess.get("profile") or {},
            user_question=combined_question,
            agent_answer=full_answer,
            charts=sess.get("raw_charts") if sess.get("raw_charts") else None,
            executed_code=all_code if all_code else None,
            df=sess.get("df"),
        )

        filename = f"csv_insight_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename,
        )
    except Exception as e:
        return jsonify({"error": f"Failed to generate PDF: {e!s}"}), 500


@app.route("/api/export/notebook", methods=["GET"])
def export_notebook():
    """Generates and downloads the reproducible Jupyter Notebook (.ipynb)."""
    session_id = get_session_id_from_request()
    sess = get_session(session_id)

    dfs = sess.get("dfs") or {}
    if not dfs:
        return jsonify({"error": "No dataset loaded to export into a notebook."}), 400

    chat_log = sess.get("chat_log", [])

    try:
        target_names = sess.get("dataset_names") or [sess.get("dataset_name") or "dataset.csv"]
        nb_chat_log = []
        for e in chat_log:
            entry_copy = dict(e)
            if e.get("role") in ("agent", "assistant"):
                entry_copy["charts"] = sess.get("raw_charts", [])
            nb_chat_log.append(entry_copy)

        nb_json = generate_jupyter_notebook(
            dataset_names=target_names,
            chat_log=nb_chat_log,
            profile_dict=sess.get("profile"),
        )

        filename = f"csv_insight_notebook_{datetime.now().strftime('%Y%m%d_%H%M%S')}.ipynb"
        return Response(
            nb_json,
            mimetype="application/x-ipynb+json",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except Exception as e:
        return jsonify({"error": f"Failed to prepare notebook: {e!s}"}), 500


@app.route("/api/reset", methods=["POST"])
def reset_session():
    """Clears active session memory, dataframes, and history."""
    session_id = get_session_id_from_request()
    with SESSION_LOCK:
        if session_id in SESSION_STORE:
            del SESSION_STORE[session_id]

    return jsonify({"success": True, "message": "Session reset successfully."})


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", 5000))
    print(f"\n=======================================================")
    print(f"🚀 CSV Insight Agent Web Server running at:")
    print(f"👉 http://{host}:{port}")
    print(f"=======================================================\n")
    app.run(host=host, port=port, debug=True)
