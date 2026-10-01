from functools import lru_cache

from app.adapters.embeddings.base import EmbeddingProvider
from app.core.config import BACKEND_DIR, settings

__all__ = ["EmbeddingProvider", "get_embedder"]


@lru_cache
def get_embedder() -> EmbeddingProvider:
    provider = settings.embedding_provider.lower()
    if provider == "hashing":
        from app.adapters.embeddings.hashing import HashingEmbedder
        return HashingEmbedder(settings.embedding_dim)
    if provider == "fastembed":
        from app.adapters.embeddings.fastembed_provider import FastEmbedProvider
        cache = settings.embedding_cache_dir or str(BACKEND_DIR / ".cache" / "fastembed")
        return FastEmbedProvider(settings.embedding_model, settings.embedding_dim, cache)
    raise ValueError(f"Unknown EMBEDDING_PROVIDER {settings.embedding_provider!r} (supported: fastembed, hashing)")
