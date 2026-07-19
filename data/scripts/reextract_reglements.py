"""
Re-extrait les 4 documents de règlement de scolarité par ARTICLE plutôt que
par page brute de PDF.

Ces documents contiennent une vraie structure ("Article 1 : ...", "Article 2
: ...") qui n'avait pas été exploitée lors du scraping initial (extraction
web générique, page par page) -- résultat : 103 fiches fragmentées sans
cohérence de sujet (une page pouvant couper un article en plein milieu, ou
mélanger la fin d'un article et le début du suivant).

Lancement (depuis la racine du projet) :
    python data/scripts/reextract_reglements.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pdfplumber

RAW_DIR = Path(__file__).resolve().parents[1] / "raw_data" / "vie_tudiante"
OUTPUT_PATH = Path(__file__).resolve().parents[1] / "processed" / "reglements_extracted.json"

# Fichier local -> (nom du parcours, source a utiliser dans la fiche).
FILES: dict[str, dict] = {
    "Reglement-de-la-scolarite_cours-du-jour-24-25.pdf": {
        "parcours": "Cours du jour",
        "source": "https://www.esprit.tn/wp-content/uploads/2025/02/Reglement-de-la-scolarite_cours-du-jour-24-25.pdf",
    },
    "Reglement-scolarite-24-25-cs.pdf": {
        "parcours": "Cours du soir",
        "source": "https://www.esprit.tn/wp-content/uploads/2025/02/Reglement-scolarite-24-25-cs.pdf",
    },
    "REGLEMENT-ALT2024-2025.pdf": {
        "parcours": "Formation en alternance",
        "source": "https://www.esprit.tn/wp-content/uploads/2025/02/REGLEMENT-ALT2024-2025.pdf",
    },
    "Private-School-of-Engineering-and-Technology.pdf": {
        "parcours": "Cours du jour (English)",
        "source": "https://www.esprit.tn/wp-content/uploads/2025/02/Private-School-of-Engineering-and-Technology.pdf",
    },
}

ARTICLE_PATTERN = re.compile(r"(Article\s*\d+\s*:.*?)(?=Article\s*\d+\s*:|\Z)", re.DOTALL)
TITLE_FROM_ARTICLE = re.compile(r"(Article\s*\d+\s*:\s*[^\n]*)")

# Ligne de sommaire type "Titre .......... 12" ou "Titre …………… 12" (pointilles
# ASCII ou ellipses unicode repetees, + numero de page).
TOC_LINE_PATTERN = re.compile(r"^.*[.…]{5,}\s*\d+\s*$", re.MULTILINE)

MAX_CHARS = 2000


def slugify(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower())
    return text.strip("_")[:60]


def extract_full_text(pdf_path: Path) -> str:
    with pdfplumber.open(str(pdf_path)) as pdf:
        return "\n".join((page.extract_text() or "") for page in pdf.pages)


def strip_toc_lines(full_text: str) -> str:
    """Retire les lignes de sommaire (titre suivi de pointilles et d'un
    numero de page), quel que soit le format du reste du document."""
    return TOC_LINE_PATTERN.sub("", full_text)


def strip_table_of_contents(full_text: str) -> str:
    """Le sommaire liste 'Article 1 :', 'Article 2 :'... avant le vrai
    contenu -- le vrai contenu commence a la DERNIERE occurrence de
    'Article 1 :' (le sommaire vient toujours avant le corps du texte)."""
    matches = list(re.finditer(r"Article\s*1\s*:", full_text))
    if len(matches) >= 2:
        return full_text[matches[-1].start():]
    return full_text


def split_long_section(titre: str, contenu: str) -> list[dict]:
    """Decoupe un article trop long (regroupe souvent des sous-clauses non
    numerotees, ex. le regime des examens ou la charte etudiante) en
    sous-parties, par phrase, comme clean_knowledgebase.py."""
    if len(contenu) <= MAX_CHARS:
        return [{"titre": titre, "contenu": contenu}]

    sentences = re.split(r"(?<=[.;:])\s+", contenu)
    chunks = []
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


def split_by_article(full_text: str) -> list[dict]:
    full_text = strip_table_of_contents(full_text)
    full_text = strip_toc_lines(full_text)
    matches = ARTICLE_PATTERN.findall(full_text)

    seen_titles = set()
    sections = []
    for match in matches:
        content = re.sub(r"\s+", " ", match).strip()
        title_match = TITLE_FROM_ARTICLE.search(match)
        title = title_match.group(1).strip() if title_match else content[:60]
        title = re.sub(r"\s+", " ", title)
        if title in seen_titles:
            continue  # doublon (ex. titre repete par erreur dans le PDF source)
        seen_titles.add(title)
        sections.extend(split_long_section(title, content))
    return sections


def main() -> None:
    all_records = []
    for filename, config in FILES.items():
        path = RAW_DIR / filename
        if not path.exists():
            print(f"[ignore] introuvable : {filename}")
            continue
        full_text = extract_full_text(path)
        sections = split_by_article(full_text)
        slug = slugify(config["parcours"])
        records = []
        for i, section in enumerate(sections, start=1):
            if len(section["contenu"]) < 20:
                continue
            records.append(
                {
                    "id": f"reglement_{slug}_art{i:03d}",
                    "categorie": "Règlement de la scolarité",
                    "titre": f"{config['parcours']} - {section['titre']}",
                    "contenu": section["contenu"],
                    "source": config["source"],
                }
            )
        print(f"[{filename}] -> {len(records)} articles extraits")
        all_records.extend(records)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_records, f, ensure_ascii=False, indent=2)

    print(f"\nTotal : {len(all_records)} fiches -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
