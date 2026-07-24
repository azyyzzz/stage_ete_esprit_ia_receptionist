"""
Extrait les programmes d'etude (paniers/UE, matieres, heures, periode, ECTS)
des PDF de data/raw_data/programme d'etude/ (un fichier par classe/
specialite, certains en anglais).

IMPORTANT : ce script est un PREMIER JET destine a etre VALIDE par
l'utilisateur avant toute fusion dans site_esprit_clean.json. Il ecrit dans
un fichier BROUILLON separe (voir OUTPUT_PATH), jamais dans la base de
connaissances principale.

Pourquoi c'est delicat : les 28 PDF ne partagent PAS tous la meme mise en
page de tableau -- certains ont une colonne "ECTS"/"Charge" par module et
une colonne "total" separee (parfois sur la meme ligne, parfois sur une
ligne differente a cause de cellules fusionnees), d'autres (1A, 2A, 3A...)
utilisent "ECTS"/"Workload"/"P1"/"P2" directement par module, un fichier
(ParcoursIA) est entierement en anglais ("UE"/"ECUE"/"Total hours"/
"Credits (ECTS)"/"P1 (Hours)"/"P2 (Hours)"). Plutot que de suivre un ordre
de colonnes fixe (qui casserait sur au moins la moitie des fichiers), ce
script classe chaque colonne par ANALYSE DE SON CONTENU (texte vs nombre,
ordre de grandeur, motif de code de periode) -- une heuristique, pas une
garantie absolue de justesse pour chaque fichier. Les fichiers/tableaux ou
la classification echoue sont signales dans le champ "a_verifier" plutot
que de deviner silencieusement.

Lancement (depuis la racine du projet) :
    python data/scripts/extract_programmes_etude.py
"""

from __future__ import annotations

import json
import re
import statistics
import unicodedata
from pathlib import Path

import pdfplumber

RAW_DIR = Path(__file__).resolve().parents[1] / "raw_data" / "programme d'etude"
OUTPUT_PATH = Path(__file__).resolve().parents[1] / "processed" / "programmes_etude_a_valider.json"

SUMMARY_ROW_MARKERS = {"total", "charge par semaine", "charge/semaine"}


def _normalize(text: str) -> str:
    if text is None:
        return ""
    text = str(text).lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text).strip()


def _to_number(text: str) -> float | None:
    if text is None:
        return None
    text = str(text).strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _looks_like_periode_strong(text: str) -> bool:
    """Marqueur de periode SANS AMBIGUITE possible (ex. "1 et 2", "1-S1") --
    ne peut pas etre confondu avec une valeur d'ECTS ou d'heures."""
    norm = _normalize(text)
    if not norm:
        return False
    return bool(re.search(r"\bet\b", norm) or re.search(r"\d\s*-\s*s?\d", norm))


def _looks_like_periode_weak(text: str) -> bool:
    """Un chiffre unique ("1", "2") ressemble a une periode MAIS peut tout
    aussi bien etre une petite valeur d'ECTS -- ambigu seul, utilise
    seulement en complement d'au moins un marqueur fort dans la colonne
    (voir _classify_columns)."""
    norm = _normalize(text)
    return bool(re.fullmatch(r"\d", norm))


def _find_header_row_indices(table: list[list]) -> list[int]:
    """Un tableau peut contenir PLUSIEURS en-tetes (un par semestre -- ex.
    "UE Semestre-2 ... ECTS" reapparait au milieu du tableau). Chaque
    occurrence marque le debut d'une nouvelle section a classer
    independamment (sinon les valeurs des deux semestres se melangent et
    la ligne d'en-tete du 2nd semestre est lue comme une fausse matiere).

    Certains programmes (ex. Genie Civil) n'ont pas de colonne ECTS du tout
    -- reconnus via "UE" + "Charge"/"HE" a defaut (les ECTS resteront vides
    pour ces classes, signale dans le brouillon plutot que masque)."""
    indices = []
    for i, row in enumerate(table):
        normalized_cells = [_normalize(c) for c in row]
        has_ects = any("ects" in c or "credit" in c for c in normalized_cells)
        has_ue = any(c == "ue" for c in normalized_cells)
        has_charge = any("charge" in c or c == "he" or "workload" in c for c in normalized_cells)
        if has_ects or (has_ue and has_charge):
            indices.append(i)
    return indices


