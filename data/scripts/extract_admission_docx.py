"""
Extrait les documents .docx du dossier data/raw_data/Admission/ et produit
des fiches groupees par SECTION (titre en gras du document), pas par simple
question/reponse individuelle.

Pourquoi grouper par section plutot que par question : les questions posees
par les appelants sont souvent vagues ("comment ca marche l'inscription ?"),
donc une fiche qui regroupe toutes les infos d'un meme sujet (ex. "Admission
et Inscription" : criteres + procedure + frais + reductions) donne une
reponse plus complete qu'une fiche par mini-question isolee. Une fiche par
question individuelle est trop courte pour bien remonter en recherche
semantique (voir la fiche de correction "Departement des stages" du meme
projet, ou le probleme etait exactement l'inverse : trop court).

Lancement (depuis la racine du projet) :
    python data/scripts/extract_admission_docx.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import docx

RAW_DIR = Path(__file__).resolve().parents[1] / "raw_data" / "Admission"
OUTPUT_PATH = Path(__file__).resolve().parents[1] / "processed" / "admission_docx_extracted.json"

# Fichier -> (programme associe pour la detection d'ambiguite RAG, ou None
# si le contenu est general/non specifique a un programme ; source a
# utiliser dans la fiche).
FILE_CONFIG: dict[str, dict] = {
    "FAQ admission cours du soir.docx": {
        "source": "https://www.esprit.tn/admissions/cours-du-soir/",
    },
    "FAQ admission parcours alternance.docx": {
        "source": "https://www.esprit.tn/admissions/formation-en-alternance/",
    },
    "FAQ Admission tunisiens cours du jour site web.docx": {
        "source": "https://www.esprit.tn/admissions/cours-du-jour/cours-du-jour-tunisiens/",
    },
    "FAQ internationaux Cours du jour.docx": {
        "source": "https://www.esprit.tn/admissions/cours-du-jour/cours-du-jour-internationaux/",
    },
    "FAQ global.docx": {
        "source": "https://www.esprit.tn/admissions/foire-aux-questions/",
    },
    "Nos conseillers admission.docx": {
        "source": "https://www.esprit.tn/admissions/nos-conseillers-admission/",
    },
    # "Admission alternance.docx" est volontairement absent : il ne contient
    # qu'une note de renvoi vers le site web ("Prendre le contenu du site :
    # ..."), aucune information a extraire.
}


def slugify(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower())
    return text.strip("_")[:60]


def is_bold_paragraph(paragraph) -> bool:
    if not paragraph.runs:
        return False
    return all(run.bold for run in paragraph.runs if run.text.strip())


def is_question(text: str) -> bool:
    return text.strip().endswith("?")


def strip_numbering(text: str) -> str:
    """Enleve un prefixe '1. ', '2. ' etc. devant une question numerotee."""
    return re.sub(r"^\d+[.)]\s*", "", text).strip()


PLACEHOLDER_PATTERN = re.compile(
    r"\((?:mettre|bouton|cliquable)[^)]*\)", re.IGNORECASE
)


def strip_author_placeholders(text: str) -> str:
    """Enleve les notes d'auteur destinees au webmaster (ex. '(mettre 3
    boutons cliquables ...)'), qui ne sont pas du contenu reel a indexer."""
    return re.sub(r"\s+", " ", PLACEHOLDER_PATTERN.sub("", text)).strip()


def group_into_sections(paragraphs: list) -> list[dict]:
    """
    Parcourt les paragraphes et regroupe le contenu par section (dernier
    titre en gras vu). A l'interieur d'une section, detecte les paires
    question/reponse (question = paragraphe finissant par '?', reponse =
    paragraphe(s) suivant(s) jusqu'a la prochaine question ou le prochain
    titre), et accumule le reste comme texte descriptif.
    """
    sections: list[dict] = []
    current_title = None
    current_lines: list[str] = []

    def flush():
        if current_title is not None and current_lines:
            sections.append({"titre": current_title, "lignes": list(current_lines)})

    for paragraph in paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue

        if is_bold_paragraph(paragraph):
            flush()
            current_title = text
            current_lines = []
            continue

        if current_title is None:
            # Texte avant le premier titre en gras (ex. titre du document) : ignore.
            continue

        # Cas "FAQ global.docx" : question et reponse dans le meme paragraphe,
        # separees par un saut de ligne interne.
        if "\n" in text:
            first_line, rest = text.split("\n", 1)
            first_line = strip_numbering(first_line)
            if is_question(first_line):
                rest = strip_author_placeholders(rest.strip())
                current_lines.append(f"Q: {first_line}\nR: {rest}")
                continue

        text = strip_numbering(text)
        text = strip_author_placeholders(text)
        if not text:
            continue

        if is_question(text):
            current_lines.append(f"Q: {text}")
        elif current_lines and current_lines[-1].startswith("Q:") and "\nR:" not in current_lines[-1]:
            # Paragraphe juste apres une question sans reponse encore attachee.
            current_lines[-1] += f"\nR: {text}"
        elif current_lines and current_lines[-1].split("\n")[-1].startswith("R:"):
            # Reponse qui continue sur plusieurs paragraphes/puces.
            current_lines[-1] += f" {text}"
        elif current_lines and current_lines[-1].startswith("- "):
            # Texte descriptif qui continue sur plusieurs paragraphes/puces.
            current_lines[-1] += f" {text}"
        else:
            # Texte descriptif hors question/reponse (ex. Nos conseillers admission.docx).
            current_lines.append(f"- {text}")

    flush()
    return sections


def process_docx(path: Path, source: str) -> list[dict]:
    document = docx.Document(str(path))
    sections = group_into_sections(document.paragraphs)

    records = []
    doc_slug = slugify(path.stem)
    for i, section in enumerate(sections, start=1):
        content = "\n\n".join(section["lignes"]).strip()
        if len(content) < 30:
            continue
        records.append(
            {
                "id": f"admission_docx_{doc_slug}_{i:02d}",
                "categorie": "Admissions",
                "titre": f"{path.stem} — {section['titre']}",
                "contenu": content,
                "source": source,
            }
        )
    return records


def main() -> None:
    all_records = []
    for filename, config in FILE_CONFIG.items():
        path = RAW_DIR / filename
        if not path.exists():
            print(f"[ignore] introuvable : {filename}")
            continue
        records = process_docx(path, config["source"])
        print(f"[{filename}] -> {len(records)} fiches (regroupees par section)")
        all_records.extend(records)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_records, f, ensure_ascii=False, indent=2)

    print(f"\nTotal : {len(all_records)} fiches -> {OUTPUT_PATH}")
    print("Fichier de revue -- a inspecter avant fusion dans site_esprit_clean.json")


if __name__ == "__main__":
    main()
