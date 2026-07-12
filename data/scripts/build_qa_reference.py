"""
Construit une base de reference Q/R a partir de site_esprit.json.
Objectif: avoir au moins une question claire pour chaque information scrappee.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INPUT_PATH = PROJECT_ROOT / "data" / "processed" / "site_esprit_clean.json"
OUTPUT_JSON_PATH = PROJECT_ROOT / "data" / "processed" / "qa_reference_esprit.json"
OUTPUT_JSONL_PATH = PROJECT_ROOT / "data" / "processed" / "qa_reference_esprit.jsonl"

NOISE_PREFIXES = [
    "Ouvrir la visibilite du contenu :",
    "Ouvrir la visibilité du contenu :",
]

QUESTION_STARTERS = (
    "qui",
    "que",
    "quoi",
    "quand",
    "comment",
    "ou",
    "où",
    "pourquoi",
    "combien",
    "quel",
    "quelle",
    "quels",
    "quelles",
    "est-ce",
    "peut",
    "puis",
    "dois",
)


def clean_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def clean_title(title: str) -> str:
    title = clean_spaces(title)
    for prefix in NOISE_PREFIXES:
        if title.startswith(prefix):
            title = clean_spaces(title[len(prefix) :])
    return title


def ensure_question(text: str) -> str:
    text = clean_spaces(text)
    if not text:
        return "Quelle information importante concerne ce sujet a ESPRIT ?"
    if text.endswith("?"):
        return text
    return f"{text} ?"


def looks_like_question(title: str) -> bool:
    t = clean_spaces(title).lower()
    if not t:
        return False
    if "?" in t:
        return True
    return t.startswith(QUESTION_STARTERS)


def looks_like_amount(title: str) -> bool:
    t = clean_spaces(title).lower()
    return bool(re.search(r"\b\d+[\d\s.,]*\s*(dt|tnd|eur|euro|usd|€|\$)?\b", t))


def looks_like_pdf_page(title: str) -> bool:
    t = clean_spaces(title).lower()
    return ".pdf" in t and "page" in t


def first_sentence(content: str, max_chars: int = 120) -> str:
    text = clean_spaces(content)
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", text)
    sentence = parts[0] if parts else text
    if len(sentence) <= max_chars:
        return sentence
    return sentence[:max_chars].rstrip() + "..."


def build_question(record: dict) -> str:
    title = clean_title(str(record.get("titre", "")))
    category = clean_spaces(str(record.get("categorie", "Informations")))
    content = clean_spaces(str(record.get("contenu", "")))

    if looks_like_question(title):
        return ensure_question(title)

    if looks_like_pdf_page(title):
        m = re.match(r"(.+\.pdf)\s*-\s*page\s*(\d+)", title, flags=re.IGNORECASE)
        if m:
            pdf_name = m.group(1)
            page_num = m.group(2)
            return ensure_question(f"Que dit {pdf_name} a la page {page_num}")

    if looks_like_amount(title):
        return ensure_question(f"A quoi correspond le montant {title} dans les informations {category.lower()} d'ESPRIT")

    if title and len(title) >= 4 and title.lower() not in {"note", "faq"}:
        return ensure_question(f"Quelles informations ESPRIT donne sur {title}")

    summary = first_sentence(content)
    if summary:
        return ensure_question(f"Quelle information importante en {category.lower()} est donnee ici: {summary}")

    return ensure_question(f"Quelle information importante concerne {category.lower()} a ESPRIT")


def build_entry(record: dict, idx: int) -> dict:
    question = build_question(record)
    answer = clean_spaces(str(record.get("contenu", "")))
    return {
        "qa_id": f"qa_{idx:05d}",
        "question": question,
        "answer": answer,
        "record_id": record.get("id", ""),
        "category": record.get("categorie", ""),
        "title": clean_title(str(record.get("titre", ""))),
        "source": record.get("source", ""),
        "source_type": record.get("type", ""),
    }


def main() -> None:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Fichier introuvable: {INPUT_PATH}")

    records = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    qa_entries = [build_entry(rec, i) for i, rec in enumerate(records, start=1)]

    OUTPUT_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON_PATH.write_text(
        json.dumps(qa_entries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with OUTPUT_JSONL_PATH.open("w", encoding="utf-8") as f:
        for row in qa_entries:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"OK: {len(qa_entries)} Q/R générées")
    print(f"JSON : {OUTPUT_JSON_PATH}")
    print(f"JSONL: {OUTPUT_JSONL_PATH}")


if __name__ == "__main__":
    main()
