"""Check every evidence_quote occurs verbatim (whitespace-normalised) on its gold page, and the split/filter rules. Run: python3 -I benchmark/verify_gold.py"""
import json, re
from pathlib import Path
R = Path(__file__).resolve().parent.parent
n = lambda s: re.sub(r"\s+", " ", s)
pages = {(p["document_id"], p["page"]): p for p in map(json.loads, open(R / "data/pages.jsonl"))}
Q = [json.loads(l) for l in open(R / "benchmark/questions.jsonl")]
bad = [q["id"] for q in Q if (q["gold_source_id"], q["gold_page"]) not in pages or n(q["evidence_quote"]) not in n(pages[(q["gold_source_id"], q["gold_page"])]["text"])]
# filters must match the gold page's own metadata (no impossible filter)
for q in Q:
    p = pages.get((q["gold_source_id"], q["gold_page"]))
    if p and any(p.get(k) != v for k, v in q.get("filter", {}).items()): bad.append(q["id"] + ":filter")
dev, test = [q for q in Q if q["split"] == "dev"], [q for q in Q if q["split"] == "test"]
flt = [q for q in Q if "filter" in q]
assert len(Q) >= 20 and len(dev) >= 15 and len(test) >= 5 and len(flt) >= 3 and any(q["split"] == "test" for q in flt)
assert len({q["id"] for q in Q}) == len(Q)
print(f"{len(Q)} questions dev={len(dev)} test={len(test)} filter={len(flt)} bad={bad}")
assert not bad
