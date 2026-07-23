"""
Extraction PDF -- adapte de data/scripts/reextract_reglements.py.

Strategie a TROIS niveaux :
1. Programme d'etude (paniers/UE, matieres, heures, periode, ECTS) -- voir
   services/programme_etude_extractor.py, qui reutilise la logique deja
   validee de data/scripts/extract_programmes_etude.py. Essaye en premier
   car sa detection est specifique (necessite un vrai tableau UE/ECTS) ;
   si rien n'est detecte, le PDF n'est probablement pas de ce type et on
   continue avec les niveaux suivants.
2. Si le PDF a une vraie structure "Article N : ..." (>= 2 occurrences),
   une fiche par article, avec retrait du sommaire et decoupage des
   articles trop longs.
3. Sinon (documents uploades arbitraires, sans structure reconnue), repli
   sur une fiche par page -- meme logique de secours que
   data/scripts/extract_local_documents_reglements.py.
"""

from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from extraction_app.config import MAX_CHARS
from extraction_app.services.programme_etude_extractor import extract_programme_etude

ARTICLE_PATTERN = re.compile(r"(Article\s*\d+\s*:.*?)(?=Article\s*\d+\s*:|\Z)", re.DOTALL)
TITLE_FROM_ARTICLE = re.compile(r"(Article\s*\d+\s*:\s*[^\n]*)")
TOC_LINE_PATTERN = re.compile(r"^.*[.…]{5,}\s*\d+\s*$", re.MULTILINE)


def _slugify(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower())
    return text.strip("_")[:60]


def _extract_full_text(pdf_path: Path) -> str:
    with pdfplumber.open(str(pdf_path)) as pdf:
        return "\n".join((page.extract_text() or "") for page in pdf.pages)


def _strip_table_of_contents(full_text: str) -> str:
    matches = list(re.finditer(r"Article\s*1\s*:", full_text))
    if len(matches) >= 2:
        return full_text[matches[-1].start():]
    return full_text


def _strip_toc_lines(full_text: str) -> str:
    return TOC_LINE_PATTERN.sub("", full_text)


def _split_long_section(titre: str, contenu: str) -> list[dict]:
    if len(contenu) <= MAX_CHARS:
        return [{"titre": titre, "contenu": contenu}]

    sentences = re.split(r"(?<=[.;:])\s+", contenu)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if current and len(current) + len(sentence) > MAX_CHARS:
            chunks.append(current.strip())
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current.strip())

    return [
        {"titre": f"{titre} (partie {i}/{len(chunks)})", "contenu": chunk}
        for i, chunk in enumerate(chunks, start=1)
    ]


def _split_by_article(full_text: str) -> list[dict]:
    full_text = _strip_table_of_contents(full_text)
    full_text = _strip_toc_lines(full_text)
    matches = ARTICLE_PATTERN.findall(full_text)

    seen_titles: set[str] = set()
    sections: list[dict] = []
    for match in matches:
        content = re.sub(r"\s+", " ", match).strip()
        title_match = TITLE_FROM_ARTICLE.search(match)
        title = title_match.group(1).strip() if title_match else content[:60]
        title = re.sub(r"\s+", " ", title)
        if title in seen_titles:
            continue
        seen_titles.add(title)
        sections.extend(_split_long_section(title, content))
    return sections


def _split_by_page(pdf_path: Path) -> list[dict]:
    sections = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = (page.extract_text() or "").strip()
            text = re.sub(r"\s+", " ", text)
            if text:
                sections.append({"titre": f"{pdf_path.name} - page {page_num}", "contenu": text})
    return sections


def extract_pdf(pdf_path: Path, categorie: str, source: str, id_slug: str | None = None) -> list[dict]:
    """Retourne une liste de fiches {id, categorie, titre, contenu, source}.

    id_slug sert a construire des id stables et deterministes pour permettre
    la dedup par id (kb_merge.py) sur un re-upload du meme fichier -- a
    fournir a partir du nom de fichier ORIGINAL (pas du chemin temporaire,
    qui est aleatoire). A defaut, derive du nom du fichier temporaire."""
    programme_records = extract_programme_etude(pdf_path, source)
    if programme_records is not None:
        return programme_records

    full_text = _extract_full_text(pdf_path)
    sections = _split_by_article(full_text)
    if not sections:
        sections = _split_by_page(pdf_path)

    slug = _slugify(id_slug if id_slug is not None else pdf_path.stem)
    records = []
    for i, section in enumerate(sections, start=1):
        if len(section["contenu"]) < 20:
            continue
        records.append(
            {
                "id": f"upload_pdf_{slug}_{i:03d}",
                "categorie": categorie,
                "titre": section["titre"],
                "contenu": section["contenu"],
                "source": source,
            }
        )
    return records
