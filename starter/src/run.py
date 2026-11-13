"""Pipeline: pages -> 3 strategies (A fixed, B sentence, C = B + metadata filter) -> pgvector -> top-3 traces.

Run from starter/:  python -m src.run
"""
import json
import os
import statistics
import time
from pathlib import Path

from dotenv import load_dotenv

from .chunking import by_sentence, fixed_size
from .embeddings import MyEmbedder
from .evaluation import evaluate_query, summarize
from .ingestion import load_pages
from .store import PgVectorStore

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "starter/results"
DEFAULT_URL = "postgresql://day6:day6_local_only@127.0.0.1:55433/day6_lab"  # local lab DB only
CFG = dict(model="BAAI/bge-small-en-v1.5", A=dict(size=500, overlap=50), B=dict(max_size=1000), top_k=3)


def main() -> None:
    load_dotenv(ROOT / "starter/.env")
    pages = load_pages(ROOT / "data/pages.jsonl")
    if len(pages) < 30:
        raise SystemExit(f"need >=30 content pages, have {len(pages)}")
    questions = [json.loads(l) for l in (ROOT / "benchmark/questions.jsonl").read_text().splitlines()]

    emb = MyEmbedder(CFG["model"])
    store = PgVectorStore(os.getenv("DATABASE_URL") or DEFAULT_URL, emb.dimensions)
    store.create_schema()

    chunks = {"A": [c for p in pages for c in fixed_size(p, **CFG["A"])],
              "B": [c for p in pages for c in by_sentence(p, **CFG["B"])]}
    chunks["C"] = chunks["B"]  # C differs from B only by query-time filtering
    stats, vecs = {}, {}
    for s in "ABC":
        t0 = time.time()
        key = "B" if s == "C" else s
        if key not in vecs:
            vecs[key] = emb.embed_documents([c.text for c in chunks[key]])
        store.upsert(s, chunks[s], vecs[key])  # idempotent: re-run does not duplicate
        lens = [len(c.text) for c in chunks[s]]
        stats[s] = dict(chunks=len(lens), total_chars=sum(lens), len_min=min(lens), len_median=statistics.median(lens),
                        len_max=max(lens), db_rows=store.count(s), ingest_seconds=round(time.time() - t0, 1),
                        embed_reused_from_B=(s == "C"), cost_usd=0)

    traces = []
    for q in questions:
        qv = emb.embed_query(q["question"])
        for s in "ABC":
            flt = q.get("filter") if s == "C" else None  # filter only in C, only when the question carries one
            hits = store.search(s, qv, CFG["top_k"], flt)
            traces.append(dict(strategy=s, qid=q["id"], split=q["split"], question=q["question"], filter=flt,
                               gold=dict(source=q["gold_source_id"], page=q["gold_page"], quote=q["evidence_quote"]),
                               eval=evaluate_query(q, hits), top3=hits))
    OUT.mkdir(exist_ok=True)
    (OUT / "traces.jsonl").write_text("".join(json.dumps(t, ensure_ascii=False) + "\n" for t in traces))
    summary = dict(config=CFG, embedding_dim=emb.dimensions, chunk_stats=stats, metrics=summarize(traces),
                   run_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(summary["metrics"], indent=1)); print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()
