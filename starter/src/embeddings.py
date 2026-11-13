"""Local embeddings via fastembed (ONNX). No API key, no data leaves the machine."""
from fastembed import TextEmbedding

QUERY_PREFIX = "Represent this sentence for searching relevant passages: "  # bge-v1.5 query instruction


class MyEmbedder:
    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        self.model_name = model_name
        self._m = TextEmbedding(model_name)
        self.dimensions = len(next(iter(self._m.embed(["probe"]))))

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._m.embed(texts)]

    def embed_query(self, question: str) -> list[float]:
        return next(iter(self._m.embed([QUERY_PREFIX + question]))).tolist()
