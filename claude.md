# zotero-arxiv-daily

## Project Overview

Daily arXiv paper recommendation system. Fetches new papers from arXiv RSS, ranks them against user's Zotero library using embedding similarity, generates LLM-powered analysis (highlight + TLDR), then delivers via email and/or a web interface.

## Architecture

Three operating modes:

1. **Email Pipeline** (`python main.py`) — full pipeline: Zotero corpus → arXiv fetch → rerank → LLM analysis → email + save JSON
2. **Web Pipeline** (`python main.py --web_only --debug`) — lightweight: arXiv fetch → LLM analysis → save JSON only (no Zotero, no email)
3. **Web Server** (`python server.py`) — FastAPI serving saved JSON data + LLM chat + integrated email pipeline (on startup & scheduled)

## File Map

| File | Role |
|---|---|
| `main.py` | CLI entry point. Orchestrates the pipeline. Flags: `--debug` (5 test papers), `--web_only` (skip Zotero/email) |
| `paper.py` | `ArxivPaper` class. Wraps `arxiv.Result` with `cached_property` for `highlight`, `tldr`, `affiliations`, `code_url`, `tex`. Has `to_dict()`/`from_dict()` for JSON serialization |
| `recommender.py` | `rerank_paper()` — ranks candidates against Zotero corpus via `sentence-transformers` cosine similarity with time-decay weighting |
| `llm.py` | `LLM` class wrapping OpenAI-compatible API. `generate()` (blocking) and `generate_stream()` (SSE streaming). Global singleton via `set_global_llm()`/`get_llm()` |
| `construct_email.py` | `render_email()` builds HTML email. Uses `ThreadPoolExecutor` to process papers concurrently (triggers all `cached_property` computations). `send_email()` via SMTP |
| `storage.py` | JSON persistence layer. `save_daily_papers()` → `data/{date}.json`, `load_daily_papers()`, `list_available_dates()`, `get_or_download_pdf()` |
| `server.py` | FastAPI web server. API endpoints + static file serving + integrated email pipeline + daily scheduler |
| `config.json` | Runtime config: chat prompts, email receivers, schedule settings (gitignored) |
| `static/` | SPA frontend (Vanilla JS). Dark theme, split-panel layout: paper list + detail panel with LLM chat |

## API Endpoints (server.py)

| Method | Path | Description |
|---|---|---|
| GET | `/api/papers/dates` | Available date list |
| GET | `/api/papers?date=YYYY-MM-DD` | Papers for a date |
| GET | `/api/paper/{arxiv_id}/pdf` | PDF proxy with caching |
| POST | `/api/chat` | SSE streaming LLM chat (requires `server_password` for server mode) |
| POST | `/api/paper/new` | Fetch + analyze a new paper by arXiv ID/URL |
| GET | `/api/llm/status` | Check if server LLM is configured and password-protected |
| GET | `/api/config/prompts` | Get chat prompt templates from config.json |
| GET | `/api/config/email` | Get email configuration |
| POST | `/api/config/email` | Update email receivers and schedule |
| POST | `/api/email/send-now` | Manually trigger pipeline + email |
| GET | `/` | Serves `static/index.html` |

## Configuration

### Environment (.env)
- `OPENAI_API_KEY`, `OPENAI_API_BASE`, `MODEL_NAME` — LLM provider (OpenAI-compatible)
- `SERVER_LLM_PASSWORD` — password required in web UI to use server's LLM key
- `ARXIV_QUERY` — arXiv RSS categories (e.g. `cat:cs.AI+cs.CV+cs.LG+cs.CL+cs.RO`)
- `LANGUAGE` — LLM output language
- `SMTP_SERVER`, `SMTP_PORT`, `SENDER`, `SENDER_PASSWORD` — SMTP email settings
- `RECEIVER` — fallback email receiver(s), comma-separated

### Runtime Config (config.json)
- `chat_system_prompt` — system prompt template for LLM chat (supports `{title}`, `{summary}`, `{arxiv_id}` placeholders)
- `chat_auto_analyze_prompt` — auto-analysis prompt sent when opening a paper
- `email_receivers` — list of email addresses to receive daily digest
- `email_schedule_hour`, `email_schedule_minute` — daily schedule time

## Key Design Decisions

- **`cached_property` pattern**: `ArxivPaper` properties like `highlight`, `tldr`, `affiliations` are computed lazily and cached. `render_email()` triggers all of them via `process_single_paper()`. After that, `to_dict()` serializes at zero cost.
- **`from_dict()` deserialization**: Creates a lightweight `ArxivPaper` with `_paper=None`. All property getters check `if self._paper is None` and read from `self._data` dict instead.
- **LLM password protection**: Server-side API key is protected by `SERVER_LLM_PASSWORD`. Frontend stores password in `localStorage`. Two modes: server (shared key + password) / client (user's own key).
- **Concurrent processing**: Email rendering uses `ThreadPoolExecutor(max_workers=20)` for parallel LLM calls.
- **Integrated email**: server.py checks on startup if today's data exists; if not, runs the full pipeline and sends emails. Also runs a daily scheduler.
- **Thinking output**: `<think>...</think>` tags from LLMs (e.g. DeepSeek) are collapsed in the chat UI using `<details>` elements.

## Common Commands

```bash
# Generate test data (5 papers, no Zotero needed)
python main.py --debug --web_only

# Start web server (auto-fetches today's papers + sends email if needed)
python server.py

# Full pipeline with Zotero (requires Zotero + SMTP config)
python main.py
```

## Data Flow

```
arXiv RSS → arxiv.Search → ArxivPaper objects
  → rerank_paper() (Zotero similarity, optional)
  → render_email() triggers: highlight, tldr, affiliations, code_url
  → save_daily_papers() → data/YYYY-MM-DD.json
  → send_email() to configured receivers

Web: server.py reads data/*.json → API → static/app.js renders UI
     LLM chat: frontend → /api/chat (SSE) → llm.generate_stream()
     Startup: check today's data → run pipeline if missing → send email
     Scheduler: daily at configured time → run pipeline → send email
```

## Style

- Python 3.11+, type hints, `loguru` for logging
- Frontend: Vanilla JS SPA, CSS custom properties, dark theme
- Font stack: DM Serif Display + IBM Plex Sans/Mono
- Color accent: purple (#c8a2f8) inherited from email template gradient (#667eea/#764ba2)
