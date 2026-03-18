import json
import os
import datetime
from pathlib import Path
from loguru import logger
import requests
from requests.adapters import HTTPAdapter, Retry

DATA_DIR = Path(__file__).parent / "data"
PDF_DIR = DATA_DIR / "pdfs"
CHAT_DIR = DATA_DIR / "chats"

PAPER_HISTORY_PATH = DATA_DIR / "paper_history.json"
STARRED_PATH = DATA_DIR / "starred.json"
STATS_PATH = DATA_DIR / "stats.json"


def _ensure_dirs():
    DATA_DIR.mkdir(exist_ok=True)
    PDF_DIR.mkdir(exist_ok=True)
    CHAT_DIR.mkdir(exist_ok=True)


def save_daily_papers(papers, date: str):
    """Save papers list to data/{date}.json"""
    _ensure_dirs()
    data = [p.to_dict() for p in papers]
    path = DATA_DIR / f"{date}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved {len(data)} papers to {path}")


def load_daily_papers(date: str):
    """Load papers from data/{date}.json, returns list of ArxivPaper"""
    from paper import ArxivPaper
    path = DATA_DIR / f"{date}.json"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [ArxivPaper.from_dict(d) for d in data]


def load_daily_papers_raw(date: str):
    """Load raw JSON data for a date"""
    path = DATA_DIR / f"{date}.json"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_available_dates() -> list[str]:
    """Return sorted list of available dates (newest first)"""
    _ensure_dirs()
    import re
    date_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}$')
    dates = []
    for f in DATA_DIR.glob("*.json"):
        if date_pattern.match(f.stem):
            dates.append(f.stem)
    dates.sort(reverse=True)
    return dates


def save_chat_history(arxiv_id: str, messages: list[dict]):
    """Save chat history for a paper."""
    _ensure_dirs()
    safe_id = arxiv_id.replace("/", "_")
    path = CHAT_DIR / f"{safe_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)


def load_chat_history(arxiv_id: str) -> list[dict] | None:
    """Load chat history for a paper. Returns None if not found."""
    safe_id = arxiv_id.replace("/", "_")
    path = CHAT_DIR / f"{safe_id}.json"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_or_download_pdf(arxiv_id: str) -> Path | None:
    """Return cached PDF path, downloading if necessary"""
    _ensure_dirs()
    safe_id = arxiv_id.replace("/", "_")
    pdf_path = PDF_DIR / f"{safe_id}.pdf"
    if pdf_path.exists():
        return pdf_path

    url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    try:
        s = requests.Session()
        retries = Retry(total=3, backoff_factor=1)
        s.mount("https://", HTTPAdapter(max_retries=retries))
        resp = s.get(url, timeout=30)
        resp.raise_for_status()
        with open(pdf_path, "wb") as f:
            f.write(resp.content)
        logger.info(f"Downloaded PDF for {arxiv_id}")
        return pdf_path
    except Exception as e:
        logger.error(f"Failed to download PDF for {arxiv_id}: {e}")
        return None


# --- Paper History (deduplication) ---

def load_paper_history() -> dict:
    """Load paper history: {arxiv_id: first_seen_date}"""
    _ensure_dirs()
    if not PAPER_HISTORY_PATH.exists():
        return {}
    with open(PAPER_HISTORY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_paper_history(history: dict):
    """Save paper history."""
    _ensure_dirs()
    with open(PAPER_HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def update_paper_history(papers, date: str):
    """Add papers to history if not already present."""
    history = load_paper_history()
    for p in papers:
        aid = p.arxiv_id if hasattr(p, 'arxiv_id') else p.get('arxiv_id', '')
        if aid and aid not in history:
            history[aid] = date
    save_paper_history(history)


# --- Starred Papers ---

def load_starred_papers() -> dict:
    """Load starred papers: {arxiv_id: {paper_data, starred_date, notes}}"""
    _ensure_dirs()
    if not STARRED_PATH.exists():
        return {}
    with open(STARRED_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_starred_papers(starred: dict):
    """Save starred papers."""
    _ensure_dirs()
    with open(STARRED_PATH, "w", encoding="utf-8") as f:
        json.dump(starred, f, ensure_ascii=False, indent=2)


def star_paper(arxiv_id: str, paper_data: dict, notes: str = ""):
    """Star a paper."""
    starred = load_starred_papers()
    starred[arxiv_id] = {
        "paper_data": paper_data,
        "starred_date": datetime.datetime.now().strftime('%Y-%m-%d'),
        "notes": notes,
    }
    save_starred_papers(starred)


def unstar_paper(arxiv_id: str):
    """Unstar a paper."""
    starred = load_starred_papers()
    starred.pop(arxiv_id, None)
    save_starred_papers(starred)


# --- Reading Statistics ---

def load_stats() -> dict:
    """Load stats: {arxiv_id: {views, last_viewed, chatted}}"""
    _ensure_dirs()
    if not STATS_PATH.exists():
        return {}
    with open(STATS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_stats(stats: dict):
    """Save stats."""
    _ensure_dirs()
    with open(STATS_PATH, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)


def record_paper_view(arxiv_id: str):
    """Record a paper view event."""
    stats = load_stats()
    now = datetime.datetime.now().isoformat()
    if arxiv_id not in stats:
        stats[arxiv_id] = {"views": 0, "last_viewed": None, "chatted": False}
    stats[arxiv_id]["views"] += 1
    stats[arxiv_id]["last_viewed"] = now
    save_stats(stats)


def record_paper_chat(arxiv_id: str):
    """Record that a paper was chatted about."""
    stats = load_stats()
    if arxiv_id not in stats:
        stats[arxiv_id] = {"views": 0, "last_viewed": None, "chatted": False}
    stats[arxiv_id]["chatted"] = True
    save_stats(stats)
