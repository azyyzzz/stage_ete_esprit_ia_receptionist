"""
Re-extrait les 4 calendriers PDF (data/raw_data/calendrier/) et remplace
TOUTES les fiches "Calendrier*" existantes dans la base de connaissances par
une version regroupee par TYPE d'evenement (au lieu d'une fiche par jour).

Pourquoi ce changement : l'ancienne extraction (voir extraction_calendrier.py)
produisait une fiche minuscule par evenement individuel ("Le mercredi
2025-12-03 : Conseils Session Principale."), sans contexte -- ce qui a cause
un probleme de recherche concret (la question "conseils de classe" ne
remontait aucune de ces fiches, faute du mot "classe" dans leur texte, voir
rapport). Ici, les evenements sont regroupes par type (rentree, APP0, examens
session principale, examens session de rattrapage, conseils de classe,
proclamation des resultats, fin des cours/vacances) pour chaque groupe
d'annee, avec toutes les dates listees dans une seule fiche coherente et des
synonymes explicites (ex. "conseil de classe") pour ameliorer la recherche.

Le calendrier "Calendrier du deuxieme semestre_2526.pdf" ne precise pas de
groupe d'annee dans son titre (contrairement aux 3 autres), et aucun signal
fiable (couleur, texte) ne permettait de deviner a quel groupe chaque
evenement s'applique. Confirme par l'utilisateur : ce calendrier est commun
a TOUTES les annees (1ere a 5eme) -- ses evenements sont donc fusionnes dans
les fiches de chaque groupe existant plutot que d'etre extraits a part.

Lancement (depuis la racine du projet) :
    python data/scripts/reextract_calendrier_groupe.py
"""

from __future__ import annotations

import datetime
import json
import re
import unicodedata
from pathlib import Path

import pdfplumber

RAW_DIR = Path(__file__).resolve().parents[1] / "raw_data" / "calendrier"
CLEAN_PATH = Path(__file__).resolve().parents[1] / "processed" / "site_esprit_clean.json"
RAW_KB_PATH = Path(__file__).resolve().parents[1] / "processed" / "site_esprit.json"

MONTH_TO_NUM = {
    "Janvier": 1, "Février": 2, "Mars": 3, "Avril": 4, "Mai": 5, "Juin": 6,
    "Juillet": 7, "Août": 8, "Septembre": 9, "Octobre": 10, "Novembre": 11, "Décembre": 12,
}
WEEKDAY_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]

# Calendriers du semestre 1, un fichier par groupe d'annee -> categorie a
# attribuer.
S1_FILES: dict[str, str] = {
    "Calendrier_1,2,3&4A_ 2526_S1.pdf": "Calendrier 1ère à 4ème année",
    "Calendrier_5A_ 2526_S1.pdf": "Calendrier 5ème année",
    "Calendrier_5DS9 & 5INFINI3.pdf": "Calendrier 5DS9 et 5Infini3",
}

# Calendrier du semestre 2 : un seul fichier, commun a tous les groupes
# ci-dessus (confirme par l'utilisateur) -- ses evenements sont fusionnes
# dans les fiches de chacun des 3 groupes.
S2_FILE = "Calendrier du deuxième semestre_2526.pdf"

# Ordre + regles de regroupement par type d'evenement. Chaque regle est une
# liste de mots-cles (normalises, sans accents/casse) ; le premier type dont
# un mot-cle est trouve dans l'evenement l'emporte (ordre = priorite).
EVENT_TYPES: list[tuple[str, str, list[str]]] = [
    ("rentree", "Rentrée et débuts de semestre", ["reprise des enseignants", "debut semestre"]),
    ("app0", "APP0 (Apprentissage Par Problèmes/Projets, module 0)", ["app0"]),
    ("conseils", "Conseils de classe", ["conseil"]),
    ("proclamation", "Proclamation des résultats", ["proclamation"]),
    ("rattrapage", "Examens de la session de rattrapage", ["rattrapage", "rattraoage", "WORD:sr"]),
    ("principale", "Examens de la session principale", ["session principale", "examens s1", "examens/ds", "examens de la session", "WORD:sp"]),
    ("soutenances", "Soutenances et examens pratiques", ["soutenance"]),
    ("fin_cours", "Fin des cours", ["fin des cours"]),
    ("vacances", "Vacances", ["vacances"]),
    ("autres", "Autres événements (fêtes, forum, activités)", []),  # filet de secours
]


