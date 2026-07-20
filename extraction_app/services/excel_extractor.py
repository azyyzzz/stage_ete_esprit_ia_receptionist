"""
Extraction Excel (.xlsx) -- pandas/openpyxl.

Chaque ligne de chaque feuille devient une fiche candidate : le contenu est
la concatenation "colonne: valeur" des cellules non vides de la ligne, le
titre est pris dans une colonne qui ressemble a un titre/sujet si elle
existe, sinon derive de la premiere cellule textuelle non vide, sinon
genere ("Feuille - ligne N").
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

TITLE_COLUMN_HINTS = ("titre", "title", "sujet", "question", "nom", "libelle", "intitule")


def _slugify(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", str(text).strip().lower())
    return text.strip("_")[:60]


def _find_title_column(columns: list[str]) -> str | None:
    for col in columns:
        normalized = str(col).strip().lower()
        if any(hint in normalized for hint in TITLE_COLUMN_HINTS):
            return col
    return None


def _row_to_content(row: pd.Series) -> str:
    parts = []
    for col, value in row.items():
        if pd.isna(value):
            continue
        text = str(value).strip()
        if text:
            parts.append(f"{col}: {text}")
    return " | ".join(parts)


def extract_excel(xlsx_path: Path, categorie: str, source: str, id_slug: str | None = None) -> list[dict]:
    """Retourne une liste de fiches {id, categorie, titre, contenu, source}.
    Voir pdf_extractor.extract_pdf pour le role de id_slug."""
    sheets = pd.read_excel(xlsx_path, sheet_name=None, engine="openpyxl")
    slug = _slugify(id_slug if id_slug is not None else xlsx_path.stem)

    records = []
    seq = 1
    for sheet_name, df in sheets.items():
        if df.empty:
            continue
        title_col = _find_title_column(list(df.columns))
        for _, row in df.iterrows():
            contenu = _row_to_content(row)
            if len(contenu) < 20:
                continue

            titre = None
            if title_col is not None and not pd.isna(row.get(title_col)):
                titre = str(row[title_col]).strip()
            if not titre:
                for value in row:
                    if not pd.isna(value) and isinstance(value, str) and value.strip():
                        titre = value.strip()
                        break
            if not titre:
                titre = f"{sheet_name} - ligne {seq}"

            records.append(
                {
                    "id": f"upload_excel_{slug}_{seq:03d}",
                    "categorie": categorie,
                    "titre": titre,
                    "contenu": contenu,
                    "source": source,
                }
            )
            seq += 1
    return records
