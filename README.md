# 🏥 Clinic AI — Natural Language to SQL System

A full-stack AI-powered system that converts plain English questions into SQL queries against a clinic management database, built with **Vanna 2.0**, **FastAPI**, and a custom dark-mode frontend.

---
![Architecture Diagram](Clinic%20NL-to-SQL%20architecture%20diagram.png)

## 🧱 Stack

| Layer         | Technology                                              |
| ------------- | ------------------------------------------------------- |
| Database      | SQLite (`clinic.db`)                                    |
| NL→SQL AI     | Vanna 2.0 Agent                                         |
| LLM Provider  | **Groq — `openai/gpt-oss-120b`** (ultra-fast inference) |
| API Server    | FastAPI + Uvicorn                                       |
| Charts        | Plotly                                                  |
| Backend Data  | Pandas                                                  |
| Frontend      | Vanilla HTML/CSS/JS (`index.html` — single file)        |
| Caching       | In-memory cache (upgrade → Redis optional)              |
| Rate Limiting | Custom middleware (IP-based)                            |
| Logging       | Structured JSON logging                                 |

---

## 📁 Project Structure

```
project/
├── __pycache__/                               # Python bytecode cache (auto-generated)
├── 37a8eec1ce19687d/                          # Vanna agent memory store (ChromaDB)
├── output/                                    # Query output exports
├── .env                                       # API keys (not committed to git)
├── Clinic NL-to-SQL architecture diagram.png  # Architecture diagram
├── Clinic_AI_README.docx                      # Word version of documentation
├── clinic.db                                  # SQLite database (generated)
├── index.html                                 # Single-page dark-mode frontend
├── main.py                                    # FastAPI application entry point
├── README.md                                  # This file
├── requirements.txt                           # Python dependencies
├── seed_memory.py                             # Seeds Q→SQL pairs into Vanna memory
├── setup_database.py                          # Creates schema + seeds data
├── test_12.py                                 # Query test runner (20 questions)
├── test_results.txt                           # Saved test output log
└── vanna_setup.py                             # Vanna 2.0 + Groq LLM configuration
```

---

## 🚀 Setup Instructions

### Step 1 — Clone & Install

```bash
git clone https://github.com/deepak75500/AI-ML-Developer-Intern-Assignment.git
pip install -r requirements.txt
```

### Step 2 — Set Your API Key

Create a `.env` file in the project root:

```env
GROQ_API_KEY=your-groq-key-here
```

> Get a free key at: https://console.groq.com

### Step 3 — Create the Database

```bash
python setup_database.py
```

Expected output:

```
✅  Database created: clinic.db
   Created 200 patients, 15 doctors, 500 appointments, 350 treatments, 300 invoices.
```

### Step 4 — Seed Agent Memory

```bash
python seed_memory.py
```

Expected output:

```
✅  Seeded 16 question→SQL pairs into agent memory.
```

> **What this does:** `seed_memory.py` calls `vn.train()` with curated question/SQL pairs. The Vanna agent uses these as few-shot examples when generating SQL for new questions — seeding significantly improves accuracy.

### Step 5 — Start the API Server

```bash
uvicorn main:app --reload --port 8000
```

API available at: `http://localhost:8000`

### Step 6 — Open the Frontend

Open `index.html` directly in your browser — no server needed, it is a fully static file.

---

## ⚡ One-liner (CI / Reviewer)

```bash
pip install -r requirements.txt && python setup_database.py && python seed_memory.py && uvicorn main:app --port 8000
```

---

## 🧪 Running the Tests

```bash
python test_12.py
```

Runs all 20 natural language questions against the live API and saves output to `test_results.txt`.

---

## 🔌 LLM Provider Configuration

Edit `vanna_setup.py` to configure your provider:

```python
from vanna.integrations.openai import OpenAILlmService

llm = OpenAILlmService(
    api_key=os.environ["GROQ_API_KEY"],
    base_url="https://api.groq.com/openai/v1",
    model="openai/gpt-oss-120b"
)
```

