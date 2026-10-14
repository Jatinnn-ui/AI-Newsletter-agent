# Submission — AI Developer Assignment: Newsletter Agent

A mini autonomous AI agent that turns one plain-English goal into a researched,
summarized, self-reviewed newsletter (HTML + Markdown) and simulates delivery by
saving the files. Built on **pure LangGraph** with **Google Gemini**, a FastAPI
backend, and a React + TypeScript frontend.

## Requirements checklist

| # | Requirement | Done | Where |
| --- | --- | :---: | --- |
| 1 | **Goal input** — plain English goal | ✅ | `run_newsletter_agent(goal)`; default goal matches the brief (`backend/app/cli.py`) |
| 2a | Research latest AI agent news (search tool) | ✅ | `backend/app/tools/web_search.py` (Tavily) + `article_retrieval.py` |
| 2b | Summarize the top 5–7 articles | ✅ | `nodes/summarize.py`; `article_count` 3–7, default 5 |
| 2c | Generate a clean newsletter (HTML **and** Markdown) | ✅ | `tools/newsletter_renderer.py` |
| 2d | Simulate sending (save file / print subject + content) | ✅ | `nodes/output.py` saves files; `delivery_note` + UI "Simulated delivery · no email sent" |
| 3a | Multi-step reasoning: planning → research → writing → review → output | ✅ | `backend/app/agent/graph.py` (planner → research → summarize → writer → critic → revision → output) |
| 3b | Tool use (≥ 2–3 tools) | ✅ | web search, article retrieval, newsletter renderer/storage — plus Gemini structured calls; every call shown in the UI activity feed |
| 3c | Self-reflection / critique that improves the output | ✅ | `nodes/review.py` critic (rules + LLM) → bounded `revision` loop |
| 3d | Autonomous — one function call does the full job | ✅ | `from newsletter_agent import run_newsletter_agent` |
| 3e | Toggle: Fully Autonomous ↔ Human-in-the-Loop | ✅ | `ExecutionMode`; HITL gates in the graph; UI mode selector |
| 3f | Clean, well-structured, readable code | ✅ | layered `tools / agent / nodes / services / api`, typed Pydantic models |

### Tech stack

- **Pure LangGraph** (`langgraph` — `StateGraph`, `interrupt()`, SQLite checkpointer)
- **Google Gemini** (`google-genai`, structured JSON output)
- **Frontend**: React + TypeScript + Vite + Tailwind (responsive, both execution modes)

## The one-call entry point

```python
# from backend/
from newsletter_agent import run_newsletter_agent, RunOptions

# Fully autonomous, live (needs GEMINI_API_KEY + TAVILY_API_KEY)
result = run_newsletter_agent("Create a weekly newsletter on the latest AI agent news and send it to our subscribers.")
print(result.status, result.subject, result.html_path)

# Offline demo — no keys, no network (labelled fixture data)
demo = run_newsletter_agent("Weekly AI agent news", RunOptions(deterministic=True))
```

## Fastest way to see it run (no API keys needed)

```bash
# Backend (terminal 1)
cd backend
python -m venv .venv && .venv\Scripts\Activate.ps1   # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
python -m app.cli --deterministic                     # autonomous demo run, prints subject + Markdown
python -m app.cli --deterministic --mode hitl         # Human-in-the-Loop: asks you to approve

# Full UI (keys optional; without keys the UI runs in demo mode)
uvicorn app.main:app --reload --port 8000             # terminal 1
cd ../frontend && npm install && npm run dev          # terminal 2 → http://127.0.0.1:5173
```

For live research add keys to `backend/.env` (`GEMINI_API_KEY`, `TAVILY_API_KEY`); see `.env.example`.

## Verified

- `pytest` — offline test suite passes (no keys/network); opt-in live test with real Tavily + Gemini passes.
- `npm run build` — TypeScript + Vite production build clean.
- `npm run e2e` — headless-browser journey passes: autonomous run, HITL article edit + approve, revision, draft approve + save, cancel, history filter, mobile (no horizontal overflow at 320–768px).

See [`README.md`](README.md) for architecture, the full API, security notes, and deployment.
