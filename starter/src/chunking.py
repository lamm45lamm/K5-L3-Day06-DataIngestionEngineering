"""Strategy A: fixed-size windows. Strategy B/C: sentence-aware groups (paragraph breaks were lost in extraction)."""
import re

from .models import Chunk, DocumentPage

_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z“(•\d])")


def _mk(page: DocumentPage, i: int, text: str) -> Chunk:
    return Chunk(chunk_id=f"{page.metadata['page_id']}#c{i:02d}", document_id=page.document_id, source=page.source,
                 page=page.page, text=text, metadata=dict(page.metadata))


def fixed_size(page: DocumentPage, size: int, overlap: int) -> list[Chunk]:
    step, t = size - overlap, page.text
    return [_mk(page, i, t[s:s + size]) for i, s in enumerate(range(0, max(len(t) - overlap, 1), step))]


def by_sentence(page: DocumentPage, max_size: int) -> list[Chunk]:
    """Greedy-pack whole sentences up to max_size; a sentence longer than max_size is hard-split."""
    parts = []
    for s in _SENT.split(page.text):
        parts += [s[i:i + max_size] for i in range(0, len(s), max_size)]
    out, cur = [], ""
    for s in parts:
        if cur and len(cur) + 1 + len(s) > max_size:
            out.append(cur); cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur: out.append(cur)
    return [_mk(page, i, t) for i, t in enumerate(out)]
