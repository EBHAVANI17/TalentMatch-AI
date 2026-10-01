import hashlib
import math
import re
from typing import List, Sequence

_TOKEN = re.compile(r"[a-z0-9+#.]+")


class HashingEmbedder:
    """Deterministic bag-of-words vectors (feature hashing). No model, no network.

    Captures shared words only, not meaning. Used in tests and as a fallback where
    a real model can't be installed.
    """

    def __init__(self, dim: int) -> None:
        self.dim = dim
        self.name = f"hashing:{dim}"

    def _vector(self, text: str) -> List[float]:
        vec = [0.0] * self.dim
        tokens = _TOKEN.findall(text.lower())
        grams = tokens + [f"{a} {b}" for a, b in zip(tokens, tokens[1:])]
        for gram in grams:
            digest = hashlib.blake2b(gram.encode(), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "little") % self.dim
            sign = 1.0 if digest[4] & 1 else -1.0
            vec[index] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        return [self._vector(t) for t in texts]
