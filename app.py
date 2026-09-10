"""
CSV Insight Agent — Streamlit Web Application (Phase 5)

Interactive web UI that lets users:
  1. Upload any CSV dataset
  2. View dataset overview (shape, sample rows, column stats)
  3. Ask open-ended questions via a chat interface
  4. See the agent's executed code, charts, and plain-English answers
  5. Download an executive PDF report
"""

import io
import sys
from datetime import datetime

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

import streamlit as st

from src.agent import CSVInsightAgent
from src.notebook import generate_jupyter_notebook
from src.profiler import (
    load_csv,
    load_dataset,
    load_multiple_files,
    profile_dataframe,
    profile_datasets,
)
from src.reporter import generate_pdf_report
from src.sandbox import create_namespace

# ──────────────────────────────────────────────
# Page Config
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="CSV Insight Agent",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────
# Custom CSS for a polished look
# ──────────────────────────────────────────────
st.markdown(
    """
<style>
/* ---------- Global ---------- */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

/* ---------- Sidebar ---------- */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0B2545 0%, #134074 100%);
}
section[data-testid="stSidebar"] * {
    color: #E2E8F0 !important;
}
section[data-testid="stSidebar"] .stFileUploader label {
    color: #93C5FD !important;
    font-weight: 600;
}

/* ---------- Hide 200MB limit text while uploading ---------- */
[data-testid="stFileUploaderDropzoneInstructions"] small,
[data-testid="stFileUploaderDropzone"] small,
[data-testid="stFileUploaderInstructions"],
[data-testid="stFileUploader"] small,
section[data-testid="stSidebar"] [data-testid="stFileUploader"] small,
div[data-testid="stFileUploader"] section small,
div[data-testid="stFileUploader"] small,
.stFileUploader small {
    display: none !important;
}

/* ---------- Header banner ---------- */
.app-header {
    background: linear-gradient(135deg, #0B2545 0%, #134074 50%, #1E3A5F 100%);
    padding: 1.5rem 2rem;
    border-radius: 12px;
    margin-bottom: 1.5rem;
    box-shadow: 0 4px 20px rgba(11, 37, 69, 0.25);
}
.app-header h1 {
    color: #FFFFFF;
    font-size: 1.75rem;
    font-weight: 700;
    margin: 0 0 0.25rem 0;
    letter-spacing: -0.01em;
}
.app-header p {
    color: #93C5FD;
    font-size: 0.9rem;
    margin: 0;
}

/* ---------- Metric cards ---------- */
.metric-row {
    display: flex;
    gap: 1rem;
    margin-bottom: 1.25rem;
}
.metric-card {
    flex: 1;
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    padding: 1rem 1.25rem;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    text-align: center;
}
.metric-card .metric-value {
    font-size: 1.6rem;
    font-weight: 700;
    color: #0B2545;
    line-height: 1.2;
}
.metric-card .metric-label {
    font-size: 0.78rem;
    color: #64748B;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    margin-top: 0.2rem;
}

/* ---------- Native Chat Messages ---------- */
[data-testid="stChatMessage"] {
    border-radius: 12px;
    padding: 1rem 1.25rem;
    margin-bottom: 0.85rem;
    background-color: #0F172A;
    border: 1px solid #1E293B;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
}
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
    background: linear-gradient(135deg, rgba(30, 58, 138, 0.35) 0%, rgba(37, 99, 235, 0.2) 100%);
    border: 1px solid rgba(59, 130, 246, 0.35);
}

/* ---------- Thinking spinner ---------- */
.thinking-indicator {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    color: #64748B;
    font-size: 0.85rem;
    padding: 0.5rem 0;
}
.thinking-indicator .dot {
    width: 6px; height: 6px;
    border-radius: 50%;
    background: #3B82F6;
    animation: pulse 1.2s infinite ease-in-out;
}
.thinking-indicator .dot:nth-child(2) { animation-delay: 0.2s; }
.thinking-indicator .dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes pulse {
    0%, 100% { opacity: 0.3; transform: scale(0.8); }
    50% { opacity: 1; transform: scale(1.2); }
}

/* ---------- Code block ---------- */
.code-block-label {
    font-size: 0.75rem;
    font-weight: 600;
    color: #64748B;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.25rem;
}

/* ---------- Section dividers ---------- */
.section-divider {
    border: none;
    border-top: 1px solid #E2E8F0;
    margin: 1.5rem 0;
}

/* Hide Streamlit branding */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
</style>
""",
    unsafe_allow_html=True,
)


