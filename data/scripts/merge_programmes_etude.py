"""
Fusionne le brouillon valide (data/processed/programmes_etude_a_valider.json,
produit par extract_programmes_etude.py) dans la base de connaissances
(site_esprit_clean.json et site_esprit.json).

Reutilise EXACTEMENT la meme logique de construction de fiche que
extraction_app (extraction_app/services/programme_etude_extractor.py,
build_fiches_from_classes) -- memes id -- pour qu'un futur ré-upload d'un de
ces memes PDF via l'appli soit reconnu comme doublon plutot que duplique.

Dedup uniquement par id (ces fiches sont un contenu entierement nouveau,
jamais vu auparavant dans la base -- pas de verification semantique TF-IDF
ici, contrairement a extraction_app, car il ne s'agit pas d'une source
externe non maitrisee mais d'un brouillon deja relu par l'utilisateur).

Idempotent par UPSERT : toutes les fiches "upload_pdf_prog_*" deja presentes
sont retirees puis regenerees a neuf avant chaque fusion -- permet de
relancer ce script apres une amelioration de build_fiches_from_classes (ex.
ajout d'une desambiguation) sans laisser d'anciennes versions perimees.

Lancement (depuis la racine du projet) :
    python data/scripts/merge_programmes_etude.py
"""

from __future__ import annotations

import json
from pathlib import Path

from extraction_app.services.programme_etude_extractor import build_fiches_from_classes

DRAFT_PATH = Path(__file__).resolve().parents[1] / "processed" / "programmes_etude_a_valider.json"
CLEAN_PATH = Path(__file__).resolve().parents[1] / "processed" / "site_esprit_clean.json"
RAW_KB_PATH = Path(__file__).resolve().parents[1] / "processed" / "site_esprit.json"


def main() -> None:
    with open(DRAFT_PATH, encoding="utf-8") as f:
        draft = json.load(f)

    all_new_records: list[dict] = []
    seen_ids: set[str] = set()
    for file_result in draft:
        records = build_fiches_from_classes(file_result["classes"], file_result["fichier"])
        for r in records:
            if r["id"] in seen_ids:
                print(f"  [ignore] id deja rencontre dans ce brouillon : {r['id']}")
                continue
            seen_ids.add(r["id"])
            all_new_records.append(r)
        print(f"[{file_result['fichier']}] -> {len(records)} fiches")

    print(f"\nTotal fiches candidates : {len(all_new_records)}")

    for path in (CLEAN_PATH, RAW_KB_PATH):
        with open(path, encoding="utf-8") as f:
            kb = json.load(f)
        before = len(kb)
        kb = [r for r in kb if not r["id"].startswith("upload_pdf_prog_")]
        removed = before - len(kb)
        kb.extend(all_new_records)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(kb, f, ensure_ascii=False, indent=2)
        print(f"[{path.name}] {removed} anciennes fiches retirees, {len(all_new_records)} regenerees -> {len(kb)} fiches au total")


if __name__ == "__main__":
    main()
