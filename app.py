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
from src.profiler import load_csv, profile_dataframe
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
        "profile": None,
        "namespace": None,
        "agent": None,
        "history": None,
        "chat_log": [],  # list of {"role": "user"|"agent", "content": str, "charts": [], "code": []}
        "dataset_name": None,
        "is_truncated": False,
        "uploaded_file_id": None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


init_session()


# ──────────────────────────────────────────────
# Sidebar — File Upload & Dataset Controls
# ──────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📂 Upload Dataset")
    uploaded_file = st.file_uploader(
        "Drop a CSV file here",
        type=["csv"],
        help="Upload any CSV dataset. The agent will profile it and answer your questions.",
    )

    # Detect new upload → reset session
    if uploaded_file is not None:
        file_id = f"{uploaded_file.name}_{uploaded_file.size}"
        if file_id != st.session_state.uploaded_file_id:
            # New file — reset everything
            st.session_state.uploaded_file_id = file_id
            st.session_state.chat_log = []
            st.session_state.history = None

            with st.spinner("Loading & profiling dataset…"):
                try:
                    df, is_truncated = load_csv(io.BytesIO(uploaded_file.getvalue()))
                    profile = profile_dataframe(df, is_truncated)
                    namespace = create_namespace(df)
                    agent = CSVInsightAgent()

                    st.session_state.df = df
                    st.session_state.profile = profile
                    st.session_state.namespace = namespace
                    st.session_state.agent = agent
                    st.session_state.dataset_name = uploaded_file.name
                    st.session_state.is_truncated = is_truncated
                except Exception as e:
                    st.error(f"❌ Failed to load CSV: {e}")
                    st.session_state.df = None

    # Show dataset info in sidebar
    if st.session_state.df is not None:
        df = st.session_state.df
        st.markdown("---")
        st.markdown(f"**📄 {st.session_state.dataset_name}**")
        st.markdown(f"**Rows:** {len(df):,}")
        st.markdown(f"**Columns:** {len(df.columns)}")
        mem_mb = round(df.memory_usage(deep=True).sum() / 1_048_576, 2)
        st.markdown(f"**Memory:** {mem_mb} MB")
        if st.session_state.is_truncated:
            st.warning("⚠️ Large file — sampled for profiling.")
        st.markdown("---")

        # Reset session button
        if st.button("🔄 Reset Session", width="stretch"):
            for key in [
                "df",
                "profile",
                "namespace",
                "agent",
                "history",
                "chat_log",
                "dataset_name",
                "is_truncated",
                "uploaded_file_id",
            ]:
                st.session_state[key] = None if key != "chat_log" else []
            st.rerun()


# ──────────────────────────────────────────────
# Header
# ──────────────────────────────────────────────
st.markdown(
    """
<div class="app-header">
    <h1>📊 CSV Insight Agent</h1>
    <p>Upload a dataset, ask any question — the AI agent writes & runs real Python code to find answers.</p>
</div>
""",
    unsafe_allow_html=True,
)


# ──────────────────────────────────────────────
# Main Area
# ──────────────────────────────────────────────
if st.session_state.df is None:
    # Landing state — no dataset yet
    st.markdown("### 👋 Welcome!")
    st.markdown(
        "Use the sidebar to **upload a CSV file**. "
        "The agent will automatically profile it, and you can start asking questions."
    )
    st.info(
        "💡 **Example questions you can ask:**\n"
        "- *What are the key trends in this dataset?*\n"
        "- *Which category has the highest average value?*\n"
        "- *What is the biggest outlier?*\n"
        "- *Show me a breakdown by the top column*\n"
        "- *What correlations exist between the numeric columns?*"
    )
    st.stop()

# ── Dataset loaded — show overview + chat ──
df = st.session_state.df
profile = st.session_state.profile or {}

# Metric cards
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

# Data preview in expander
with st.expander("🔍 Preview Dataset", expanded=False):
    st.dataframe(df.head(50), width="stretch", height=300)
    st.caption(f"Showing first 50 rows of {n_rows:,} total.")

st.markdown('<hr class="section-divider">', unsafe_allow_html=True)


# ──────────────────────────────────────────────
# Chat Interface
# ──────────────────────────────────────────────
st.markdown("### 💬 Ask the Agent")

# Display chat history
for entry in st.session_state.chat_log:
    if entry["role"] == "user":
        with st.chat_message("user", avatar="👤"):
            st.markdown(entry["content"])
    else:
        with st.chat_message("assistant", avatar="📊"):
            st.markdown(entry["content"])

            # Show charts if any (or generate empirical breakdown if missing)
            charts_to_display = entry.get("charts") or []
            if not charts_to_display and st.session_state.df is not None:
                try:
                    from src.reporter import _generate_fallback_chart

                    fb = _generate_fallback_chart(st.session_state.df)
                    if fb:
                        charts_to_display = [fb]
                        entry["charts"] = charts_to_display
                except Exception:
                    pass

            if charts_to_display:
                for i, chart_bytes in enumerate(charts_to_display):
                    st.image(
                        chart_bytes,
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
                if success:
                    status_box.write(f"✅ Step {step} execution successful.")
                    if stdout:
                        with status_box.expander(f"Output Preview (Step {step})", expanded=False):
                            status_box.text(stdout[:800] + ("..." if len(stdout) > 800 else ""))
                    if has_chart:
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
            st.session_state.chat_log.append(
                {
                    "role": "agent",
                    "content": result["answer"],
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
# PDF Report Download (appears after at least one substantive agent response)
# ──────────────────────────────────────────────
def _is_substantive_report(content: str) -> bool:
    """Checks if an agent response is a substantive report rather than an error or intermediate chatter."""
    return len(content.strip()) > 40 and not content.strip().startswith("⚠️")

valid_agent_responses = [
    e for e in st.session_state.chat_log
    if e.get("role") == "agent" and _is_substantive_report(e.get("content", ""))
]

if valid_agent_responses:
    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
    st.markdown("### 📥 Download Executive Report")

    # Use the latest valid agent response for the report
    latest = valid_agent_responses[-1]
    # Collect all charts and code from entire conversation
    all_charts = []
    all_code = []
    all_questions = []
    for entry in st.session_state.chat_log:
        if entry["role"] == "agent":
            all_charts.extend(entry.get("charts", []))
            all_code.extend(entry.get("code", []))
        elif entry["role"] == "user":
            all_questions.append(entry["content"])

    combined_question = (
        " | ".join(all_questions) if all_questions else "General Analysis"
    )

    if st.button(
        "📄 Generate & Download PDF Report", width="stretch", type="primary"
    ):
        with st.spinner("Generating executive PDF report…"):
            try:
                pdf_bytes = generate_pdf_report(
                    dataset_name=st.session_state.dataset_name,
                    profile_dict=st.session_state.profile,
                    user_question=combined_question,
                    agent_answer=latest["content"],
                    charts=all_charts if all_charts else None,
                    executed_code=all_code if all_code else None,
                    df=st.session_state.df,
                )
                st.session_state["generated_pdf"] = pdf_bytes
                st.session_state["generated_pdf_name"] = f"csv_insight_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                st.success(f"✅ Report successfully generated! ({len(pdf_bytes):,} bytes)")
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