**Alternative providers:**

<details>
<summary>Google Gemini</summary>

```env
# .env
GOOGLE_API_KEY=your-gemini-key-here
```

Get a free key at: https://aistudio.google.com/apikey

</details>

<details>
<summary>Ollama (local, no API key needed)</summary>

```python
llm = OpenAILlmService(
    api_key="ollama",
    base_url="http://localhost:11434/v1",
    model="llama3"
)
```

</details>

---

## 📡 API Documentation

### `POST /chat`

Converts a natural language question into SQL, executes it against `clinic.db`, and returns results with an optional Plotly chart.

**Request:**

```json
{
  "question": "Show me the top 5 patients by total spending"
}
```

**Response:**

```json
{
  "message": "Found 5 record(s) for your question.",
  "sql_query": "SELECT p.first_name, p.last_name, SUM(i.total_amount) AS total_spending FROM patients p JOIN invoices i ON p.id = i.patient_id GROUP BY p.id ORDER BY total_spending DESC LIMIT 5",
  "columns": ["first_name", "last_name", "total_spending"],
  "rows": [
    ["Lakshmi", "Reddy", 22279.47],
    ["Dinesh",  "Bose",  21467.61]
  ],
  "row_count": 5,
  "chart": { "data": ["..."], "layout": {} },
  "chart_type": "bar",
  "cached": false
}
```

> Validation errors return a `message` with explanation and the rejected `sql_query`. No query is executed against the database.

---

### `GET /health`

Returns system status and agent memory item count.

```json
{
  "status": "ok",
  "database": "connected",
  "agent_memory_items": 16
}
```

---

### Validation Rules

| Rule | Detail |
|------|--------|
| SELECT-only | `INSERT` / `UPDATE` / `DELETE` / `DROP` / `ALTER` rejected before execution |
| Forbidden keywords | `EXEC`, `xp_`, `sp_`, `GRANT`, `REVOKE`, `SHUTDOWN` blocked |
| System tables | `sqlite_master` and similar blocked |
| Input length | Empty questions rejected; max 500 characters |

---

## 🏗️ Architecture Overview

```
Browser  (index.html)
    │
    │  POST /chat  { "question": "..." }
    ▼
FastAPI  (main.py)
    ├── Pydantic input validation
    ├── Rate limiter  (20 req / 60 s per IP)
    ├── MD5 cache lookup  ──► return cached result if hit
    ├── Vanna Agent  (vanna_setup.py)
    │       └── Groq  openai/gpt-oss-120b
    │               └── generates SQL
    ├── SQL Validator  (allowlist / blocklist regex)
    ├── SQLite execution  (clinic.db)
    ├── Plotly chart generation
    └── JSON response  ──► browser
```

**Key files and their roles:**

| File | Role |
|------|------|
| `main.py` | FastAPI routes, middleware, validation, chart logic |
| `vanna_setup.py` | Vanna 2.0 agent init + Groq LLM wiring |
| `seed_memory.py` | Trains agent with 16 curated Q→SQL examples |
| `setup_database.py` | Creates SQLite schema, seeds realistic clinic data |
| `test_12.py` | Automated test runner — 20 questions, saves to `test_results.txt` |
| `index.html` | Zero-dependency dark-mode SPA frontend |
| `clinic.db` | SQLite database (200 patients, 15 doctors, 500 appointments) |
| `37a8eec1ce19687d/` | ChromaDB vector store — persists Vanna agent memory between runs |

---

## ✨ Features

| Feature | Detail |
|---------|--------|
| NL→SQL | Plain English → validated SQL via Vanna + Groq |
| Chart generation | Plotly bar/line charts auto-selected by result shape |
| Query caching | Identical questions skip the LLM (MD5-keyed, in-memory) |
| Rate limiting | 20 requests / 60 seconds per IP |
| Structured logging | All pipeline steps logged with timestamps |
| Security | SELECT-only enforcement + keyword blocklist |

---

## 📊 Results

👉 [View Results](./results.md)
