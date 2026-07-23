"""
Extraction des programmes d'etude (paniers/UE, matieres, heures, periode,
ECTS) -- reutilise directement la logique de
data/scripts/extract_programmes_etude.py (deja validee sur les 30 PDF de
data/raw_data/programme d'etude/, voir le registre de validation).

Ce module fait la jonction entre cette logique (qui produit une structure
classe -> panier -> matieres) et le schema strict des fiches de la base de
connaissances (id/categorie/titre/contenu/source) : une fiche par (classe,
panier), listant ses matieres avec heures/periode/ECTS en une phrase
lisible plutot qu'un tableau brut.

Utilise par extraction_app/services/pdf_extractor.py : essaye D'ABORD cette
extraction quand un PDF est uploade ; si aucune classe/panier n'est
detecte, le PDF n'est probablement pas un programme d'etude et le pipeline
retombe sur l'extraction generique (article / page).
"""

from __future__ import annotations

import re
from pathlib import Path

from data.scripts.extract_programmes_etude import process_pdf


def _slugify(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower())
    return text.strip("_")[:60]


def _format_valeur(label: str, valeur, unite: str = "") -> str:
    if valeur in (None, ""):
        return ""
    prefix = f"{label} " if label else ""
    return f"{prefix}{valeur}{unite}"


def _format_matiere(m: dict) -> str:
    parts = [
        _format_valeur("", m.get("heures_matiere"), "h"),
        _format_valeur("période", m.get("periode")),
        _format_valeur("", m.get("ects_matiere"), " ECTS"),
    ]
    details = ", ".join(p for p in parts if p)
    if details:
        return f"{m['matiere']} ({details})"
    return m["matiere"]


def _sum_ects(matieres: list[dict]) -> float | None:
    total = 0.0
    found = False
    for m in matieres:
        val = m.get("ects_matiere")
        if val in (None, ""):
            continue
        try:
            total += float(str(val).replace(",", "."))
            found = True
        except ValueError:
            continue
    return total if found else None


def build_fiches_from_classes(classes: list[dict], source: str) -> list[dict]:
    """Convertit une structure classe -> lignes (panier/matiere/heures/
    periode/ects, telle que produite par process_pdf) en fiches
    {id, categorie, titre, contenu, source} : une fiche par (classe,
    panier). Partagee entre l'extraction PDF live d'extraction_app et la
    fusion en masse du brouillon deja valide (voir
    data/scripts/merge_programmes_etude.py) -- memes id, pour qu'un futur
    ré-upload du meme PDF via l'appli soit reconnu comme doublon plutot que
    duplique."""
    records = []
    for classe in classes:
        classe_nom = classe["classe"]
        paniers: dict[str, list[dict]] = {}
        order = []
        for row in classe["lignes"]:
            p = row["panier"]
            if p not in paniers:
                paniers[p] = []
                order.append(p)
            paniers[p].append(row)

        for panier in order:
            matieres = paniers[panier]
            phrases = [_format_matiere(m) for m in matieres]
            total_ects = _sum_ects(matieres)

            contenu = (
                f"Dans le programme d'étude de la classe {classe_nom}, "
                f"l'unité d'enseignement (panier) « {panier} » comprend "
                f"les matières suivantes : " + " ; ".join(phrases) + "."
            )
            if total_ects is not None:
                contenu += f" Total ECTS de ce panier : {total_ects:g}."

            records.append(
                {
                    "id": f"upload_pdf_prog_{_slugify(classe_nom)}_{_slugify(panier)}",
                    "categorie": "Programme d'étude",
                    "titre": f"Programme d'étude — {classe_nom} — {panier}",
                    "contenu": contenu,
                    "source": source,
                }
            )

    return records


def extract_programme_etude(pdf_path: Path, source: str) -> list[dict] | None:
    """Retourne une liste de fiches, ou None si ce PDF ne ressemble pas a un
    programme d'etude (aucun panier/matiere detecte -- le pipeline appelant
    doit alors essayer l'extraction generique a la place)."""
    result = process_pdf(pdf_path)
    if not result["classes"]:
        return None
    return build_fiches_from_classes(result["classes"], source)
