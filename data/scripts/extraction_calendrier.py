"""
Extrait les événements des calendriers PDF (grilles jour par jour) d'ESPRIT
et les fusionne dans le fichier JSON existant de la base de connaissances.

Contrairement aux règlements (texte en paragraphes), un calendrier est un
tableau : jour, lettre du jour, événement, répété pour chaque mois. Ce script
utilise l'extraction de tableaux de pdfplumber (pas l'extraction de texte
brut) pour reconstruire une date exacte pour chaque événement trouvé.

Installation :
    pip install pdfplumber

Lancement :
    python extract_calendars.py
"""

import os
import re
import json
import datetime

import pdfplumber

# ----------------------------------------------------------------------------
# 1. Liste des calendriers à traiter : chemin -> catégorie à leur attribuer.
# ----------------------------------------------------------------------------
CALENDAR_FILES = {
    r"C:\Users\zizou\Desktop\stage_ia_recepsionist\data\raw_data\calendrier\Calendrier_1,2,3&4A_ 2526_S1.pdf": "Calendrier 1ère à 4ème année",
    r"C:\Users\zizou\Desktop\stage_ia_recepsionist\data\raw_data\calendrier\Calendrier_5A_ 2526_S1.pdf": "Calendrier 5ème année",
    r"C:\Users\zizou\Desktop\stage_ia_recepsionist\data\raw_data\calendrier\Calendrier_5DS9 & 5INFINI3.pdf": "Calendrier 5DS9 et 5Infini3",
}

OUTPUT_PATH = r"C:\Users\zizou\Desktop\stage_ia_recepsionist\data\processed\site_esprit.json"

MONTH_TO_NUM = {
    "Janvier": 1, "Février": 2, "Mars": 3, "Avril": 4, "Mai": 5, "Juin": 6,
    "Juillet": 7, "Août": 8, "Septembre": 9, "Octobre": 10, "Novembre": 11, "Décembre": 12,
}
WEEKDAY_FR = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]


def slugify(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower())
    return text.strip("_")[:60]


def find_academic_years(title_text: str) -> tuple[int, int]:
    """Extrait '2025-2026' du titre du tableau -> (2025, 2026)."""
    match = re.search(r"(\d{4})\s*-\s*(\d{4})", title_text or "")
    if match:
        return int(match.group(1)), int(match.group(2))
    # repli raisonnable si jamais le titre est absent ou différent
    today = datetime.date.today()
    return today.year, today.year + 1


def find_month_columns(header_row: list) -> list[tuple[int, str]]:
    """Repère à quelle colonne commence chaque bloc de mois (nom, lettre, événement)."""
    columns = []
    for i, cell in enumerate(header_row):
        if cell and cell.strip() in MONTH_TO_NUM:
            columns.append((i, cell.strip()))
    return columns


def extract_calendar_events(pdf_path: str) -> list[dict]:
    events = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                if len(table) < 3:
                    continue

                title_text = table[0][0] if table[0] else ""
                start_year, end_year = find_academic_years(title_text)
                month_columns = find_month_columns(table[1])
                if not month_columns:
                    continue

                for row in table[2:]:
                    for col_index, month_name in month_columns:
                        if col_index + 2 >= len(row):
                            continue
                        day_cell = row[col_index]
                        event_cell = row[col_index + 2]

                        if not day_cell or not str(day_cell).strip().isdigit():
                            continue
                        if not event_cell or not str(event_cell).strip():
                            continue

                        day = int(str(day_cell).strip())
                        month_num = MONTH_TO_NUM[month_name]
                        year = start_year if month_num >= 9 else end_year

                        try:
                            date = datetime.date(year, month_num, day)
                        except ValueError:
                            continue  # jour invalide pour ce mois (ex: 31 dans un mois à 30 jours)

                        event_text = re.sub(r"\s+", " ", str(event_cell)).strip()
                        weekday_fr = WEEKDAY_FR[date.weekday()]

                        events.append({
                            "date": date.isoformat(),
                            "jour_semaine": weekday_fr,
                            "evenement": event_text,
                        })
    return events


def build_records(events: list[dict], categorie: str, source: str) -> list[dict]:
    records = []
    for i, event in enumerate(events, start=1):
        contenu = (
            f"Le {event['jour_semaine'].lower()} {event['date']} : {event['evenement']}."
        )
        records.append({
            "id": f"{slugify(categorie)}_{event['date']}_{i:03d}",
            "categorie": categorie,
            "titre": f"{event['date']} - {event['evenement']}",
            "contenu": contenu,
            "source": source,
            "type": "pdf",
        })
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
            continue
        existing.append(record)
        existing_ids.add(record["id"])
        added += 1
    print(f"\n{added} nouvelles fiches ajoutées (doublons ignorés automatiquement).")
    return existing


if __name__ == "__main__":
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    all_new_records = []
    for pdf_path, categorie in CALENDAR_FILES.items():
        if not os.path.exists(pdf_path):
            print(f"[erreur] fichier introuvable : {pdf_path}")
            continue
        print(f"[{categorie}] {pdf_path}")
        events = extract_calendar_events(pdf_path)
        records = build_records(events, categorie, os.path.basename(pdf_path))
        print(f"  -> {len(records)} événements extraits")
        all_new_records.extend(records)

    existing_records = load_existing(OUTPUT_PATH)
    merged = merge_records(existing_records, all_new_records)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    print(f"Total dans la base de connaissances : {len(merged)} fiches -> {OUTPUT_PATH}")