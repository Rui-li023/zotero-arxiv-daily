import os
import json
import asyncio
import re
from pathlib import Path
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
    DATA_DIR,
)
from llm import LLM, set_global_llm, get_llm
from paper import ArxivPaper
from loguru import logger

app = FastAPI(title="arXiv Daily Papers")

# Server LLM password (required to use server-side API key)
SERVER_LLM_PASSWORD = os.getenv("SERVER_LLM_PASSWORD", "")

# Mount static files
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.on_event("startup")
async def startup():
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
    model = os.getenv("MODEL_NAME", "gpt-4o")
    lang = os.getenv("LANGUAGE", "English")
    if api_key:
        set_global_llm(api_key=api_key, base_url=base_url, model=model, lang=lang)
        logger.info("LLM initialized from environment")


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

    async def event_stream():
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


@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
