import json
import os
from pathlib import Path
from loguru import logger
import requests
from requests.adapters import HTTPAdapter, Retry

DATA_DIR = Path(__file__).parent / "data"
PDF_DIR = DATA_DIR / "pdfs"


def _ensure_dirs():
    DATA_DIR.mkdir(exist_ok=True)
    PDF_DIR.mkdir(exist_ok=True)


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
    dates = []
    for f in DATA_DIR.glob("*.json"):
        dates.append(f.stem)
    dates.sort(reverse=True)
    return dates


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
