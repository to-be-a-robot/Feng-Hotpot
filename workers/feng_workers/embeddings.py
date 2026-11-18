"""Embedding providers. Switch with EMBEDDING_PROVIDER / EMBEDDING_MODEL in .env.

`fake` produces deterministic hashed bag-of-words vectors offline. It's only for
wiring and tests: similarity is purely lexical and must not be used for demo
scores.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

import httpx

from .config import env

BATCH_SIZE = 64


class Embedder(Protocol):
    name: str  # stored in <table>.embedding_model, e.g. "voyage:voyage-3.5"

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class FakeEmbedder:
    def __init__(self, dim: int = 256):
        self.dim = dim
        self.name = f"fake:hash-{dim}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * self.dim
            # Latin words plus single CJK characters, so Chinese captions get tokens too.
            for tok in re.findall(r"[a-z0-9]+|[一-鿿]", text.lower()):
                h = int.from_bytes(hashlib.sha256(tok.encode()).digest()[:8], "big")
                vec[h % self.dim] += 1.0 if (h >> 63) == 0 else -1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out


class VoyageEmbedder:
    def __init__(self, model: str):
        self.model = model
        self.name = f"voyage:{model}"
        self.key = env("VOYAGE_API_KEY", required=True)

    def embed(self, texts: list[str]) -> list[list[float]]:
        r = httpx.post(
            "https://api.voyageai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {self.key}"},
            json={"input": texts, "model": self.model, "input_type": "document"},
            timeout=60,
        )
        r.raise_for_status()
        return [d["embedding"] for d in sorted(r.json()["data"], key=lambda d: d["index"])]


class OpenAIEmbedder:
    def __init__(self, model: str):
        self.model = model
        self.name = f"openai:{model}"
        self.key = env("OPENAI_API_KEY", required=True)

    def embed(self, texts: list[str]) -> list[list[float]]:
        r = httpx.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {self.key}"},
            json={"input": texts, "model": self.model},
            timeout=60,
        )
        r.raise_for_status()
        return [d["embedding"] for d in sorted(r.json()["data"], key=lambda d: d["index"])]


def get_embedder() -> Embedder:
    provider = (env("EMBEDDING_PROVIDER", "fake") or "fake").lower()
    model = env("EMBEDDING_MODEL", "voyage-3.5")
    if provider == "fake":
        return FakeEmbedder()
    if provider == "voyage":
        return VoyageEmbedder(model)
    if provider == "openai":
        return OpenAIEmbedder(model)
    raise SystemExit(f"Unknown EMBEDDING_PROVIDER={provider!r} (use fake, voyage or openai)")