def _normalize(text: str) -> str:
    text = text.lower()
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


def _slugify(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower())
    return text.strip("_")[:60]


def _classify(evenement: str) -> tuple[str, str]:
    """Un mot-cle prefixe "WORD:" est cherche en mot entier (evite les faux
    positifs des abreviations courtes comme "sp"/"sr", qui matcheraient
    n'importe quel mot les contenant en simple sous-chaine) ; les autres
    mots-cles (phrases plus longues, non ambigues) utilisent une recherche
    de sous-chaine simple."""
    normalized = _normalize(evenement)
    for key, label, keywords in EVENT_TYPES:
        if key == "autres":
            continue
        for kw in keywords:
            if kw.startswith("WORD:"):
                word = _normalize(kw[len("WORD:"):])
                if re.search(rf"\b{re.escape(word)}\b", normalized):
                    return key, label
            elif _normalize(kw) in normalized:
                return key, label
    return "autres", "Autres événements (fêtes, forum, activités)"


def _find_academic_years(title_text: str) -> tuple[int, int]:
    match = re.search(r"(\d{4})\s*-\s*(\d{4})", title_text or "")
    if match:
        return int(match.group(1)), int(match.group(2))
    today = datetime.date.today()
    return today.year, today.year + 1


def _find_month_columns(header_row: list) -> list[tuple[int, str]]:
    columns = []
    for i, cell in enumerate(header_row):
        if cell and cell.strip() in MONTH_TO_NUM:
            columns.append((i, cell.strip()))
    return columns


# Semaine "S1".."S16" : simple numero de semaine affiche dans la grille,
# jamais un vrai evenement -- ignore.
WEEK_MARKER_PATTERN = re.compile(r"^s\d{1,2}$")

# Fragments de texte qui, dans ces PDF, ne sont QUE la suite d'un evenement
# trop long pour tenir sur une seule case (le texte "deborde" visuellement
# sur la case du jour suivant, que pdfplumber attribue alors par erreur au
# jour suivant plutot qu'au jour de depart de l'evenement). Verifie
# manuellement sur les 4 PDF -- pas une regle generale.
CONTINUATION_FRAGMENTS = {
    "rattrapage", "principale", "pratique", "l'ecole", "de rattrapage", "de la",
    "printemps",
}


def _is_continuation_fragment(text: str) -> bool:
    return _normalize(text) in CONTINUATION_FRAGMENTS


def _merge_wrapped_continuations(column_events: list[dict]) -> list[dict]:
    """Fusionne un evenement avec le suivant si celui-ci n'est qu'un
    fragment de texte deborde du jour precedent (voir CONTINUATION_FRAGMENTS),
    et seulement si les deux jours sont consecutifs."""
    column_events = sorted(column_events, key=lambda e: e["date"])
    merged: list[dict] = []
    for event in column_events:
        if (
            merged
            and _is_continuation_fragment(event["evenement"])
            and event["date"] == merged[-1]["date"] + datetime.timedelta(days=1)
        ):
            merged[-1]["evenement"] = f"{merged[-1]['evenement']} {event['evenement']}"
            continue
        merged.append(dict(event))
    return merged


def extract_events(pdf_path: Path) -> list[dict]:
    """Reprend la logique table-based de extraction_calendrier.py (fiable,
    deja testee) : reconstruit une date exacte pour chaque evenement.
    Ajoute : fusion des evenements dont le texte deborde sur le jour suivant
    (voir _merge_wrapped_continuations), et filtre les simples numeros de
    semaine ("S1", "S2"...) qui ne sont pas de vrais evenements."""
    events_by_column: dict[int, list[dict]] = {}
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                if len(table) < 3:
                    continue
                title_text = table[0][0] if table[0] else ""
                start_year, end_year = _find_academic_years(title_text)
                month_columns = _find_month_columns(table[1])
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
                            continue

                        event_text = re.sub(r"\s+", " ", str(event_cell)).strip()
                        if WEEK_MARKER_PATTERN.match(_normalize(event_text)):
                            continue  # "S1".."S16" : numero de semaine, pas un evenement

                        events_by_column.setdefault(col_index, []).append(
                            {
                                "date": date,
                                "jour_semaine": WEEKDAY_FR[date.weekday()],
                                "evenement": event_text,
                            }
                        )

    events: list[dict] = []
    for column_events in events_by_column.values():
        events.extend(_merge_wrapped_continuations(column_events))
    return events