HEADER_CONTINUATION_WORDS = {"he", "charge", "ects", "periode", "credits", "hours"}


def _is_header_continuation_row(row: list) -> bool:
    """Deuxieme ligne d'un en-tete fusionne sur 2 lignes (ex. "Charge" sur
    une ligne, "HE" juste en-dessous) : presque toutes les cellules vides,
    les rares non-vides sont des mots d'en-tete connus."""
    non_empty = [c for c in row if c not in (None, "")]
    if not non_empty or len(non_empty) > 2:
        return False
    return all(_normalize(c) in HEADER_CONTINUATION_WORDS for c in non_empty)


SEMESTRE_PATTERN = re.compile(r"semestre\s*-?\s*\d|\bs\d\b", re.IGNORECASE)


def _find_semestre_label(row: list) -> str | None:
    for cell in row:
        if not cell:
            continue
        cell_str = re.sub(r"\s+", " ", str(cell)).strip()
        match = SEMESTRE_PATTERN.search(_normalize(cell_str))
        if match:
            # Ne garde que le segment court correspondant (ex. "S2",
            # "Semestre-2"), pas toute la cellule (qui peut contenir un
            # en-tete de colonnes fusionne a la suite, ex. "S2 Unite
            # d'enseignement ECTS Charge P1 P2").
            return cell_str[: match.end()].strip()
    return None


