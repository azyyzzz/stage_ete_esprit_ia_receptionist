"""
Scraping des "Options" de spécialisation - ESPRIT Tunis
=========================================================
Complète les 4 fiches "Spécialité X — ESPRIT Tunis" déjà dans la base de
connaissances (description générale de chaque grande spécialité) avec le
détail des OPTIONS de spécialisation au sein de chacune (ex. la spécialité
Informatique propose Fintech, IoT & Embedded Technologies, Cloud &
Cybersecurity Engineering, Data Analytics & Science, Software Systems
Architecture), chacune avec sa description, ses objectifs, ses modules
spécifiques (4ème/5ème année) et ses débouchés.

Catégorie dédiée "Options" (pas "Programmes") pour ces fiches : elles ne
doivent PAS apparaître dans la liste des grandes spécialités par campus
(voir modules/rag/ingest.py::record_to_campus, modules/rag/pipeline.py) --
une option est un sous-ensemble d'une spécialité, pas une spécialité en soi.

Fusionne le résultat directement dans data/processed/site_esprit_clean.json
et site_esprit.json (UPSERT idempotent par préfixe d'id, même logique que
data/scripts/merge_programmes_etude.py) : relancer ce script remplace
proprement les anciennes fiches d'options par les nouvelles, sans jamais
toucher aux autres fiches de la base.

Installation :
    pip install requests beautifulsoup4

Lancement (depuis la racine du projet) :
    python data/scripts/scrape_esprit_tunis_options.py
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; EspritOptionsBot/1.0)"}

SPECIALTY_URLS = [
    "https://www.esprit.tn/nos-programmes/programmes-dingenieur/esprit-tunis/ingenieur-en-genie-informatique/",
    "https://www.esprit.tn/nos-programmes/programmes-dingenieur/esprit-tunis/ingenieur-en-genie-des-telecommunications/",
    "https://www.esprit.tn/nos-programmes/programmes-dingenieur/esprit-tunis/ingenieur-en-genie-civil/",
    "https://www.esprit.tn/nos-programmes/programmes-dingenieur/esprit-tunis/ingenieur-en-genie-electromecanique/",
]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_OUTPUT_PATH = PROJECT_ROOT / "data" / "raw_data" / "esprit_tunis_options.json"
CLEAN_KB_PATH = PROJECT_ROOT / "data" / "processed" / "site_esprit_clean.json"
RAW_KB_PATH = PROJECT_ROOT / "data" / "processed" / "site_esprit.json"

ID_PREFIX = "esprit_tunis_options_"


def _slugify(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower()).strip("_")


def extract_options(html: str) -> tuple[str, list[dict]]:
    soup = BeautifulSoup(html, "html.parser")
    specialty = soup.find("h1").get_text(strip=True) if soup.find("h1") else ""
    full_text = soup.get_text("\n")

    # La page contient PLUSIEURS occurrences de "Options" -- la première est
    # le menu de navigation en haut de page ("Présentation Admission
    # Programme Options Mobilité internationale..."), pas la vraie section
    # (confirmé en inspectant la page réelle : ce nav factice fait que le
    # PREMIER match n'est jamais le bon). La vraie section de contenu est
    # toujours la DERNIÈRE occurrence de "Options" sur la page (le nav
    # s'affiche une seule fois, en haut, avant tout contenu).
    starts = list(re.finditer(r"\nOptions\n", full_text))
    ends = list(re.finditer(r"\nMobilit[ée] internationale\n", full_text))
    section = ""
    if starts:
        s = starts[-1].end()
        candidate_ends = [e.start() for e in ends if e.start() > s]
        section_end = candidate_ends[0] if candidate_ends else len(full_text)
        section = full_text[s:section_end]

    # Chaque option est encadrée par ces marqueurs d'accordéon
    blocks = re.findall(
        r"Ouvrir la visibilité du contenu\s*:\s*(.+?)\n(.*?)Fermer la visibilité du contenu",
        section, re.DOTALL,
    )

    def grab(block, label, stop):
        m = re.search(label + r"\s*\n(.*?)(?=" + stop + r"|$)", block, re.DOTALL)
        return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""

    options = []
    for name, block in blocks:
        options.append({
            "option": name.strip(),
            "description": grab(block, "Description", "Objectifs"),
            "objectifs": grab(block, "Objectifs", r"MODULES SP[ÉE]CIFIQUES"),
            "modules_4eme_annee": grab(block, r"4[ée]me ann[ée]e", r"5[ée]me ann[ée]e"),
            "modules_5eme_annee": grab(block, r"5[ée]me ann[ée]e", r"Les d[ée]bouch[ée]s"),
            "debouches": grab(block, r"Les d[ée]bouch[ée]s", "Formule de calcul du score"),
        })
    return specialty, options


def scrape_all() -> list[dict]:
    all_data = []
    for url in SPECIALTY_URLS:
        print(f"Scraping: {url}")
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        specialty, options = extract_options(resp.text)
        if not options:
            print(f"  [attention] aucune option trouvée pour {specialty!r} -- vérifier la page")
        for opt in options:
            all_data.append({"specialite": specialty, "url": url, **opt})
        print(f"  -> {len(options)} options extraites ({specialty})")
        time.sleep(1)
    return all_data


def to_kb_record(entry: dict) -> dict:
    specialite = entry["specialite"]
    option = entry["option"]
    parts = []
    if entry["description"]:
        parts.append(f"Description : {entry['description']}")
    if entry["objectifs"]:
        parts.append(f"Objectifs : {entry['objectifs']}")
    if entry["modules_4eme_annee"]:
        parts.append(f"Modules 4ème année : {entry['modules_4eme_annee']}")
    if entry["modules_5eme_annee"]:
        parts.append(f"Modules 5ème année : {entry['modules_5eme_annee']}")
    if entry["debouches"]:
        parts.append(f"Débouchés : {entry['debouches']}")

    return {
        "id": f"{ID_PREFIX}{_slugify(specialite)}_{_slugify(option)}",
        "categorie": "Options",
        "titre": f"Option {option} — {specialite} — ESPRIT Tunis",
        "contenu": " ".join(parts),
        "source": entry["url"],
    }


def merge_into_kb(records: list[dict]) -> None:
    for path in (CLEAN_KB_PATH, RAW_KB_PATH):
        with open(path, encoding="utf-8") as f:
            kb = json.load(f)
        before = len(kb)
        kb = [r for r in kb if not r["id"].startswith(ID_PREFIX)]
        removed = before - len(kb)
        kb.extend(records)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(kb, f, ensure_ascii=False, indent=2)
        print(f"[{path.name}] {removed} anciennes fiches d'options retirées, {len(records)} régénérées -> {len(kb)} fiches au total")


def main() -> None:
    raw_data = scrape_all()

    RAW_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RAW_OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(raw_data, f, ensure_ascii=False, indent=2)
    print(f"\n{len(raw_data)} options extraites -> {RAW_OUTPUT_PATH}")

    records = [to_kb_record(e) for e in raw_data]
    merge_into_kb(records)


if __name__ == "__main__":
    main()
