"""Optional hybrid retrieval: dense (pgvector) + BM25 on the same B chunks and the same metadata filter as C.

score = alpha*dense_norm + (1-alpha)*bm25_norm (min-max per query). alpha=1 == baseline C.
alpha is chosen on dev only; test is reported once with the chosen alpha.
Run from starter/:  python -m src.hybrid
"""
import json
import math
import os
import re
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

from .embeddings import MyEmbedder
from .evaluation import evaluate_query, summarize
from .run import CFG, DEFAULT_URL, ROOT, OUT
from .store import PgVectorStore

ALPHAS = [i / 10 for i in range(11)]
_tok = lambda s: re.findall(r"\w+", s.lower())


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75) -> None:
        self.tf = [Counter(_tok(d)) for d in docs]
        self.len = [sum(t.values()) for t in self.tf]
        self.avg = sum(self.len) / len(docs)
        df = Counter(w for t in self.tf for w in t)
        n = len(docs)
        self.idf = {w: math.log(1 + (n - c + 0.5) / (c + 0.5)) for w, c in df.items()}
        self.k1, self.b = k1, b

    def score(self, query: str, i: int) -> float:
        tf, norm = self.tf[i], self.k1 * (1 - self.b + self.b * self.len[i] / self.avg)
        return sum(self.idf.get(w, 0) * tf[w] * (self.k1 + 1) / (tf[w] + norm) for w in set(_tok(query)) if w in tf)


def _norm(xs: list[float]) -> list[float]:
    lo, hi = min(xs), max(xs)
    return [(x - lo) / (hi - lo) if hi > lo else 0.0 for x in xs]


def fuse(cands: list[dict], bm: list[float], alpha: float, k: int = 3) -> list[dict]:
    d, b = _norm([c["score"] for c in cands]), _norm(bm)
    order = sorted(range(len(cands)), key=lambda i: -(alpha * d[i] + (1 - alpha) * b[i]))[:k]
    return [{**cands[i], "dense": cands[i]["score"], "bm25": bm[i], "score": alpha * d[i] + (1 - alpha) * b[i]} for i in order]


def main() -> None:
    load_dotenv(ROOT / "starter/.env")
    questions = [json.loads(l) for l in (ROOT / "benchmark/questions.jsonl").read_text().splitlines()]
    emb = MyEmbedder(CFG["model"])
    store = PgVectorStore(os.getenv("DATABASE_URL") or DEFAULT_URL, emb.dimensions)
    n_all = store.count("B")
    # IDF/avg-length are computed on the whole B corpus, so filtering does not change term statistics.
    corpus = store.search("B", emb.embed_query("x"), n_all)
    bm_all = BM25([c["text"] for c in corpus])
    idx = {c["chunk_id"]: i for i, c in enumerate(corpus)}

    # candidates per question: all chunks passing the filter (corpus is small) with dense score + BM25
    cache = {}
    for q in questions:
        flt = q.get("filter")
        cands = store.search("B", emb.embed_query(q["question"]), n_all, flt)
        cache[q["id"]] = (cands, [bm_all.score(q["question"], idx[c["chunk_id"]]) for c in cands])

    def run(alpha: float, split: str | None) -> list[dict]:
        out = []
        for q in questions:
            if split and q["split"] != split:
                continue
            cands, bm = cache[q["id"]]
            hits = fuse(cands, bm, alpha)
            out.append(dict(strategy="H", alpha=alpha, qid=q["id"], split=q["split"], question=q["question"],
                            filter=q.get("filter"), gold=dict(source=q["gold_source_id"], page=q["gold_page"], quote=q["evidence_quote"]),
                            eval=evaluate_query(q, hits), top3=hits))
        return out

    def tally(ts):
        return (sum(t["eval"]["hit_at_3"] for t in ts), sum(t["eval"]["hit_at_1"] for t in ts))

    sweep = {a: tally(run(a, "dev")) for a in ALPHAS}  # (hit@3, hit@1) on dev
    best = max(ALPHAS, key=lambda a: (*sweep[a], a))  # ties -> larger alpha (closer to dense baseline)
    traces = run(best, None)
    base = {t["qid"]: t for t in run(1.0, None)}
    diff = {"better": [], "worse": []}
    for t in traces:
        b = base[t["qid"]]["eval"]
        k = (t["eval"]["hit_at_3"], t["eval"]["hit_at_1"]), (b["hit_at_3"], b["hit_at_1"])
        if k[0] > k[1]: diff["better"].append(f'{t["qid"]}({t["split"]})')
        elif k[0] < k[1]: diff["worse"].append(f'{t["qid"]}({t["split"]})')
    summary = dict(alpha_sweep_dev={str(a): dict(hit_at_3=v[0], hit_at_1=v[1]) for a, v in sweep.items()}, chosen_alpha=best,
                   bm25=dict(k1=1.5, b=0.75, tokenizer="\\w+ lowercase, no stemming/stopwords"),
                   baseline_C=summarize(run(1.0, None))["H"], hybrid=summarize(traces)["H"], vs_baseline_C=diff)
    (OUT / "hybrid_traces.jsonl").write_text("".join(json.dumps(t, ensure_ascii=False) + "\n" for t in traces))
    (OUT / "hybrid_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
