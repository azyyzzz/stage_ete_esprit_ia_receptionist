"""
Extraction image (.jpg/.jpeg/.png) -- OCR via pytesseract, puis meme
decoupage que le PDF (article si detecte, sinon fiche unique decoupee si
trop longue).

Controle qualite obligatoire (contrainte explicite) : si le texte
reconnu est trop court ou contient trop de caracteres non reconnus, on ne
fusionne PAS silencieusement dans la base -- la fiche est mise de cote pour
verification manuelle (voir extraction_app/services/kb_merge.py, qui ecrit
ces items dans data/a_verifier.json).

Necessite le moteur Tesseract OCR installe comme binaire systeme (pas
seulement `pip install pytesseract`, qui n'est qu'un wrapper) -- voir
README.md.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytesseract
from PIL import Image

from extraction_app.config import MIN_OCR_CHARS
from extraction_app.services.pdf_extractor import _slugify, _split_by_article, _split_long_section

# Caracteres consideres "propres" : lettres (accentuees incluses), chiffres,
# espaces et ponctuation courante. Un OCR de mauvaise qualite produit
# beaucoup de symboles hors de cet ensemble.
_CLEAN_CHAR_PATTERN = re.compile(r"[a-zA-ZÀ-ÿ0-9\s.,;:!?()\-'\"%€]")
MIN_CLEAN_RATIO = 0.85


def _quality_ok(text: str) -> tuple[bool, str]:
    stripped = text.strip()
    if len(stripped) < MIN_OCR_CHARS:
        return False, f"texte reconnu trop court ({len(stripped)} caracteres, minimum {MIN_OCR_CHARS})"

    clean_chars = len(_CLEAN_CHAR_PATTERN.findall(stripped))
    ratio = clean_chars / len(stripped) if stripped else 0.0
    if ratio < MIN_CLEAN_RATIO:
        return False, f"trop de caracteres non reconnus ({ratio:.0%} de caracteres propres, minimum {MIN_CLEAN_RATIO:.0%})"

    return True, ""


def extract_image(image_path: Path, categorie: str, source: str, id_slug: str | None = None) -> tuple[list[dict], dict | None]:
    """Retourne (fiches, item_a_verifier). item_a_verifier est None si l'OCR
    est de qualite suffisante ; sinon les fiches sont vides et l'item
    decrit ce qui a ete rejete (pour data/a_verifier.json).
    Voir pdf_extractor.extract_pdf pour le role de id_slug."""
    raw_text = pytesseract.image_to_string(Image.open(image_path), lang="fra")
    text = re.sub(r"\s+", " ", raw_text).strip()

    ok, reason = _quality_ok(text)
    if not ok:
        item = {
            "source": source,
            "motif": reason,
            "extrait": text[:200],
        }
        return [], item

    title_base = id_slug if id_slug is not None else image_path.stem
    sections = _split_by_article(text)
    if not sections:
        sections = _split_long_section(title_base, text)

    slug = _slugify(title_base)
    records = []
    for i, section in enumerate(sections, start=1):
        if len(section["contenu"]) < 20:
            continue
        records.append(
            {
                "id": f"upload_image_{slug}_{i:03d}",
                "categorie": categorie,
                "titre": section["titre"],
                "contenu": section["contenu"],
                "source": source,
            }
        )
    return records, None
