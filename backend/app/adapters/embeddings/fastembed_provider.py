import threading
from typing import List, Optional, Sequence


class FastEmbedProvider:
    """Local ONNX sentence-embedding model (default BAAI/bge-small-en-v1.5, 384 dimensions).

    Runs on CPU, needs no API key, and sends no data to third parties. The model is
    downloaded once into cache_dir (the Docker image bakes it in at build time).
    """

    def __init__(self, model: str, dim: int, cache_dir: Optional[str] = None) -> None:
        self.model_name = model
        self.dim = dim
        self.cache_dir = cache_dir
        self.name = f"fastembed:{model}"
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._model is None:
                from fastembed import TextEmbedding

                self._model = TextEmbedding(self.model_name, cache_dir=self.cache_dir)
        return self._model

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        if not texts:
            return []
        vectors = [v.tolist() for v in self._load().embed(list(texts))]
        if vectors and len(vectors[0]) != self.dim:
            raise ValueError(f"{self.model_name} returns {len(vectors[0])} dimensions; EMBEDDING_DIM is {self.dim}")
        return vectors
