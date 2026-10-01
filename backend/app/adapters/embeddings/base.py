from typing import List, Protocol, Sequence


class EmbeddingProvider(Protocol):
    """Turns text into fixed-length vectors. Vectors are L2-normalized (cosine = dot product)."""

    name: str  # stored with each vector, e.g. "fastembed:BAAI/bge-small-en-v1.5"
    dim: int

    def embed(self, texts: Sequence[str]) -> List[List[float]]: ...