# Coquilles reperees dans les PDF sources (transcrites fidelement par
# l'extraction), corrigees ici car elles nuisent a la recherche sans
# changer le sens.
KNOWN_TYPOS = {"rattraoage": "rattrapage"}


def _fix_known_typos(text: str) -> str:
    for wrong, right in KNOWN_TYPOS.items():
        text = re.sub(re.escape(wrong), right, text, flags=re.IGNORECASE)
    return text


def build_grouped_records(events: list[dict], categorie: str) -> list[dict]:
    """Regroupe les evenements par type (voir EVENT_TYPES) et construit une
    fiche par groupe non vide, listant toutes les dates par ordre
    chronologique. Chaque evenement porte son propre champ "source"
    (fichier PDF d'origine) -- une fiche qui combine semestre 1 et semestre
    2 cite alors les deux fichiers."""
    events = [{**e, "evenement": _fix_known_typos(e["evenement"])} for e in events]
    buckets: dict[str, list[dict]] = {}
    for event in events:
        key, _ = _classify(event["evenement"])
        buckets.setdefault(key, []).append(event)

    slug = _slugify(categorie)
    records = []
    for key, label, _keywords in EVENT_TYPES:
        group_events = sorted(buckets.get(key, []), key=lambda e: e["date"])
        if not group_events:
            continue

        lines = [
            f"Le {e['jour_semaine']} {e['date'].isoformat()} : {e['evenement']}."
            for e in group_events
        ]
        contenu = f"Pour {categorie} -- " + " ".join(lines)

        titre = f"[{categorie}] {label}"
        if key == "conseils":
            # Synonyme explicite ajoute suite au probleme de recherche
            # constate ("conseils de classe" ne remontait aucune fiche).
            titre += " (conseil de classe)"
            contenu += " (Il s'agit du conseil de classe.)"
        if key == "rattrapage":
            # Synonyme explicite ajoute suite a un probleme constate : la
            # recherche remontait bien cette fiche pour "session de
            # controle", mais le LLM ne faisait pas le lien avec
            # "rattrapage" et ignorait l'info dans sa reponse.
            titre += " (session de contrôle)"
            contenu += " (Aussi appelée session de contrôle.)"

        sources = sorted({e["source"] for e in group_events})
        records.append(
            {
                "id": f"calendrier_v2_{slug}_{key}",
                "categorie": categorie,
                "titre": titre,
                "contenu": contenu,
                "source": " / ".join(sources),
            }
        )
    return records


def main() -> None:
    s2_path = RAW_DIR / S2_FILE
    s2_events = []
    if s2_path.exists():
        s2_events = [{**e, "source": S2_FILE} for e in extract_events(s2_path)]
        print(f"[{S2_FILE}] -> {len(s2_events)} evenements bruts (communs a tous les groupes)")
    else:
        print(f"[ignore] introuvable : {S2_FILE}")

    all_new_records = []
    for filename, categorie in S1_FILES.items():
        path = RAW_DIR / filename
        if not path.exists():
            print(f"[ignore] introuvable : {filename}")
            continue
        s1_events = [{**e, "source": filename} for e in extract_events(path)]
        combined = s1_events + s2_events
        records = build_grouped_records(combined, categorie)
        print(f"[{categorie}] -> {len(s1_events)} evenements S1 + {len(s2_events)} evenements S2 -> {len(records)} fiches regroupees")
        all_new_records.extend(records)

    for path in (CLEAN_PATH, RAW_KB_PATH):
        with open(path, encoding="utf-8") as f:
            kb = json.load(f)
        before = len(kb)
        kb = [r for r in kb if not r["categorie"].startswith("Calendrier")]
        removed = before - len(kb)
        kb.extend(all_new_records)  # ajoutees a la FIN du fichier
        with open(path, "w", encoding="utf-8") as f:
            json.dump(kb, f, ensure_ascii=False, indent=2)
        print(f"[{path.name}] {removed} anciennes fiches calendrier supprimees, {len(all_new_records)} nouvelles ajoutees -> {len(kb)} fiches au total")


if __name__ == "__main__":
    main()