def _classify_columns(data_rows: list[list], n_cols: int) -> dict:
    """Classe chaque colonne (texte / heures / periode / ects) en analysant
    les valeurs des lignes de donnees (pas seulement le texte d'en-tete,
    peu fiable ici -- voir docstring du module)."""
    data_rows = [
        row for row in data_rows
        if row and _normalize(row[1] if len(row) > 1 else row[0]) not in SUMMARY_ROW_MARKERS
    ]

    col_stats = []
    for col in range(n_cols):
        values = [row[col] for row in data_rows if col < len(row) and row[col] not in (None, "")]
        numeric_values = [v for v in (_to_number(x) for x in values) if v is not None]
        n_strong = sum(1 for x in values if _looks_like_periode_strong(x))
        n_periode_like = sum(1 for x in values if _looks_like_periode_strong(x) or _looks_like_periode_weak(x))
        col_stats.append(
            {
                "col": col,
                "n_values": len(values),
                "n_numeric": len(numeric_values),
                "n_periode_strong": n_strong,
                "n_periode_like": n_periode_like,
                "mean_numeric": statistics.mean(numeric_values) if numeric_values else None,
                "fill_ratio": len(values) / len(data_rows) if data_rows else 0,
            }
        )

    roles: dict[int, str] = {}
    for stat in col_stats:
        col = stat["col"]
        if stat["n_values"] == 0:
            continue
        # Un chiffre isole ("1") est ambigu avec une petite valeur d'ECTS --
        # la colonne n'est classee "periode" que si elle contient AU MOINS
        # une valeur sans ambiguite possible (ex. "1 et 2", "1-S1").
        if stat["n_periode_strong"] >= 1 and stat["n_periode_like"] >= stat["n_values"] * 0.6:
            roles[col] = "periode"
        elif stat["n_numeric"] >= stat["n_values"] * 0.8:
            if stat["mean_numeric"] is not None and stat["mean_numeric"] <= 12:
                roles[col] = "ects"
            else:
                roles[col] = "heures"
        else:
            roles[col] = "texte"

    # Parmi les colonnes "texte", celle qui varie a (quasi) chaque ligne =
    # matiere ; celle qui n'apparait que par intermittence (fusion sur
    # plusieurs lignes) = panier (UE). S'il n'y en a qu'une, elle sert aux
    # deux (cas UE a un seul module).
    texte_cols = [c for c, r in roles.items() if r == "texte"]
    texte_cols.sort(key=lambda c: next(s["fill_ratio"] for s in col_stats if s["col"] == c), reverse=True)
    matiere_col = texte_cols[0] if texte_cols else None

    # Certaines matieres trop longues pour la colonne matiere sont renvoyees
    # par pdfplumber dans une colonne voisine (avec une chaine VIDE -- pas
    # None -- dans matiere_col sur cette meme ligne) : une 3e colonne texte
    # apparait alors, purement pour ce repli, a ne pas confondre avec le
    # panier (sinon celui-ci est ignore -- son role de panier passe alors
    # inapercu -- ET les lignes concernees sont perdues, leur "matiere"
    # semblant vide).
    matiere_overflow_col = None
    panier_col = None
    for col in texte_cols[1:]:
        rows_with_col = [row for row in data_rows if col < len(row) and row[col] not in (None, "")]
        if not rows_with_col:
            continue
        is_overflow = matiere_col is not None and all(
            matiere_col < len(row) and row[matiere_col] == "" for row in rows_with_col
        )
        if is_overflow and matiere_overflow_col is None:
            matiere_overflow_col = col
        elif panier_col is None:
            panier_col = col

    # Parmi les colonnes "heures"/"ects", celle qui est remplie a (quasi)
    # chaque ligne = valeur PAR MATIERE ; celle qui n'apparait que par
    # intermittence = TOTAL du panier.
    def _split_module_vs_total(role: str) -> tuple[int | None, int | None]:
        cols = [c for c, r in roles.items() if r == role]
        if not cols:
            return None, None
        cols.sort(key=lambda c: next(s["fill_ratio"] for s in col_stats if s["col"] == c), reverse=True)
        module_col = cols[0]
        total_col = cols[1] if len(cols) > 1 else None
        return module_col, total_col

    heures_module_col, heures_total_col = _split_module_vs_total("heures")
    ects_module_col, ects_total_col = _split_module_vs_total("ects")
    periode_cols = [c for c, r in roles.items() if r == "periode"]
    periode_col = periode_cols[0] if periode_cols else None

    return {
        "panier_col": panier_col,
        "matiere_col": matiere_col,
        "matiere_overflow_col": matiere_overflow_col,
        "heures_module_col": heures_module_col,
        "heures_total_col": heures_total_col,
        "ects_module_col": ects_module_col,
        "ects_total_col": ects_total_col,
        "periode_col": periode_col,
        "n_data_rows": len(data_rows),
    }


CID_ARTIFACT_PATTERN = re.compile(r"\(cid:\d+\)")


def _cell(row: list, col: int | None):
    if col is None or col >= len(row):
        return None
    val = row[col]
    if isinstance(val, str):
        return CID_ARTIFACT_PATTERN.sub("", val).strip()
    return val


def _extract_section_rows(section_rows: list[list], cols: dict, semestre_label: str | None = None) -> list[dict]:
    rows = []
    current_panier = None
    for row in section_rows:
        if not row or _is_header_continuation_row(row):
            continue
        matiere = _cell(row, cols["matiere_col"])
        if not matiere and cols.get("matiere_overflow_col") is not None:
            matiere = _cell(row, cols["matiere_overflow_col"])
        if _normalize(matiere) in SUMMARY_ROW_MARKERS or not matiere:
            continue
        panier_cell = _cell(row, cols["panier_col"])
        if panier_cell:
            current_panier = panier_cell
        if current_panier is None:
            current_panier = matiere
        rows.append(
            {
                "semestre": semestre_label,
                "panier": re.sub(r"\s+", " ", str(current_panier)).strip(),
                "matiere": re.sub(r"\s+", " ", str(matiere)).strip(),
                "heures_matiere": _cell(row, cols["heures_module_col"]),
                "heures_panier_total": _cell(row, cols["heures_total_col"]),
                "periode": _cell(row, cols["periode_col"]),
                "ects_matiere": _cell(row, cols["ects_module_col"]),
                "ects_panier_total": _cell(row, cols["ects_total_col"]),
            }
        )
    return rows


