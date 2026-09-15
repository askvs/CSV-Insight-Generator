# Vikash Sharma G6 GenAi - SURE ProEd
<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/Flask-Server-000000?style=for-the-badge&logo=flask&logoColor=white" alt="Flask" />
  <img src="https://img.shields.io/badge/Groq-LLM-FF6B35?style=for-the-badge&logo=groq&logoColor=white" alt="Groq" />
  <img src="https://img.shields.io/badge/Plotly-Interactive_Charts-3F4F75?style=for-the-badge&logo=plotly&logoColor=white" alt="Plotly" />
  <img src="https://img.shields.io/badge/Render-Deployed-46E3B7?style=for-the-badge&logo=render&logoColor=white" alt="Render" />
</p>

# 📊 CSV & Multi-Dataset Insight Agent

> **An autonomous AI data intelligence engine** that writes and executes real Python code in a secure sandbox, generates interactive Plotly visualizations, and synthesizes board-ready executive briefings — all from natural language questions about your data.

---

## 🌟 What It Does

Upload any combination of **CSV, Excel, or JSON** files. Ask questions in plain English. The agent autonomously:

1. **Reasons** about your data schema and profile
2. **Writes** optimized Python code (Pandas, NumPy, Plotly)
3. **Executes** it in an isolated sandbox
4. **Generates** interactive charts and visual breakdowns
5. **Delivers** a structured 5-section executive intelligence briefing

No manual coding. No copy-pasting. Just insights.

---

## 💡 Who Is This For

**🔬 Data Analysts & Scientists** — Skip the repetitive EDA boilerplate. Ask complex analytical questions and get publication-ready charts and statistics in seconds, not hours. The agent handles the Pandas wrangling, aggregation, and Plotly rendering so you can focus on interpretation.

**🎓 Students & Researchers** — Explore unfamiliar datasets without writing a single line of code. Upload your survey data, experiment results, or public datasets and get instant profiling, visual breakdowns, and structured summaries perfect for thesis chapters or assignments.

**📈 Business Stakeholders & Executives** — Get board-ready intelligence briefings from raw data files. The agent delivers structured 5-section reports (Executive Summary → Key Findings → Root-Cause Drivers → Strategic Recommendations → Risk Assessment) that you can export as polished PDFs.

**👩‍💻 Developers & Engineers** — Export reproducible Jupyter Notebooks with every analysis. All generated code is visible, editable, and ready to integrate into your existing data pipelines. The sandboxed execution ensures nothing touches your production environment.

**🏢 Small Teams Without a Data Team** — Turn any CSV export from your CRM, accounting software, or operations dashboard into actionable insights. No need to hire a data analyst for ad-hoc questions — just upload and ask.

---

## ✨ Key Features

| Feature | Description |
| :--- | :--- |
| **Multi-Format Upload** | Drag & drop CSV, XLSX, XLS, and JSON files — upload multiple datasets simultaneously |
| **Multi-Dataset Analysis** | Cross-dataset joins and comparative analysis across loaded tables (e.g., `pd.merge(orders, customers, on='customer_id')`) |
| **Real-Time SSE Streaming** | Watch the agent think, code, and analyze live via Server-Sent Events with an auto-collapsing reasoning stepper |
| **Interactive Plotly Charts** | Full pan, zoom, hover, and export on every visualization — not static images |
| **Sandboxed Code Execution** | Python runs in a restricted namespace with only data science libraries available |
| **Executive PDF Reports** | Download formal 5-section briefings with charts, findings, and executed code via ReportLab |
| **Jupyter Notebook Export** | Get a reproducible `.ipynb` notebook with all your analysis code and chart outputs |
| **Paginated Data Explorer** | Browse loaded datasets with search, pagination, and per-table column inspection |
| **Session Persistence** | Sessions survive server restarts through disk-backed pickle serialization |
| **Cancellation Support** | Stop a running analysis mid-flight without losing prior chat history |
| **Automatic Fallback Charts** | If the agent doesn't generate a chart, an empirical baseline visualization is auto-created |

---

## 🛠️ Tech Stack

| Layer | Technology |
| :--- | :--- |
| **Backend** | [Flask](https://flask.palletsprojects.com/) with Gunicorn (gthread workers) |
| **Frontend** | Vanilla HTML / CSS / JavaScript — custom single-page app |
| **LLM Engine** | [Groq API](https://groq.com/) — Qwen 3.8-27B, GPT-OSS-120B, GPT-OSS-20B (automatic model fallback) |
| **Data Processing** | Pandas, NumPy, OpenPyXL |
| **Visualization** | Plotly (Express + Graph Objects) with Matplotlib fallback |
| **PDF Generation** | ReportLab with custom markdown-to-PDF parser |
| **Notebook Export** | Custom `.ipynb` builder |
| **Streaming** | Server-Sent Events (SSE) for real-time agent updates |
| **Deployment** | [Render](https://render.com/) (Singapore region) |

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.11+**
- A [Groq API Key](https://console.groq.com/keys)

### Local Setup

```bash
# Clone the repository
git clone https://github.com/askvs/CSV-Insight-Generator.git
cd CSV-Insight-Generator

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate        # macOS / Linux
venv\Scripts\activate           # Windows

# Install dependencies
pip install -r requirements.txt

# Configure your API key
echo "GROQ_API_KEY=your_key_here" > .env

# Launch the server
python server.py
```

The app will start at **http://127.0.0.1:5000**

> **Windows shortcut** — double-click `run_web.bat` to activate the venv and launch the server in one step.

### Production Deployment (Render)

The project includes a `render.yaml` blueprint for one-click deployment:

```yaml
services:
  - type: web
    name: csv-insight-agent
    env: python
    region: singapore
    plan: free
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn server:app --worker-class gthread --workers 2 --threads 4 --timeout 180
```

Set `GROQ_API_KEY` in Render's environment variables dashboard.

---

## 🧠 How the Agent Works

```
User Question
     │
     ▼
┌─────────────────────────┐
│  Groq LLM (Tool Calling)│ ◄── System prompt + dataset profile + chat history
│  Qwen / GPT-OSS models  │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│  execute_python tool     │ ── Writes Pandas/Plotly code
│  Sandboxed Execution     │ ── Runs in restricted namespace
│  Chart Capture           │ ── Extracts Plotly/Matplotlib figures
└────────┬────────────────┘
         │  (loops if more analysis needed)
         ▼
┌─────────────────────────┐
│  final_answer tool       │ ── 5-section executive briefing
│  Structured Markdown     │ ── Tables, bullet points, metrics
└────────┬────────────────┘
         │
         ▼
   Client (SSE Stream)
```

The agent operates in a **multi-step tool-calling loop** — it can reason, write code, inspect execution output, and iterate before delivering a comprehensive final answer with interactive charts.

---

## 🔒 Security

- **Sandboxed execution** — code runs in a restricted Python namespace with only approved data science imports (`pandas`, `numpy`, `plotly`, `matplotlib`)
- **Code sanitization** — generated code is validated and repaired before execution
- **API key management** — keys are loaded from environment variables or `.env` files, never hardcoded
- **Session isolation** — each browser session operates on its own data and chat history
- **No permanent storage** — uploaded datasets exist only in memory and session cache; no user data is written to external databases

---

## 📝 License

This project was developed as part of the **SURE ProEd Generative AI** Intership.

---

## 👤 Author

**Vikash Sharma**

[![Email](https://img.shields.io/badge/Email-askvikashsharma@gmail.com-D14836?style=flat-square&logo=gmail&logoColor=white)](mailto:askvikashsharma@gmail.com)

Course: Generative AI — SURE ProEd
