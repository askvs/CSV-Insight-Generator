# 📊 CSV Insight Generator

An AI-powered Streamlit web application that lets you upload any CSV dataset and ask open-ended questions about your data. The agent writes and executes real Python code to analyze your data, generates visualizations, and delivers executive-style reports.

## ✨ Features

- **Upload & Profile** — Drop any CSV file and get instant dataset statistics (rows, columns, memory usage, missing values)
- **Chat Interface** — Ask natural language questions about your data via an interactive chat UI
- **AI Agent** — Powered by Groq LLM (Qwen/GPT models) with tool-calling for code generation and execution
- **Sandboxed Execution** — Python code runs in a secure sandbox with restricted imports
- **Visualizations** — Auto-generates matplotlib charts and visual intelligence breakdowns
- **PDF Reports** — Download executive PDF reports with findings, charts, and executed code

## 🛠️ Tech Stack

- **Frontend**: [Streamlit](https://streamlit.io/)
- **LLM Backend**: [Groq API](https://groq.com/) (Qwen 3.8-27B, GPT-OSS models)
- **Data Processing**: Pandas, NumPy
- **Visualization**: Matplotlib
- **PDF Generation**: ReportLab

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- A [Groq API Key](https://console.groq.com/keys)

### Local Setup

```bash
# Clone the repository
git clone https://github.com/askvs/CSV-Insight-Generator.git
cd CSV-Insight-Generator

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set your API key
echo "GROQ_API_KEY=your_key_here" > .env

# Run the app
streamlit run app.py
```

### Deployed Version

This app is deployed on **Streamlit Community Cloud**:
🔗 [csv-insight-generator.streamlit.app](https://csv-insight-generator.streamlit.app)

## 📁 Project Structure

```
CSV-Insight-Generator/
├── app.py                  # Main Streamlit application
├── src/
│   ├── __init__.py         # Package init
│   ├── agent.py            # CSVInsightAgent — LLM tool-calling loop
│   ├── profiler.py         # CSV loading & dataset profiling
│   ├── prompts.py          # System prompts & tool definitions
│   ├── reporter.py         # PDF report generation
│   └── sandbox.py          # Sandboxed Python code execution
├── .streamlit/
│   └── config.toml         # Streamlit server configuration
├── requirements.txt        # Python dependencies
└── README.md               # This file
```

## 🔒 Security

- Code execution is sandboxed with restricted imports (only data science libraries allowed)
- API keys are managed via environment variables or Streamlit Secrets
- No user data is stored permanently

## 📝 License

This project is for educational purposes as part of the SURE ProEd Generative AI course.

## 👤 Author

**Vikash Sharma**  
- Email: askvikashsharma@gmail.com
- Course: Generative AI — SURE ProEd