# ──────────────────────────────────────────────
# Session State Initialization
# ──────────────────────────────────────────────
def init_session():
    """Initialize all session state keys if they don't exist."""
    defaults = {
        "df": None,
        "dfs": {},
        "dataset_names": [],
        "profile": None,
        "namespace": None,
        "agent": None,
        "history": None,
        "chat_log": [],  # list of {"role": "user"|"agent", "content": str, "charts": [], "code": []}
        "dataset_name": None,
        "is_truncated": False,
        "uploaded_files_id": None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


init_session()

# Self-healing: cleanse any stale profile dictionary held in browser session memory
if st.session_state.get("profile"):
    try:
        json.dumps(st.session_state.profile, default=str)
    except Exception:
        if isinstance(st.session_state.profile, dict):
            st.session_state.profile = {
                k: v for k, v in st.session_state.profile.items() if k != "datasets"
            }
        st.session_state.history = None
with st.sidebar:
    st.markdown("## 📂 Upload Datasets")
    uploaded_files = st.file_uploader(
        "Drop datasets here (CSV, Excel, Parquet, JSON)",
        type=["csv", "xlsx", "xls", "parquet", "json"],
        accept_multiple_files=True,
        help="Upload one or more datasets in CSV, Excel (.xlsx/.xls), Parquet, or JSON format.",
    )

    # Detect new upload → reset session
    if uploaded_files:
        files_id = "_".join(sorted([f"{f.name}_{getattr(f, 'size', 0)}" for f in uploaded_files]))
        if files_id != st.session_state.uploaded_files_id:
            st.session_state.uploaded_files_id = files_id
            st.session_state.chat_log = []
            st.session_state.history = None
            st.session_state.pop("generated_pdf", None)
            st.session_state.pop("generated_pdf_name", None)

            with st.spinner("Loading & profiling dataset(s)…"):
                try:
                    loaded_dict = load_multiple_files(uploaded_files)
                    dfs = {name: pair[0] for name, pair in loaded_dict.items()}
                    truncations = {name: pair[1] for name, pair in loaded_dict.items()}

                    profile = profile_datasets(dfs, truncations)
                    namespace = create_namespace(dfs)
                    agent = CSVInsightAgent()

                    st.session_state.dfs = dfs
                    st.session_state.df = next(iter(dfs.values())) if dfs else None
                    st.session_state.dataset_names = list(dfs.keys())
                    st.session_state.dataset_name = (
                        ", ".join(dfs.keys()) if len(dfs) > 1 else (next(iter(dfs.keys())) if dfs else "dataset")
                    )
                    st.session_state.profile = profile
                    st.session_state.namespace = namespace
                    st.session_state.agent = agent
                    st.session_state.is_truncated = any(truncations.values())
                except Exception as e:
                    st.error(f"❌ Failed to load datasets: {e}")
                    st.session_state.df = None
                    st.session_state.dfs = {}

    # Show dataset info in sidebar
    if st.session_state.dfs:
        dfs = st.session_state.dfs
        st.markdown("---")
        if len(dfs) == 1:
            d_name, single_df = next(iter(dfs.items()))
            st.markdown(f"**📄 {d_name}**")
            st.markdown(f"**Rows:** {len(single_df):,}")
            st.markdown(f"**Columns:** {len(single_df.columns)}")
            mem_mb = round(single_df.memory_usage(deep=True).sum() / 1_048_576, 2)
            st.markdown(f"**Memory:** {mem_mb} MB")
        else:
            total_rows = sum(len(d) for d in dfs.values())
            total_cols = sum(len(d.columns) for d in dfs.values())
            total_mem = round(sum(d.memory_usage(deep=True).sum() for d in dfs.values()) / 1_048_576, 2)
            st.markdown(f"**📚 {len(dfs)} Datasets Loaded**")
            st.markdown(f"**Total Records:** {total_rows:,}")
            st.markdown(f"**Total Features:** {total_cols}")
            st.markdown(f"**Total Memory:** {total_mem} MB")
            with st.expander("📑 View Table Inventory", expanded=False):
                for name, d in dfs.items():
                    st.caption(f"• **{name}**: {len(d):,} rows × {len(d.columns)} cols")

        if st.session_state.is_truncated:
            st.warning("⚠️ Large file(s) — sampled for profiling.")
        st.markdown("---")

        # Reset session button
        if st.button("🔄 Reset Session", width="stretch"):
            for key in [
                "df",
                "dfs",
                "dataset_names",
                "profile",
                "namespace",
                "agent",
                "history",
                "chat_log",
                "dataset_name",
                "is_truncated",
                "uploaded_files_id",
                "generated_pdf",
                "generated_pdf_name",
            ]:
                st.session_state[key] = None if key != "chat_log" else []
            st.rerun()


# ──────────────────────────────────────────────
# Header
# ──────────────────────────────────────────────
st.markdown(
    """
<div class="app-header">
    <h1>📊 CSV & Multi-Dataset Insight Agent</h1>
    <p>Drop CSV, Excel, Parquet, or JSON datasets — the AI agent writes Python, executes code, generates interactive Plotly charts, and uncovers cross-table intelligence.</p>
</div>
""",
    unsafe_allow_html=True,
)


# ──────────────────────────────────────────────
# Main Area
# ──────────────────────────────────────────────
if not st.session_state.dfs:
    # Landing state — no dataset yet
    st.markdown("### 👋 Welcome!")
    st.markdown(
        "Use the sidebar to **upload one or more datasets** (`.csv`, `.xlsx`, `.xls`, `.parquet`, `.json`). "
        "The agent will automatically profile schemas, discover potential relational join keys, and answer complex analytical questions."
    )
    st.info(
        "💡 **Example questions you can ask:**\n"
        "- *What are the key trends and correlations in this dataset?*\n"
        "- *Join the orders and customers tables to find top buyers by lifetime value.*\n"
        "- *Which product category has the highest average revenue?*\n"
        "- *Identify anomalies and outliers across numeric metrics.*\n"
        "- *Create an interactive breakdown comparing performance across groups.*"
    )
    st.stop()

# ── Datasets loaded — show overview + chat ──
dfs = st.session_state.dfs
profile = st.session_state.profile or {}
is_multi = profile.get("is_multi_dataset", len(dfs) > 1)

if is_multi:
    s = profile.get("summary", {})
    n_tables = s.get("total_datasets", len(dfs))
    n_rows = s.get("total_rows", sum(len(d) for d in dfs.values()))
    n_cols = sum(len(d.columns) for d in dfs.values())
    mem_mb = s.get("total_memory_mb", round(sum(d.memory_usage(deep=True).sum() for d in dfs.values()) / 1_048_576, 2))

    st.markdown(
        f"""
<div class="metric-row">
    <div class="metric-card">
        <div class="metric-value">{n_tables}</div>
        <div class="metric-label">Tables Loaded</div>
    </div>
    <div class="metric-card">
        <div class="metric-value">{n_rows:,}</div>
        <div class="metric-label">Total Records</div>
    </div>
    <div class="metric-card">
        <div class="metric-value">{n_cols}</div>
        <div class="metric-label">Total Features</div>
    </div>
    <div class="metric-card">
        <div class="metric-value">{mem_mb} MB</div>
        <div class="metric-label">Memory Footprint</div>
    </div>
</div>
""",
        unsafe_allow_html=True,
    )

    # Display detected relational join keys
    common_keys = profile.get("common_keys_for_joins", [])
    if common_keys:
        keys_summary = ", ".join([f"`{k['column']}` ({', '.join(k['tables'])})" for k in common_keys])
        st.info(f"🔗 **Relational Link Detected:** Shared join key(s): {keys_summary}. The AI agent can perform cross-table merges seamlessly.")

    # Multi-tab data preview
    with st.expander("🔍 Preview Loaded Datasets", expanded=False):
        tab_titles = [f"📄 {name} ({len(d):,} rows)" for name, d in dfs.items()]
        tabs = st.tabs(tab_titles)
        for tab, (t_name, t_df) in zip(tabs, dfs.items()):
            with tab:
                st.dataframe(t_df.head(50), width="stretch", height=280)
                st.caption(f"Showing first 50 rows of {len(t_df):,} total for `{t_name}`.")
else:
    df = st.session_state.df
    shape = profile.get("shape", {})
    n_rows = shape.get("rows", len(df) if df is not None else 0)
    n_cols = shape.get("columns", len(df.columns) if df is not None else 0)
    mem_mb = profile.get("memory_mb", "?")
    null_pct = round(df.isnull().mean().mean() * 100, 1) if df is not None else 0.0

    st.markdown(
        f"""
<div class="metric-row">
    <div class="metric-card">
        <div class="metric-value">{n_rows:,}</div>
        <div class="metric-label">Records</div>
    </div>
    <div class="metric-card">
        <div class="metric-value">{n_cols}</div>
        <div class="metric-label">Features</div>
    </div>
    <div class="metric-card">
        <div class="metric-value">{mem_mb} MB</div>
        <div class="metric-label">Memory</div>
    </div>
    <div class="metric-card">
        <div class="metric-value">{null_pct}%</div>
        <div class="metric-label">Missing Values</div>
    </div>
</div>
""",
        unsafe_allow_html=True,
    )

    with st.expander("🔍 Preview Dataset", expanded=False):
        st.dataframe(df.head(50), width="stretch", height=300)
        st.caption(f"Showing first 50 rows of {n_rows:,} total.")

st.markdown('<hr class="section-divider">', unsafe_allow_html=True)


# ──────────────────────────────────────────────
# Chat Interface
# ──────────────────────────────────────────────
st.markdown("### 💬 Ask the Agent")

# Display chat history
for entry_idx, entry in enumerate(st.session_state.chat_log):
    if entry.get("role") == "user":
        with st.chat_message("user", avatar="👤"):
            st.markdown(entry.get("content", ""))
    else:
        with st.chat_message("assistant", avatar="📊"):
            agent_content = (entry.get("content") or "").strip()
            if not agent_content:
                agent_content = "### 📊 Analysis Complete\n\nReview the visual breakdown and executed code below."
            st.markdown(agent_content)

            # Show charts if any
            charts_to_display = entry.get("charts") or []
            if charts_to_display:
                for i, chart in enumerate(charts_to_display):
                    if hasattr(chart, "to_dict") and hasattr(chart, "data"):
                        st.plotly_chart(
                            chart,
                            use_container_width=True,
                            key=f"chart_{entry_idx}_{i}",
                        )
                    elif isinstance(chart, bytes):
                        st.image(
                            chart,
                            caption=f"📊 Visual Intelligence Breakdown (Figure {i + 1})",
                            width="stretch",
                        )

            # Show executed code in expander
            if entry.get("code"):
                with st.expander(
                    f"⚙️ Executed Code ({len(entry['code'])} step{'s' if len(entry['code']) != 1 else ''})",
                    expanded=False,
                ):
                    for j, snippet in enumerate(entry["code"], 1):
                        st.caption(f"**Step {j}:**")
                        st.code(snippet, language="python")

# Chat input
user_question = st.chat_input("Ask a question about your dataset…")

if user_question:
    # Add user message to log
    st.session_state.chat_log.append({"role": "user", "content": user_question})

    # Display user message immediately
    with st.chat_message("user", avatar="👤"):
        st.markdown(user_question)

    # Run agent inside assistant message with live step-by-step status
    with st.chat_message("assistant", avatar="📊"):
        status_box = st.status("⚡ Initializing intelligent data analysis...", expanded=True)

        def on_agent_status(event: str, data: dict):
            step = data.get("step", 1)
            phase = data.get("phase", "planning")
            is_retry = data.get("is_retry", False)
            model = data.get("model", "")
            short_model = model.split("/")[-1] if model else ""

            if event == "model_calling":
                if is_retry:
                    status_box.update(label=f"🔄 Fallback to {short_model} (Step {step})...")
                    status_box.write(f"🔄 **Switching to fallback model:** `{short_model}` (Step {step})...")
                elif phase == "synthesis":
                    status_box.update(label=f"📝 Synthesizing Executive Report (Step {step})...")
                    status_box.write(f"📝 **Synthesizing findings & formulating report** (Step {step})...")
                else:
                    status_box.update(label=f"🧠 Reasoning & Planning Analysis (Step {step})...")
                    status_box.write(f"🧠 **Reasoning and planning analysis** (Step {step})...")
            elif event == "code_generated":
                code = data.get("code", "")
                status_box.update(label=f"💻 Executing Step {step} Analysis in Sandbox...")
                status_box.write(f"💻 **Generated Python Code (Step {step}):**")
                status_box.code(code, language="python")
            elif event == "code_executing":
                status_box.write("⚙️ Executing script in sandbox environment...")
            elif event == "code_executed":
                success = data.get("success", False)
                stdout = data.get("stdout", "")
                has_chart = data.get("has_chart", False)
                is_plotly = data.get("is_plotly", False)
                if success:
                    status_box.write(f"✅ Step {step} execution successful.")
                    if stdout:
                        with status_box.expander(f"Output Preview (Step {step})", expanded=False):
                            status_box.text(stdout[:800] + ("..." if len(stdout) > 800 else ""))
                    if is_plotly:
                        status_box.write("📈 Interactive Plotly visualization generated & captured.")
                    elif has_chart:
                        status_box.write("📈 Data visualization generated & captured.")
                else:
                    err = data.get("error", "Unknown error")
                    status_box.write(f"⚠️ Code error encountered in Step {step}, auto-correcting: `{err[:200]}`")
            elif event == "synthesis_start":
                status_box.update(label="📝 Finalizing Executive Briefing...")
                status_box.write("📝 **Compiling comprehensive 5-section executive report...**")
            elif event == "completed":
                status_box.write("✨ Executive intelligence report ready!")

        try:
            result = st.session_state.agent.run_turn(
                user_question=user_question,
                profile_dict=st.session_state.profile,
                namespace=st.session_state.namespace,
                history=st.session_state.history,
                status_callback=on_agent_status,
            )
            status_box.update(
                label="✅ Analysis & computation complete!",
                state="complete",
                expanded=False,
            )

            # Update persistent history for follow-ups
            st.session_state.history = result["history"]

            # Add agent response to chat log
            ans = (result.get("answer") or "").strip()
            if not ans:
                ans = "### 📊 Analysis Complete\n\nComputed empirical findings and visual charts are provided below."
            st.session_state.chat_log.append(
                {
                    "role": "agent",
                    "content": ans,
                    "charts": result["charts"],
                    "code": result["executed_code"],
                }
            )

        except Exception as e:
            status_box.update(
                label="❌ Analysis encountered an error",
                state="error",
                expanded=True,
            )
            status_box.error(str(e))
            st.session_state.chat_log.append(
                {
                    "role": "agent",
                    "content": f"⚠️ An error occurred: {e!s}",
                    "charts": [],
                    "code": [],
                }
            )

    st.rerun()


# ──────────────────────────────────────────────
# Export Deliverables (PDF Briefing & Jupyter Notebook)
# ──────────────────────────────────────────────
def _is_substantive_report(content: str) -> bool:
    """Checks if an agent response is a substantive report rather than an error or intermediate chatter."""
    return len(content.strip()) > 40 and not content.strip().startswith("⚠️")

valid_agent_responses = [
    e for e in st.session_state.chat_log
    if e.get("role") in ("agent", "assistant") and _is_substantive_report(e.get("content", ""))
]

if valid_agent_responses:
    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
    st.markdown("### 📥 Export Deliverables")

    all_charts = []
    all_code = []
    all_questions = []
    agent_answers = []

    for entry in st.session_state.chat_log:
        if entry.get("role") in ("agent", "assistant"):
            if entry.get("charts"):
                all_charts.extend(entry["charts"])
            if entry.get("code"):
                all_code.extend(entry["code"])
            if _is_substantive_report(entry.get("content", "")):
                agent_answers.append(entry["content"])
        elif entry.get("role") == "user":
            all_questions.append(entry.get("content", ""))

    combined_question = (
        " | ".join(all_questions) if all_questions else "Comprehensive Dataset Analysis"
    )

    # If multiple questions were investigated, compile each part clearly into the executive briefing
    if len(agent_answers) > 1 and len(all_questions) == len(agent_answers):
        combined_report_parts = []
        for q_idx, (q, ans) in enumerate(zip(all_questions, agent_answers), 1):
            combined_report_parts.append(f"# Investigation Part {q_idx}: {q.strip()}\n\n{ans.strip()}")
        full_agent_answer = "\n\n---\n\n".join(combined_report_parts)
    elif len(agent_answers) > 1:
        full_agent_answer = "\n\n---\n\n".join(agent_answers)
    elif agent_answers:
        full_agent_answer = agent_answers[-1]
    else:
        full_agent_answer = valid_agent_responses[-1].get("content", "")

    col_pdf, col_nb = st.columns(2)

    with col_pdf:
        st.markdown("#### 📄 Executive PDF Report")
        st.caption("Publication-ready formal briefing with visual charts, data audit, and key strategic takeaways.")

        if st.button(
            "📄 Generate PDF Report", width="stretch", type="primary"
        ):
            with st.spinner("Generating executive PDF report…"):
                try:
                    pdf_bytes = generate_pdf_report(
                        dataset_name=st.session_state.dataset_name,
                        profile_dict=st.session_state.profile,
                        user_question=combined_question,
                        agent_answer=full_agent_answer,
                        charts=all_charts if all_charts else None,
                        executed_code=all_code if all_code else None,
                        df=st.session_state.df,
                    )
                    st.session_state["generated_pdf"] = pdf_bytes
                    st.session_state["generated_pdf_name"] = f"csv_insight_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                    st.success(f"✅ PDF successfully generated! ({len(pdf_bytes):,} bytes)")
                except Exception as e:
                    st.error(f"❌ Failed to generate PDF: {e}")

        if st.session_state.get("generated_pdf"):
            st.download_button(
                label="⬇️ Download PDF Report",
                data=st.session_state["generated_pdf"],
                file_name=st.session_state.get(
                    "generated_pdf_name", f"csv_insight_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                ),
                mime="application/pdf",
                width="stretch",
            )

    with col_nb:
        st.markdown("#### 📓 Jupyter Notebook (.ipynb)")
        st.caption("Reproducible data science notebook containing all executed Python scripts, outputs & Plotly charts.")

        try:
            target_names = st.session_state.get("dataset_names") or [st.session_state.dataset_name or "dataset.csv"]
            nb_json = generate_jupyter_notebook(
                dataset_names=target_names,
                chat_log=st.session_state.chat_log,
                profile_dict=st.session_state.profile,
            )
            st.download_button(
                label="⬇️ Download Jupyter Notebook (.ipynb)",
                data=nb_json,
                file_name=f"csv_insight_notebook_{datetime.now().strftime('%Y%m%d_%H%M%S')}.ipynb",
                mime="application/x-ipynb+json",
                width="stretch",
                type="secondary",
            )
        except Exception as e:
            st.error(f"❌ Failed to prepare notebook: {e}")
