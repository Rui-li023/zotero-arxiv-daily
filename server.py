import os
import json
import asyncio
import re
import datetime
import threading
from pathlib import Path
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv(override=True)

from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
import arxiv

from storage import (
    list_available_dates,
    load_daily_papers_raw,
    get_or_download_pdf,
    save_daily_papers,
    save_chat_history,
    load_chat_history,
    DATA_DIR,
)
from llm import LLM, set_global_llm, get_llm
from paper import ArxivPaper
from construct_email import render_email, send_email
from recommender import rerank_paper
from loguru import logger

# --- Config ---

CONFIG_PATH = Path(__file__).parent / "config.json"

def load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_config(cfg: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# Server LLM password (required to use server-side API key)
SERVER_LLM_PASSWORD = os.getenv("SERVER_LLM_PASSWORD", "")

# Email config from env
SMTP_SERVER = os.getenv("SMTP_SERVER", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SENDER = os.getenv("SENDER", "")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD", "")
ARXIV_QUERY = os.getenv("ARXIV_QUERY", "cat:cs.AI+cs.CV+cs.LG+cs.CL+cs.RO")
MAX_PAPER_NUM = int(os.getenv("MAX_PAPER_NUM", "25"))

# Zotero config from env
ZOTERO_ID = os.getenv("ZOTERO_ID", "")
ZOTERO_KEY = os.getenv("ZOTERO_KEY", "")
ZOTERO_IGNORE = os.getenv("ZOTERO_IGNORE", "")

# Mount static files
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

# --- Email Pipeline ---

def get_email_receivers() -> list[str]:
    """Get receivers from config.json, fall back to env RECEIVER."""
    cfg = load_config()
    receivers = cfg.get("email_receivers", [])
    if not receivers:
        env_receiver = os.getenv("RECEIVER", "")
        if env_receiver:
            receivers = [r.strip() for r in env_receiver.split(",") if r.strip()]
    return receivers


def run_daily_pipeline():
    """Fetch papers from arXiv, process with LLM, save JSON, and send email."""
    import feedparser
    from main import get_arxiv_paper, get_zotero_corpus, filter_corpus

    today = datetime.datetime.now().strftime('%Y-%m-%d')
    logger.info(f"Running daily pipeline for {today}...")

    try:
        papers = get_arxiv_paper(ARXIV_QUERY, debug=False)
    except Exception as e:
        logger.error(f"Failed to fetch arXiv papers: {e}")
        return

    if not papers:
        logger.info("No new papers found today.")
        return

    # Rerank papers using Zotero corpus if credentials are available
    if ZOTERO_ID and ZOTERO_KEY:
        try:
            logger.info("Retrieving Zotero corpus for reranking...")
            corpus = get_zotero_corpus(ZOTERO_ID, ZOTERO_KEY)
            logger.info(f"Retrieved {len(corpus)} papers from Zotero.")
            if ZOTERO_IGNORE:
                corpus = filter_corpus(corpus, ZOTERO_IGNORE)
                logger.info(f"Remaining {len(corpus)} papers after filtering.")
            if corpus:
                papers = rerank_paper(papers, corpus)
                logger.info("Papers reranked by Zotero similarity.")
            else:
                logger.warning("Zotero corpus is empty after filtering. Using default ordering.")
                for i, p in enumerate(papers):
                    p.score = max(10 - i * 0.3, 5)
        except Exception as e:
            logger.error(f"Zotero reranking failed: {e}. Using default ordering.")
            for i, p in enumerate(papers):
                p.score = max(10 - i * 0.3, 5)
    else:
        logger.warning("Zotero credentials not configured. Papers will not be ranked by research interest.")
        for i, p in enumerate(papers):
            p.score = max(10 - i * 0.3, 5)

    if MAX_PAPER_NUM != -1:
        papers = papers[:MAX_PAPER_NUM]

    logger.info(f"Processing {len(papers)} papers...")
    html = render_email(papers)  # Triggers highlight/tldr/affiliations

    save_daily_papers(papers, today)
    logger.success(f"Saved {len(papers)} papers to data/{today}.json")

    # Send email to all configured receivers
    receivers = get_email_receivers()
    if receivers and SMTP_SERVER and SENDER and SENDER_PASSWORD:
        for receiver in receivers:
            try:
                send_email(SENDER, receiver, SENDER_PASSWORD, SMTP_SERVER, SMTP_PORT, html)
                logger.success(f"Email sent to {receiver}")
            except Exception as e:
                logger.error(f"Failed to send email to {receiver}: {e}")
    else:
        logger.info("Email sending skipped: missing SMTP config or no receivers configured.")


def check_and_run_pipeline():
    """Check if today's data exists; if not, run the pipeline in a background thread."""
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    data = load_daily_papers_raw(today)
    if data is not None:
        logger.info(f"Data for {today} already exists ({len(data)} papers). Skipping pipeline.")
        return

    logger.info(f"No data for {today}. Starting pipeline in background...")
    thread = threading.Thread(target=run_daily_pipeline, daemon=True)
    thread.start()


# --- Scheduled daily email ---

_scheduler_task = None

async def daily_scheduler():
    """Run pipeline daily at configured time."""
    while True:
        cfg = load_config()
        target_hour = cfg.get("email_schedule_hour", 9)
        target_minute = cfg.get("email_schedule_minute", 0)

        now = datetime.datetime.now()
        target = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
        if target <= now:
            target += datetime.timedelta(days=1)

        wait_seconds = (target - now).total_seconds()
        logger.info(f"Next scheduled pipeline at {target.strftime('%Y-%m-%d %H:%M')} (in {wait_seconds/3600:.1f}h)")

        await asyncio.sleep(wait_seconds)

        # Run pipeline in thread to not block event loop
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, run_daily_pipeline)


# --- App Lifecycle ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler_task

    # Init LLM
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
    model = os.getenv("MODEL_NAME", "gpt-4o")
    lang = os.getenv("LANGUAGE", "English")
    if api_key:
        set_global_llm(api_key=api_key, base_url=base_url, model=model, lang=lang)
        logger.info("LLM initialized from environment")

    # Check if today's data exists; if not, run pipeline
    check_and_run_pipeline()

    # Start daily scheduler
    _scheduler_task = asyncio.create_task(daily_scheduler())

    yield

    # Cleanup
    if _scheduler_task:
        _scheduler_task.cancel()


app = FastAPI(title="arXiv Daily Papers", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# --- API endpoints ---


@app.get("/api/papers/dates")
async def get_dates():
    return {"dates": list_available_dates()}


@app.get("/api/papers")
async def get_papers(date: str = Query(..., description="Date in YYYY-MM-DD format")):
    data = load_daily_papers_raw(date)
    if data is None:
        raise HTTPException(status_code=404, detail=f"No data for {date}")
    return {"date": date, "papers": data}


@app.get("/api/paper/{arxiv_id:path}/pdf")
async def get_pdf(arxiv_id: str):
    pdf_path = get_or_download_pdf(arxiv_id)
    if pdf_path is None:
        raise HTTPException(status_code=404, detail="PDF not found")
    return FileResponse(str(pdf_path), media_type="application/pdf")


@app.get("/api/paper/{arxiv_id:path}/fulltext")
async def get_fulltext(arxiv_id: str):
    """获取论文全文（从arXiv HTML页面提取）"""
    try:
        # 创建临时Paper对象获取全文
        client = arxiv.Client()
        search = arxiv.Search(id_list=[arxiv_id])
        results = list(client.results(search))
        if not results:
            raise HTTPException(status_code=404, detail="Paper not found on arXiv")

        paper = ArxivPaper(results[0])
        full_text = paper.full_text

        if full_text is None:
            raise HTTPException(status_code=404, detail="Full text not available for this paper")

        return {"arxiv_id": arxiv_id, "full_text": full_text}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get full text for {arxiv_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/paper/{arxiv_id:path}/content")
async def get_paper_content(arxiv_id: str):
    """获取论文内容（优先PDF）"""
    import base64

    try:
        # 优先获取PDF
        pdf_path = get_or_download_pdf(arxiv_id)
        if pdf_path and pdf_path.exists():
            with open(pdf_path, "rb") as f:
                pdf_base64 = base64.b64encode(f.read()).decode("utf-8")
            return {"arxiv_id": arxiv_id, "type": "pdf", "content": pdf_base64}

        raise HTTPException(status_code=404, detail="No PDF available for this paper")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get content for {arxiv_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class ChatRequest(BaseModel):
    messages: list[dict]
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    server_password: str | None = None  # Password to use server-side LLM


@app.get("/api/llm/status")
async def llm_status():
    """Check if server LLM is configured and whether password is required."""
    has_llm = os.getenv("OPENAI_API_KEY") is not None
    needs_password = bool(SERVER_LLM_PASSWORD)
    return {"has_server_llm": has_llm, "needs_password": needs_password}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    if req.api_key:
        # Client mode: user provides their own key
        llm = LLM(api_key=req.api_key, base_url=req.base_url or "https://api.openai.com/v1", model=req.model or "gpt-4o")
    else:
        # Server mode: verify password first
        if SERVER_LLM_PASSWORD:
            if not req.server_password or req.server_password != SERVER_LLM_PASSWORD:
                raise HTTPException(status_code=403, detail="Invalid password for server LLM")
        try:
            llm = get_llm()
        except Exception:
            raise HTTPException(status_code=400, detail="No LLM configured. Provide an API key or set server environment variables.")

    def event_stream():
        """Sync generator — Starlette runs it in a threadpool so the
        blocking LLM calls don't stall the event-loop, and each yield
        is flushed to the client immediately."""
        try:
            for token in llm.generate_stream(req.messages):
                data = json.dumps({"token": token}, ensure_ascii=False)
                yield f"data: {data}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            error_data = json.dumps({"error": str(e)})
            yield f"data: {error_data}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


class NewPaperRequest(BaseModel):
    arxiv_input: str  # arxiv ID or URL


@app.post("/api/paper/new")
async def add_new_paper(req: NewPaperRequest):
    # Extract arxiv ID from URL or raw input
    arxiv_id = req.arxiv_input.strip()
    # Handle URLs like https://arxiv.org/abs/2401.12345
    match = re.search(r'(\d{4}\.\d{4,5})', arxiv_id)
    if match:
        arxiv_id = match.group(1)
    else:
        raise HTTPException(status_code=400, detail="Invalid arXiv ID or URL")

    try:
        client = arxiv.Client()
        search = arxiv.Search(id_list=[arxiv_id])
        results = list(client.results(search))
        if not results:
            raise HTTPException(status_code=404, detail="Paper not found on arXiv")

        paper = ArxivPaper(results[0])

        # Compute properties (these are cached_property, accessing triggers computation)
        _ = paper.highlight
        _ = paper.tldr
        _ = paper.affiliations
        _ = paper.code_url

        return {"paper": paper.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch paper {arxiv_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- Chat History API ---

@app.get("/api/chat/history/{arxiv_id:path}")
async def get_chat_history(arxiv_id: str):
    """Load saved chat history for a paper."""
    messages = load_chat_history(arxiv_id)
    if messages is None:
        return {"messages": []}
    return {"messages": messages}


class SaveChatRequest(BaseModel):
    messages: list[dict]


@app.post("/api/chat/history/{arxiv_id:path}")
async def save_chat(arxiv_id: str, req: SaveChatRequest):
    """Save chat history for a paper."""
    save_chat_history(arxiv_id, req.messages)
    return {"status": "ok"}


# --- Config API ---

@app.get("/api/config/prompts")
async def get_prompts():
    """Return chat prompts from config.json."""
    cfg = load_config()
    return {
        "chat_system_prompt": cfg.get("chat_system_prompt", ""),
        "chat_auto_analyze_prompt": cfg.get("chat_auto_analyze_prompt", ""),
    }


@app.get("/api/config/email")
async def get_email_config():
    """Return email configuration."""
    cfg = load_config()
    return {
        "email_receivers": cfg.get("email_receivers", []),
        "email_schedule_hour": cfg.get("email_schedule_hour", 9),
        "email_schedule_minute": cfg.get("email_schedule_minute", 0),
        "smtp_configured": bool(SMTP_SERVER and SENDER),
    }


class EmailConfigRequest(BaseModel):
    email_receivers: list[str] | None = None
    email_schedule_hour: int | None = None
    email_schedule_minute: int | None = None


@app.post("/api/config/email")
async def update_email_config(req: EmailConfigRequest):
    """Update email configuration in config.json."""
    cfg = load_config()
    if req.email_receivers is not None:
        cfg["email_receivers"] = req.email_receivers
    if req.email_schedule_hour is not None:
        cfg["email_schedule_hour"] = req.email_schedule_hour
    if req.email_schedule_minute is not None:
        cfg["email_schedule_minute"] = req.email_schedule_minute
    save_config(cfg)
    return {"status": "ok"}


@app.post("/api/email/send-now")
async def send_email_now():
    """Manually trigger pipeline and email sending."""
    thread = threading.Thread(target=run_daily_pipeline, daemon=True)
    thread.start()
    return {"status": "pipeline started"}


@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
