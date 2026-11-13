"""Automatic Hit@1 / Evidence Hit@3. Human labels (coherence, grounding) are separate."""
import re
from collections import defaultdict
from typing import Any

_n = lambda s: re.sub(r"\s+", " ", s).strip()


def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any]:
    """hit = gold document+page AND full evidence_quote inside the chunk text (GUIDE.md §4.1).
    page_match (no quote needed) is kept to expose evidence split across chunks."""
    quote = _n(question["evidence_quote"])
    rows = []
    for rank, h in enumerate(hits, 1):
        pm = h["document_id"] == question["gold_source_id"] and h["page"] == question["gold_page"]
        rows.append(dict(rank=rank, chunk_id=h["chunk_id"], score=round(h["score"], 4), page_match=pm,
                         evidence_full=pm and quote in _n(h["text"])))
    first = next((r["rank"] for r in rows if r["evidence_full"]), None)
    return dict(hit_at_1=bool(rows and rows[0]["evidence_full"]), hit_at_3=first is not None, first_hit_rank=first,
                split_evidence=first is None and any(r["page_match"] for r in rows), ranks=rows)


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    g = defaultdict(list)
    for t in traces:
        g[(t["strategy"], t["split"])].append(t)
        g[(t["strategy"], "all")].append(t)
    out = {}
    for (s, sp), ts in sorted(g.items()):
        out.setdefault(s, {})[sp] = dict(
            n=len(ts), hit_at_1=sum(t["eval"]["hit_at_1"] for t in ts), evidence_hit_at_3=sum(t["eval"]["hit_at_3"] for t in ts),
            page_only_misses=sum(t["eval"]["split_evidence"] for t in ts))
    return out
