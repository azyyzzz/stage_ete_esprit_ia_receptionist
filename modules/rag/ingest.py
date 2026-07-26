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
from modules.rag.nlu import TITRE_CLASSE_PATTERN
from modules.rag.vectorstore import add_records, reset_collection
from pathlib import Path

# Optional additional source: fiches issues du pipeline d'extraction
EXTRA_PROGRAMMES_PATH = Path(__file__).resolve().parents[2] / "data" / "processed" / "programmes_etude_a_valider.json"

BATCH_SIZE = 64


def record_to_text(record: dict) -> str:
    """Texte à embedder : titre + contenu, pour que le titre pèse dans la recherche."""
    titre = record.get("titre", "").strip()
    contenu = record.get("contenu", "").strip()
    return f"{titre} : {contenu}" if titre else contenu


def record_to_classe(record: dict) -> str:
    """Nom de classe extrait du titre pour les fiches "Programme d'étude"
    (voir modules/rag/nlu.py), utilisé comme métadonnée filtrable pour la
    recherche par classe -- vide pour toute autre catégorie."""
    if record.get("categorie") != "Programme d'étude":
        return ""
    match = TITRE_CLASSE_PATTERN.match(record.get("titre", ""))
    return match.group(1) if match else ""


def main() -> None:
    records = json.loads(KNOWLEDGE_BASE_PATH.read_text(encoding="utf-8"))

    # If an extra programmes file exists (raw parsed program tables), convert
    # it to the same record format and append so it's indexed too.
    if EXTRA_PROGRAMMES_PATH.exists():
        try:
            extra = json.loads(EXTRA_PROGRAMMES_PATH.read_text(encoding="utf-8"))
            generated = []
            for file_entry in extra:
                fichier = file_entry.get("fichier", "")
                classes = file_entry.get("classes", [])
                # if no classes parsed, try to create a fallback record from filename
                if not classes:
                    # derive candidate name from filename similar to NLU logic
                    candidate = fichier.replace("Plan d'étude", "")
                    candidate = candidate.replace("Plan d'études", "")
                    candidate = candidate.replace("Plan d\u2019etude", "")
                    candidate = candidate.replace("Plan d\u2019etudes", "")
                    candidate = candidate.replace(".pdf", "")
                    import re
                    candidate = re.sub(r"\b\d{2}[- ]?\d{2}\b", "", candidate)
                    candidate = candidate.strip()
                    if candidate:
                        # summarize parse errors / unparsed tables
                        tables = file_entry.get("tables_non_parsees", [])
                        parts = []
                        for t in tables:
                            page = t.get("page")
                            err = t.get("erreur")
                            parts.append(f"page {page}: {err}" if page or err else "table non parsee")
                        contenu = "; ".join(parts) if parts else "Tables non parsees"
                        import uuid
                        rec_id = f"peval_{uuid.uuid4().hex}"
                        generated.append({
                            "id": rec_id,
                            "categorie": "Programme d'étude",
                            "titre": f"Programme d\'étude — {candidate} — non parse",
                            "contenu": contenu,
                            "source": fichier,
                        })
                for cls in classes:
                    classe_nom = cls.get("classe", "")
                    lignes = cls.get("lignes", [])
                    # group by panier
                    from collections import defaultdict

                    panier_map = defaultdict(list)
                    for l in lignes:
                        panier = l.get("panier", "Autres").strip()
                        mat = l.get("matiere", "").strip()
                        if mat:
                            panier_map[panier].append(l)

                    for panier, items in panier_map.items():
                        titre = f"Programme d\'étude — {classe_nom} — {panier}"
                        # build contenu text listing matieres
                        parts = []
                        for it in items:
                            mat = it.get("matiere", "").strip()
                            ects = it.get("ects_matiere") or ""
                            parts.append(f"{mat} ({ects} ECTS)" if ects else mat)
                        contenu = "; ".join(parts)
                        import uuid
                        rec_id = f"peval_{uuid.uuid4().hex}"
                        generated.append({
                            "id": rec_id,
                            "categorie": "Programme d'étude",
                            "titre": titre,
                            "contenu": contenu,
                            "source": fichier,
                        })
            print(f"Ajout de {len(generated)} fiches generées depuis {EXTRA_PROGRAMMES_PATH}")
            records.extend(generated)
        except Exception as e:
            print(f"Erreur lors de l'integration de {EXTRA_PROGRAMMES_PATH}: {e}")

    print(f"{len(records)} fiches a indexer depuis {KNOWLEDGE_BASE_PATH} (+ extras)")

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
                "classe": record_to_classe(r),
            }
            for r in batch
        ]
        add_records(collection, ids=ids, documents=texts, embeddings=vectors, metadatas=metadatas)
        print(f"  -> {min(start + BATCH_SIZE, len(records))}/{len(records)} indexees")

    print(f"\nTermine : {collection.count()} fiches dans la collection.")


if __name__ == "__main__":
    main()
