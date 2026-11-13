"""Build audit sheets for GUIDE.md §4 dims 2-4 from results/traces.jsonl.

Labels written here are DRAFTS (rule-based + 2 hand overrides, made by the AI assistant). The author must review and
fill `author_label`; only author labels may be reported as manual results.   Run from starter/:  python -m src.audit
"""
import csv
import json
import re
from pathlib import Path

from .chunking import by_sentence, fixed_size
from .ingestion import load_pages

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "starter/results"
_n = lambda s: re.sub(r"\s+", " ", s).strip()


def write(name, rows):
    with (OUT / name).open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def coherence(pages):
    """Same 10 positions for every strategy: first 10 sorted page_ids, char offset = 40% of page text (fixed before labelling)."""
    rows = []
    for p in sorted(pages, key=lambda p: p.metadata["page_id"])[:10]:
        pos = int(len(p.text) * 0.4)
        for s, ch in (("A", fixed_size(p, 500, 50)), ("B", by_sentence(p, 1000))):
            cur = 0
            for c in ch:
                i = p.text.find(c.text[:40], max(0, cur - 60)); cur = i
                if i <= pos < i + len(c.text):
                    break
            starts = i == 0 or p.text[i - 1] in " " and p.text[i - 2] in ".!?”)" or i == 0
            ends = i + len(c.text) >= len(p.text) or p.text[i + len(c.text) - 1] in ".!?”)"
            mid_word = (not p.text[i - 1:i].isspace() and i > 0) or (i + len(c.text) < len(p.text) and not p.text[i + len(c.text):i + len(c.text) + 1].isspace())
            lab, why = (2, "starts and ends at sentence boundaries") if starts and ends else \
                       (1, "cut at edge but not mid-word; sentence context partly missing") if not mid_word else \
                       (0, "cut mid-word at an edge; ideas truncated")
            rows.append(dict(strategy=s, position=f"{p.metadata['page_id']}@{pos}", chunk_id=c.chunk_id, chunk_text=c.text,
                             draft_label=lab, draft_reason=why, author_label="", author_reason=""))
    return rows + [dict(r, strategy="C") for r in rows if r["strategy"] == "B"]  # C chunks == B chunks


def metadata_and_grounding(traces, pages):
    ref = {(p.document_id, p.page): p for p in pages}
    meta, ground = [], []
    for t in (x for x in traces if x["split"] == "test"):
        for h in t["top3"]:
            p = ref[(h["document_id"], h["page"])]
            checks = dict(
                text_in_page=_n(h["text"]) in p.text, source_ok=h["source"] == p.source,
                printed_ok=h["printed_page"] == p.metadata["printed_page"], section_ok=h["section"] == p.metadata["section"],
                function_ok=h["function"] == p.metadata["function"], year_ok=h["year"] == p.metadata["year"],
                filter_ok=all(h[k] == v for k, v in (t["filter"] or {}).items()))
            meta.append(dict(strategy=t["strategy"], qid=t["qid"], chunk_id=h["chunk_id"], filter=json.dumps(t["filter"]),
                             **checks, draft_label="ok" if all(checks.values()) else "error", author_label="", author_note=""))
        e = t["eval"]
        lab, why = (2, "gold evidence present in top-3 with page metadata") if e["hit_at_3"] else (0, "no relevant evidence in top-3")
        ground.append(dict(strategy=t["strategy"], qid=t["qid"], question=t["question"], hit_at_3=e["hit_at_3"],
                           draft_label=lab, draft_reason=why, author_label="", author_reason=""))
    for g in ground:  # hand overrides after reading top-3 (partial evidence: alternative red-teaming passages on p54-55, no full definition)
        if g["qid"] == "q19" and g["strategy"] in "BC":
            g["draft_label"], g["draft_reason"] = 1, "top-3 are red-teaming passages (p54-55) but none gives the definition; gold p53 absent"
    return meta, ground


def main():
    pages = load_pages(ROOT / "data/pages.jsonl")
    traces = [json.loads(l) for l in (OUT / "traces.jsonl").read_text().splitlines()]
    meta, ground = metadata_and_grounding(traces, pages)
    coh = coherence(pages)
    write("audit_coherence.csv", coh); write("audit_metadata.csv", meta); write("audit_grounding.csv", ground)
    avg = lambda rows, s: round(sum(r["draft_label"] for r in rows if r["strategy"] == s) / sum(r["strategy"] == s for r in rows), 2)
    summ = {s: dict(coherence_mean_of_2=avg(coh, s), coherence_counts={k: sum(r["draft_label"] == k for r in coh if r["strategy"] == s) for k in (0, 1, 2)},
                    metadata_ok=f"{sum(r['draft_label'] == 'ok' for r in meta if r['strategy'] == s)}/{sum(r['strategy'] == s for r in meta)}",
                    grounding_mean_of_2=avg(ground, s), grounding_counts={k: sum(r["draft_label"] == k for r in ground if r["strategy"] == s) for k in (0, 1, 2)})
            for s in "ABC"}
    summ["filter_compliance_C"] = f"{sum(1 for t in traces if t['strategy']=='C' and t['split']=='test' and t['filter'] and all(h[k]==v for h in t['top3'] for k,v in t['filter'].items()))}/{sum(1 for t in traces if t['strategy']=='C' and t['split']=='test' and t['filter'])}"
    summ["note"] = "DRAFT labels by AI assistant, pending author review"
    (OUT / "audit_summary.json").write_text(json.dumps(summ, indent=2) + "\n"); print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