def extract_table_rows(table: list[list], fallback_cols: dict | None = None) -> tuple[list[dict], dict]:
    """Retourne (lignes structurees, diagnostic). Le tableau est d'abord
    decoupe en sections independantes (une par semestre, voir
    _find_header_row_indices), chacune classee et extraite separement pour
    ne jamais melanger les colonnes de deux semestres ni lire un en-tete
    comme une matiere.

    fallback_cols : classification de colonnes d'un tableau precedent sur la
    MEME PAGE, reutilisee telle quelle si ce tableau-ci n'a pas son propre
    en-tete -- cas frequent ou pdfplumber decoupe une seule table logique
    (UE + matieres) en plusieurs tableaux au milieu, sans repeter l'en-tete."""
    header_indices = _find_header_row_indices(table)
    if not header_indices:
        if fallback_cols is not None and fallback_cols.get("matiere_col") is not None:
            rows = _extract_section_rows(table, fallback_cols)
            if rows:
                return rows, {
                    "erreur": None,
                    "sections": [{"semestre": None, "repris_du_tableau_precedent": True, **fallback_cols}],
                    "last_cols": fallback_cols,
                }
        return [], {"erreur": "en-tete non detecte (aucune colonne ECTS trouvee)"}

    n_cols = max(len(row) for row in table)
    rows: list[dict] = []
    section_diagnostics = []
    last_good_cols = None

    for section_num, header_idx in enumerate(header_indices):
        section_end = header_indices[section_num + 1] if section_num + 1 < len(header_indices) else len(table)
        # Le libelle de semestre est parfois sur une ligne-titre juste
        # avant la vraie ligne d'en-tete (ex. "S2" suivi d'une ligne
        # "Course Unit / Module / ECTS..." separee) plutot que sur la ligne
        # d'en-tete elle-meme -- on regarde donc quelques lignes en arriere.
        lookback_start = header_indices[section_num - 1] + 1 if section_num > 0 else 0
        semestre_label = None
        for lookback_row in table[max(lookback_start, header_idx - 3) : header_idx + 1]:
            label = _find_semestre_label(lookback_row)
            if label:
                semestre_label = label

        body_start = header_idx + 1
        # saute une eventuelle 2e ligne d'en-tete fusionnee (ex. "HE" seul)
        if body_start < section_end and _is_header_continuation_row(table[body_start]):
            body_start += 1

        section_rows = table[body_start:section_end]
        cols = _classify_columns(section_rows, n_cols)
        section_diagnostics.append({"semestre": semestre_label, **cols})

        if cols["matiere_col"] is None or cols["heures_module_col"] is None:
            continue  # section illisible, ignoree (signalee via le diagnostic global)
        # ECTS absent (ex. programmes de Genie Civil) : accepte quand meme,
        # les valeurs ECTS resteront vides dans le resultat (signale plutot
        # que fiche completement ignoree).

        rows.extend(_extract_section_rows(section_rows, cols, semestre_label))
        last_good_cols = cols

    if not rows:
        return [], {"erreur": "aucune section exploitable", "sections": section_diagnostics}
    return rows, {"erreur": None, "sections": section_diagnostics, "last_cols": last_good_cols}


def _find_classe_label(table: list[list], header_idx: int) -> str | None:
    """Le libelle de classe est en general la premiere cellule non vide du
    tableau, avant la ligne d'en-tete (ex. "Classe 4DS Actuariat", "4 SIM",
    "1EM")."""
    for row in table[:header_idx]:
        for cell in row:
            if cell and _normalize(cell) not in ("", "semestre-1", "semestre-2"):
                return re.sub(r"\s+", " ", str(cell)).strip()
    return None


