"""Load pre-extracted pages (data/pages.jsonl, built by scripts/build_corpus.py from the PDFs)."""
import json
import re
import unicodedata
from pathlib import Path

from .models import DocumentPage


def normalize_text(text: str) -> str:
    """NFC + whitespace collapse. No NFKC: gold quotes keep curly quotes and dashes."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


def load_pages(path: Path) -> list[DocumentPage]:
    pages = []
    for line in path.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        pages.append(DocumentPage(
            document_id=r["document_id"], source=r["source"], page=r["page"], text=normalize_text(r["text"]),
            metadata={k: r[k] for k in ("page_id", "printed_page", "section", "function", "year")}))
    return pages
