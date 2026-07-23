"""
Recherche des fiches de la base de connaissances pertinentes pour une
question donnée.
"""

from __future__ import annotations

from dataclasses import dataclass

from modules.rag.config import TOP_K
from modules.rag.embeddings import embed
from modules.rag.vectorstore import get_all, query


@dataclass
class RetrievedChunk:
    content: str
    metadata: dict
    score: float  # similarité : 1.0 = identique, 0.0 = sans rapport


def _distance_to_similarity(distance: float) -> float:
    """Avec la distance cosinus (0 = identique, 2 = opposé), la similarité
    cosinus est simplement 1 - distance."""
    return max(0.0, 1.0 - distance)


def retrieve(question: str, top_k: int = TOP_K, where: dict | None = None) -> list[RetrievedChunk]:
    """where : filtre de metadonnee optionnel (ex. {"classe": "4 ERP-BI"}),
    voir modules/rag/nlu.py -- restreint la recherche par similarite a un
    sous-ensemble de fiches plutot que toute la base, pour eviter la
    confusion entre deux entites voisines (ex. classes "4 ERP-BI" et
    "5 ERP-BI") qui ne se distinguent que par un signal faible en
    embedding."""
    question_vector = embed([question])[0]
    result = query(question_vector, top_k=top_k, where=where)

    documents = result["documents"][0]
    metadatas = result["metadatas"][0]
    distances = result["distances"][0]

    chunks = [
        RetrievedChunk(content=doc, metadata=meta, score=_distance_to_similarity(dist))
        for doc, meta, dist in zip(documents, metadatas, distances)
    ]
    return sorted(chunks, key=lambda c: c.score, reverse=True)


def retrieve_all(question: str, where: dict) -> list[RetrievedChunk]:
    """Recupere TOUTES les fiches correspondant au filtre (pas de limite
    TOP_K) -- utilise quand la question demande une liste exhaustive (voir
    modules/rag/nlu.py::is_list_all_intent) : une simple recherche par
    similarite plafonnee a TOP_K omettrait mecaniquement une partie des
    fiches d'une classe ayant 10+ paniers. Le score est tout de meme
    calcule (similarite cosinus contre la question) pour un tri et un
    affichage des sources coherents avec retrieve()."""
    question_vector = embed([question])[0]
    result = get_all(where=where)

    documents = result["documents"]
    metadatas = result["metadatas"]
    embeddings = result["embeddings"]

    chunks = [
        RetrievedChunk(content=doc, metadata=meta, score=max(0.0, sum(a * b for a, b in zip(question_vector, emb))))
        for doc, meta, emb in zip(documents, metadatas, embeddings)
    ]
    return sorted(chunks, key=lambda c: c.score, reverse=True)