_JUNK_CLASSE_LABEL_PATTERN = re.compile(r"^(page\d+_tableau\d+|s\d+|semestre.*)$", re.IGNORECASE)

_FILENAME_CLASSE_PATTERN = re.compile(r"plan_d.?etude-?([a-z0-9]+)", re.IGNORECASE)


def _filename_classe_fallback(path: Path) -> str | None:
    """Certains PDF ("Plan_d'étude-3A.pdf", "Plan_d'étude-2P.pdf"...) n'ont
    aucun libelle de classe exploitable dans le tableau lui-meme (mise en
    page differente des autres fichiers) -- mais le nom de fichier encode
    deja la classe sans ambiguite, une par fichier. Utilise seulement en
    filet de secours (voir process_pdf) quand la detection en-tableau a
    echoue ou n'a trouve qu'un libelle "poubelle" (semestre/page-tableau)
    pour TOUT le fichier -- si le fichier contient plusieurs classes
    distinctes deja bien detectees (ex. SLEAM.pdf -- "4 SLEAM"/"5 SLEAM"),
    ce filet ne s'applique pas (on ne devine pas laquelle des deux)."""
    match = _FILENAME_CLASSE_PATTERN.search(_normalize(path.stem))
    return match.group(1).upper() if match else None


def process_pdf(path: Path) -> dict:
    result = {"fichier": path.name, "classes": [], "tables_non_parsees": []}
    with pdfplumber.open(str(path)) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            fallback_cols = None  # dernier classement de colonnes reussi sur CETTE page
            for table_num, table in enumerate(page.extract_tables(), start=1):
                if not table:
                    continue
                if len(table) < 3:
                    result["tables_non_parsees"].append(
                        {"page": page_num, "table": table_num, "classe_detectee": None, "erreur": "tableau trop petit (< 3 lignes)"}
                    )
                    continue
                header_indices = _find_header_row_indices(table)
                classe_label = _find_classe_label(table, header_indices[0]) if header_indices else None
                rows, diag = extract_table_rows(table, fallback_cols=fallback_cols)
                if not rows:
                    result["tables_non_parsees"].append(
                        {"page": page_num, "table": table_num, "classe_detectee": classe_label, **diag}
                    )
                    continue
                if "last_cols" in diag:
                    fallback_cols = diag["last_cols"]
                result["classes"].append(
                    {
                        "classe": classe_label or f"page{page_num}_tableau{table_num}",
                        "page": page_num,
                        "lignes": rows,
                        "diagnostic": {k: v for k, v in diag.items() if k not in ("erreur", "last_cols")},
                    }
                )

    filename_classe = _filename_classe_fallback(path)
    if filename_classe:
        distinct_valid = {
            group["classe"] for group in result["classes"]
            if not _JUNK_CLASSE_LABEL_PATTERN.match(group["classe"].strip())
        }
        if len(distinct_valid) <= 1:
            for group in result["classes"]:
                group["classe"] = filename_classe

    return result


def main() -> None:
    all_results = []
    for path in sorted(RAW_DIR.glob("*.pdf")):
        print(f"[{path.name}]", end=" ")
        result = process_pdf(path)
        n_rows = sum(len(c["lignes"]) for c in result["classes"])
        print(f"-> {len(result['classes'])} groupes classe/panier, {n_rows} lignes matiere, {len(result['tables_non_parsees'])} tableau(x) non parse(s)")
        all_results.append(result)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    total_rows = sum(sum(len(c["lignes"]) for c in r["classes"]) for r in all_results)
    total_flagged = sum(len(r["tables_non_parsees"]) for r in all_results)
    print(f"\nTotal : {total_rows} lignes matiere extraites, {total_flagged} tableau(x) signale(s) a verifier.")
    print(f"Fichier brouillon (NON fusionne dans la base) : {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
