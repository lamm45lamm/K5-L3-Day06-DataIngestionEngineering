"""PostgreSQL + pgvector store. Exact cosine search (no ANN index; corpus is small)."""
from typing import Any

import psycopg

from .models import Chunk

FILTER_COLUMNS = {"document_id", "section", "function", "year"}  # whitelist: names are never user input


def _lit(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.7g}" for x in v) + "]"


class PgVectorStore:
    def __init__(self, database_url: str, dimensions: int) -> None:
        self.url, self.dim = database_url, dimensions

    def _conn(self):
        return psycopg.connect(self.url)

    def create_schema(self) -> None:
        with self._conn() as c:
            c.execute("CREATE EXTENSION IF NOT EXISTS vector")
            c.execute(f"""CREATE TABLE IF NOT EXISTS chunks (
                strategy text NOT NULL, chunk_id text NOT NULL, document_id text NOT NULL, source text NOT NULL,
                page int NOT NULL, printed_page int, section text, function text, year int, text text NOT NULL,
                embedding vector({self.dim}) NOT NULL, PRIMARY KEY (strategy, chunk_id))""")

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        if len(chunks) != len(vectors) or any(len(v) != self.dim for v in vectors):
            raise ValueError("chunk/vector count or dimension mismatch")
        ids = [c.chunk_id for c in chunks]
        with self._conn() as c:
            c.execute("DELETE FROM chunks WHERE strategy = %s AND chunk_id <> ALL(%s)", (strategy, ids))  # obsolete
            with c.cursor() as cur:
                cur.executemany(
                    """INSERT INTO chunks VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector)
                       ON CONFLICT (strategy, chunk_id) DO UPDATE SET document_id=EXCLUDED.document_id, source=EXCLUDED.source,
                       page=EXCLUDED.page, printed_page=EXCLUDED.printed_page, section=EXCLUDED.section,
                       function=EXCLUDED.function, year=EXCLUDED.year, text=EXCLUDED.text, embedding=EXCLUDED.embedding""",
                    [(strategy, k.chunk_id, k.document_id, k.source, k.page, k.metadata.get("printed_page"),
                      k.metadata.get("section"), k.metadata.get("function"), k.metadata.get("year"), k.text, _lit(v))
                     for k, v in zip(chunks, vectors)])

    def count(self, strategy: str) -> int:
        with self._conn() as c:
            return c.execute("SELECT count(*) FROM chunks WHERE strategy=%s", (strategy,)).fetchone()[0]

    def search(self, strategy: str, query_vector: list[float], top_k: int = 3,
               filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        filters = filters or {}
        if not set(filters) <= FILTER_COLUMNS:
            raise ValueError(f"unsupported filter fields: {set(filters) - FILTER_COLUMNS}")
        where = "".join(f" AND {k} = %s" for k in filters)
        q = _lit(query_vector)
        sql = f"""SELECT chunk_id, text, 1 - (embedding <=> %s::vector) AS score, document_id, source, page,
                  printed_page, section, function, year FROM chunks WHERE strategy = %s{where}
                  ORDER BY embedding <=> %s::vector LIMIT %s"""
        with self._conn() as c:
            rows = c.execute(sql, [q, strategy, *filters.values(), q, top_k]).fetchall()
        keys = ["chunk_id", "text", "score", "document_id", "source", "page", "printed_page", "section", "function", "year"]
        return [dict(zip(keys, r)) for r in rows]
