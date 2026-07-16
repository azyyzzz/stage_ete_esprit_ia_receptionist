"""
Extrait le texte de documents PDF locaux (règlements, chartes...) et fusionne
le résultat dans le fichier JSON existant de la base de connaissances.

Contrairement aux scripts précédents (qui téléchargent depuis le site), celui-ci
lit des PDF déjà présents sur ton disque -- ceux que tu as reçus ou téléchargés
toi-même et qui ne sont pas forcément publiés sur le site.

Installation :
    pip install pdfplumber

Lancement :
    python extract_local_documents.py
"""

import os
import re
import json

import pdfplumber

# ----------------------------------------------------------------------------
# 1. Liste des PDF locaux à traiter : chemin -> catégorie à leur attribuer.
#    Ajoute une ligne ici à chaque fois que tu reçois un nouveau document local.
# ----------------------------------------------------------------------------
PDF_FILES = {
    r"C:\Users\zizou\Desktop\stage_ia_recepsionist\data\raw_data\reglement\Charte des examens_étudiants 25.pdf": "Règlement des examens",
    r"C:\Users\zizou\Desktop\stage_ia_recepsionist\data\raw_data\reglement\Règlement de la scolarité_cours du jour 24-25.pdf": "Règlement de la scolarité",
}

# Fichier de base de connaissances existant, dans lequel on fusionne les nouvelles fiches.
# Adapté à ton chemin Windows -- modifie-le si besoin.
OUTPUT_PATH = r"C:\Users\zizou\Desktop\stage_ia_recepsionist\data\processed\site_esprit.json"

ARTICLE_PATTERN = re.compile(r"(Article\s*\d+\s*:.*?)(?=Article\s*\d+\s*:|\Z)", re.DOTALL)
TITLE_FROM_ARTICLE = re.compile(r"(Article\s*\d+\s*:\s*[^\n]*)")


def slugify(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower())
    return text.strip("_")[:60]


def extract_full_text(pdf_path: str) -> list[str]:
    """Retourne le texte de chaque page du PDF, dans une liste."""
    pages_text = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = (page.extract_text() or "").strip()
            pages_text.append(text)
    return pages_text


def strip_table_of_contents(full_text: str) -> str:
    """
    Beaucoup de règlements commencent par un sommaire qui liste "Article 1 :",
    "Article 2 :", etc. avant le vrai contenu -- ce qui fausse le découpage.
    Astuce : si "Article 1 :" apparaît plusieurs fois, le vrai contenu commence
    à la DERNIÈRE occurrence (le sommaire vient toujours avant le corps du texte).
    """
    matches = list(re.finditer(r"Article\s*1\s*:", full_text))
    if len(matches) >= 2:
        return full_text[matches[-1].start():]
    return full_text


def split_by_article(full_text: str) -> list[dict]:
    """
    Découpe le texte par 'Article N :' quand cette structure existe.
    Retourne une liste de {titre, contenu} ou une liste vide si le document
    ne contient pas ce type de structure.
    """
    full_text = strip_table_of_contents(full_text)
    matches = ARTICLE_PATTERN.findall(full_text)
    if len(matches) < 2:
        return []

    sections = []
    for match in matches:
        content = re.sub(r"\s+", " ", match).strip()
        title_match = TITLE_FROM_ARTICLE.search(match)
        title = title_match.group(1).strip() if title_match else content[:60]
        title = re.sub(r"\s+", " ", title)
        sections.append({"titre": title, "contenu": content})
    return sections


def process_pdf(pdf_path: str, categorie: str) -> list[dict]:
    if not os.path.exists(pdf_path):
        print(f"[erreur] fichier introuvable : {pdf_path}")
        return []

    print(f"[{categorie}] {pdf_path}")
    pages_text = extract_full_text(pdf_path)
    full_text = "\n".join(pages_text)
    filename = os.path.basename(pdf_path)
    slug = slugify(filename)

    records = []

    # Cas 1 : le document est structuré en articles -> un enregistrement par article
    sections = split_by_article(full_text)
    if sections:
        for i, section in enumerate(sections, start=1):
            if len(section["contenu"]) < 20:
                continue
            records.append({
                "id": f"{slugify(categorie)}_{slug}_art{i:03d}",
                "categorie": categorie,
                "titre": section["titre"],
                "contenu": section["contenu"],
                "source": filename,
            })
        print(f"  -> {len(records)} articles extraits")
        return records

    # Cas 2 : pas de structure "Article" détectée -> un enregistrement par page
    for page_num, page_text in enumerate(pages_text, start=1):
        text = re.sub(r"\s+", " ", page_text).strip()
        if len(text) < 20:
            continue
        records.append({
            "id": f"{slugify(categorie)}_{slug}_p{page_num:03d}",
            "categorie": categorie,
            "titre": f"{filename} - page {page_num}",
            "contenu": text,
            "source": filename,
        })
    print(f"  -> {len(records)} pages extraites (pas de structure par article détectée)")
    return records


def load_existing(output_path: str) -> list[dict]:
    if os.path.exists(output_path):
        with open(output_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def merge_records(existing: list[dict], new_records: list[dict]) -> list[dict]:
    existing_ids = {r["id"] for r in existing}
    added = 0
    for record in new_records:
        if record["id"] in existing_ids:
            # évite les doublons si le script est relancé plusieurs fois
            continue
        existing.append(record)
        existing_ids.add(record["id"])
        added += 1
    print(f"\n{added} nouvelles fiches ajoutées (doublons ignorés automatiquement).")
    return existing


if __name__ == "__main__":
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    all_new_records = []
    for pdf_path, categorie in PDF_FILES.items():
        all_new_records.extend(process_pdf(pdf_path, categorie))

    existing_records = load_existing(OUTPUT_PATH)
    merged = merge_records(existing_records, all_new_records)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    print(f"Total dans la base de connaissances : {len(merged)} fiches -> {OUTPUT_PATH}")
