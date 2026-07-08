"""RAG vector store with FAISS backend (Windows/Python 3.9 compatible)."""

from __future__ import annotations

import json
import pickle
import uuid
from pathlib import Path
from typing import Any, Optional

import numpy as np

from config.settings import get_settings


class VectorStore:
    COLLECTIONS = {
        "runbooks": "runbooks",
        "historical_incidents": "historical_incidents",
        "sops": "sops",
        "feedback": "feedback",
    }

    def __init__(self) -> None:
        settings = get_settings()
        self.persist_dir = Path(settings.vector_store_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self._stores: dict[str, dict[str, Any]] = {}
        self._load_all()

    def _collection_path(self, name: str) -> Path:
        return self.persist_dir / f"{name}.pkl"

    def _load_all(self) -> None:
        for coll in self.COLLECTIONS.values():
            path = self._collection_path(coll)
            if path.exists():
                with open(path, "rb") as f:
                    self._stores[coll] = pickle.load(f)
            else:
                self._stores[coll] = {"documents": [], "metadatas": [], "ids": [], "vectors": None}

    def _save(self, name: str) -> None:
        with open(self._collection_path(name), "wb") as f:
            pickle.dump(self._stores[name], f)

    def _embed(self, texts: list[str]) -> np.ndarray:
        try:
            from sentence_transformers import SentenceTransformer

            settings = get_settings()
            if not hasattr(self, "_model"):
                self._model = SentenceTransformer(settings.embedding_model)
            return self._model.encode(texts, normalize_embeddings=True)
        except Exception:
            # Fallback: simple bag-of-words hashing for demo without heavy models
            vectors = []
            for text in texts:
                vec = np.zeros(384)
                for i, word in enumerate(text.lower().split()):
                    vec[hash(word) % 384] += 1.0 / (i + 1)
                norm = np.linalg.norm(vec)
                vectors.append(vec / norm if norm > 0 else vec)
            return np.array(vectors)

    def add_documents(
        self,
        collection: str,
        documents: list[str],
        metadatas: Optional[list[dict]] = None,
        ids: Optional[list[str]] = None,
    ) -> None:
        store = self._stores[collection]
        if ids is None:
            ids = [str(uuid.uuid4()) for _ in documents]
        if metadatas is None:
            metadatas = [{} for _ in documents]

        new_vectors = self._embed(documents)
        if store["vectors"] is None:
            store["vectors"] = new_vectors
        else:
            store["vectors"] = np.vstack([store["vectors"], new_vectors])

        store["documents"].extend(documents)
        store["metadatas"].extend(metadatas)
        store["ids"].extend(ids)
        self._save(collection)

    def query(
        self,
        collection: str,
        query_text: str,
        n_results: int = 5,
        where: Optional[dict] = None,
    ) -> list[dict[str, Any]]:
        store = self._stores.get(collection, {})
        if not store.get("documents"):
            return []

        query_vec = self._embed([query_text])[0]
        vectors = store["vectors"]
        scores = vectors @ query_vec

        indices = np.argsort(scores)[::-1][:n_results]
        output = []
        for idx in indices:
            meta = store["metadatas"][idx]
            if where:
                if not all(meta.get(k) == v for k, v in where.items()):
                    continue
            output.append(
                {
                    "document": store["documents"][idx],
                    "metadata": meta,
                    "distance": float(1 - scores[idx]),
                    "id": store["ids"][idx],
                }
            )
        return output

    def search_all(self, query_text: str, n_results: int = 3) -> dict[str, list[dict]]:
        return {
            name: self.query(coll_name, query_text, n_results)
            for name, coll_name in self.COLLECTIONS.items()
        }
