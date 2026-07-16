"""
Indexe data/processed/site_esprit_clean.json dans ChromaDB.

À relancer chaque fois que site_esprit_clean.json change (nouveau scraping,
nouveau document ajouté, etc.) : reconstruit la collection de zéro pour
éviter tout désaccord entre la base de connaissances et l'index vectoriel.

Lancement :
    python -m modules.rag.ingest
"""

from __future__ import annotations

import json

from modules.rag.config import KNOWLEDGE_BASE_PATH
from modules.rag.embeddings import embed
from modules.rag.vectorstore import add_records, reset_collection

BATCH_SIZE = 64


def record_to_text(record: dict) -> str:
    """Texte à embedder : titre + contenu, pour que le titre pèse dans la recherche."""
    titre = record.get("titre", "").strip()
    contenu = record.get("contenu", "").strip()
    return f"{titre} : {contenu}" if titre else contenu


def main() -> None:
    records = json.loads(KNOWLEDGE_BASE_PATH.read_text(encoding="utf-8"))
    print(f"{len(records)} fiches a indexer depuis {KNOWLEDGE_BASE_PATH}")

    collection = reset_collection()

    for start in range(0, len(records), BATCH_SIZE):
        batch = records[start : start + BATCH_SIZE]
        texts = [record_to_text(r) for r in batch]
        vectors = embed(texts)
        ids = [r["id"] for r in batch]
        metadatas = [
            {
                "categorie": r.get("categorie", ""),
                "titre": r.get("titre", ""),
                "source": r.get("source", ""),
            }
            for r in batch
        ]
        add_records(collection, ids=ids, documents=texts, embeddings=vectors, metadatas=metadatas)
        print(f"  -> {min(start + BATCH_SIZE, len(records))}/{len(records)} indexees")

    print(f"\nTermine : {collection.count()} fiches dans la collection.")


if __name__ == "__main__":
    main()
