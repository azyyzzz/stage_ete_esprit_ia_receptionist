"""
Wrapper autour de ChromaDB : création de la collection, ajout de fiches et
recherche par similarité. Le reste du module RAG ne parle jamais directement
à ChromaDB, seulement à ce fichier.
"""

from __future__ import annotations

from functools import lru_cache

import chromadb

from modules.rag.config import COLLECTION_NAME, VECTOR_STORE_DIR


@lru_cache(maxsize=1)
def get_client() -> chromadb.ClientAPI:
    VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(VECTOR_STORE_DIR))


def reset_collection() -> chromadb.Collection:
    """Supprime puis recrée la collection (utilisé par ingest.py pour repartir propre)."""
    client = get_client()
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass  # la collection n'existait pas encore
    # Distance cosinus explicite : plus adaptee a des embeddings de texte
    # que la distance L2 par defaut de ChromaDB.
    return client.create_collection(COLLECTION_NAME, metadata={"hnsw:space": "cosine"})


def get_collection() -> chromadb.Collection:
    return get_client().get_or_create_collection(
        COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
    )


def add_records(
    collection: chromadb.Collection,
    ids: list[str],
    documents: list[str],
    embeddings: list[list[float]],
    metadatas: list[dict],
) -> None:
    collection.add(ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas)


def query(embedding: list[float], top_k: int) -> dict:
    collection = get_collection()
    return collection.query(query_embeddings=[embedding], n_results=top_k)
