"""
Recherche des fiches de la base de connaissances pertinentes pour une
question donnée.
"""

from __future__ import annotations

from dataclasses import dataclass

from modules.rag.config import TOP_K
from modules.rag.embeddings import embed
from modules.rag.vectorstore import query


@dataclass
class RetrievedChunk:
    content: str
    metadata: dict
    score: float  # similarité : 1.0 = identique, 0.0 = sans rapport


def _distance_to_similarity(distance: float) -> float:
    """Avec la distance cosinus (0 = identique, 2 = opposé), la similarité
    cosinus est simplement 1 - distance."""
    return max(0.0, 1.0 - distance)


def retrieve(question: str, top_k: int = TOP_K) -> list[RetrievedChunk]:
    question_vector = embed([question])[0]
    result = query(question_vector, top_k=top_k)

    documents = result["documents"][0]
    metadatas = result["metadatas"][0]
    distances = result["distances"][0]

    chunks = [
        RetrievedChunk(content=doc, metadata=meta, score=_distance_to_similarity(dist))
        for doc, meta, dist in zip(documents, metadatas, distances)
    ]
    return sorted(chunks, key=lambda c: c.score, reverse=True)
