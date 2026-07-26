"""
NLU legere, a base de regles (pas de framework -- coherent avec la
contrainte 100% local/gratuit et le style deja existant de
modules/rag/programmes.py, qui fait exactement ce type de desambiguisation
par mots-cles pour les "programmes" admissions).

Reconnait deux choses dans une question :
1. Une classe precise du programme d'etude ("4 ERP-BI", "4DS"...), pour
   filtrer la recherche par metadonnee ChromaDB plutot que de compter
   uniquement sur la similarite d'embedding -- deux classes voisines (ex.
   "4 ERP-BI" / "5 ERP-BI") ne se distinguent souvent que par un chiffre,
   signal trop faible pour l'embedding seul (constate en usage reel, voir
   rapport).
2. Une intention "liste tout" (vs question sur un fait precis), pour
   recuperer TOUTES les fiches d'une classe (voir retriever.retrieve_all)
   au lieu de se limiter a TOP_K -- une classe a souvent 10+ fiches (une
   par panier), TOP_K=5 en cache mecaniquement la moitie.

Meme philosophie que mentioned_programme() : en cas de doute (plusieurs
classes candidates), ne renvoie rien plutot que de deviner -- coherent avec
la regle du projet de ne jamais demander de clarification en mode vocal.
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache

from modules.rag.config import KNOWLEDGE_BASE_PATH
from pathlib import Path

# Optional extra parsed programmes file (may contain additional class names)
EXTRA_PROGRAMMES_PATH = Path(__file__).resolve().parents[2] / "data" / "processed" / "programmes_etude_a_valider.json"

TITRE_CLASSE_PATTERN = re.compile(r"^Programme d'étude — (.+?) — ")

# Noms de classe qui sont en realite des artefacts d'extraction (page/tableau
# non identifie, marqueur de semestre isole...) -- jamais proposes comme
# filtre, une question ne les mentionnera jamais tels quels.
JUNK_CLASSE_PATTERN = re.compile(r"^(page\d+_tableau\d+|s\d+|semestre.*)$", re.IGNORECASE)


def _normalize(text: str) -> str:
    text = text.lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[-/_]", " ", text)
    # ensure separation between digits and letters (e.g. '4bi' -> '4 bi')
    text = re.sub(r"(?<=\d)(?=[A-Za-z])", " ", text)
    text = re.sub(r"(?<=[A-Za-z])(?=\d)", " ", text)
    # remove punctuation (keep word chars and whitespace)
    text = re.sub(r"[^\w\s]", " ", text)
    # "4eme"/"4ème"/"4e"/"1ere"/"1ère" -> "4", "1"... (suffixe ordinal colle au chiffre)
    text = re.sub(r"(\d)\s*(?:eres?|ères?|emes?|èmes?|e)\b", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _classe_core(classe_nom: str) -> str:
    """Forme normalisee "coeur" d'un nom de classe : sans prefixe "Classe",
    sans suffixe d'annee academique (25-26, 2025-2026...), pour comparer un
    nom de classe a une question independamment de ces variations."""
    norm = _normalize(classe_nom)
    norm = re.sub(r"^classe\s+", "", norm)
    norm = re.sub(r"\b(20)?\d{2}\s*[-/]\s*(20)?\d{2}\b", "", norm)
    return re.sub(r"\s+", " ", norm).strip()


@lru_cache(maxsize=1)
def _load_known_classes() -> tuple[str, ...]:
    """Toutes les classes distinctes du programme d'etude, telles
    qu'apparaissant dans site_esprit_clean.json (nom original, pas
    normalise -- c'est la valeur exacte stockee en metadonnee ChromaDB)."""
    records = json.loads(KNOWLEDGE_BASE_PATH.read_text(encoding="utf-8"))
    classes: list[str] = []
    seen = set()
    for r in records:
        if r.get("categorie") != "Programme d'étude":
            continue
        match = TITRE_CLASSE_PATTERN.match(r.get("titre", ""))
        if not match:
            continue
        classe_nom = match.group(1)
        if JUNK_CLASSE_PATTERN.match(classe_nom.strip()):
            continue
        if classe_nom not in seen:
            seen.add(classe_nom)
            classes.append(classe_nom)
        try:
            if EXTRA_PROGRAMMES_PATH.exists():
                extra = json.loads(EXTRA_PROGRAMMES_PATH.read_text(encoding="utf-8"))
                for file_entry in extra:
                    # existing parsed classes
                    for cls in file_entry.get("classes", []):
                        classe_nom = cls.get("classe", "")
                        if classe_nom and classe_nom not in seen and not JUNK_CLASSE_PATTERN.match(classe_nom.strip()):
                            seen.add(classe_nom)
                            classes.append(classe_nom)
                    # if no classes parsed, try to extract a class-like token from the filename
                    if not file_entry.get("classes"):
                        fname = file_entry.get("fichier", "")
                        if fname:
                            # remove common prefixes/suffixes and extension
                            candidate = fname.replace("Plan d'étude", "")
                            candidate = candidate.replace("Plan d'études", "")
                            candidate = candidate.replace("Plan d\u2019etude", "")
                            candidate = candidate.replace("Plan d\u2019etudes", "")
                            candidate = candidate.replace(".pdf", "")
                            # strip years like 2526 or 25-26
                            candidate = re.sub(r"\b\d{2}[- ]?\d{2}\b", "", candidate)
                            candidate = candidate.strip()
                            if candidate and candidate not in seen and not JUNK_CLASSE_PATTERN.match(candidate):
                                seen.add(candidate)
                                classes.append(candidate)
        except Exception:
            # ignore parsing errors of the extra file
            pass

    return tuple(classes)
    


def detect_classe_mention(question: str) -> str | None:
    """Renvoie le nom de classe (valeur exacte a utiliser dans un filtre
    ChromaDB where={"classe": ...}) si la question en mentionne UNE SEULE
    sans ambiguite -- sinon None (soit aucune classe mentionnee, soit
    plusieurs candidates possibles)."""
    q_norm = _normalize(question)
    matches = []
    for classe_nom in _load_known_classes():
        core = _classe_core(classe_nom)
        if not core:
            continue

        # exact core phrase match
        if re.search(rf"\b{re.escape(core)}\b", q_norm):
            matches.append(classe_nom)
            continue

        # token-overlap heuristic: require the numeric part (e.g. '4') and at
        # least one other token from the core (e.g. 'bi' from '4 erp bi') to
        # tolerate abbreviated user queries like '4 bi' -> match '4 ERP-BI'.
        core_tokens = [t for t in core.split() if t]
        q_tokens = q_norm.split()
        if not core_tokens:
            continue
        # find numeric token in core (e.g. '4')
        numeric_tokens = [t for t in core_tokens if re.fullmatch(r"\d+", t)]
        if numeric_tokens:
            if any(nt in q_tokens for nt in numeric_tokens):
                # check for at least one additional non-numeric token overlap
                if any(t in q_tokens for t in core_tokens if t not in numeric_tokens):
                    matches.append(classe_nom)
                    continue
    if len(matches) == 1:
        return matches[0]

    # consult alias map for common abbreviated forms (e.g. '4bi', '4 erpbi')
    alias_map = _build_alias_map()
    alias_matches: list[str] = []
    # check longer aliases first
    for alias, canon in sorted(alias_map.items(), key=lambda kv: -len(kv[0])):
        if " " in alias:
            if re.search(rf"\b{re.escape(alias)}\b", q_norm):
                alias_matches.append(canon)
        else:
            if alias in q_norm:
                alias_matches.append(canon)

    # deduplicate while preserving order
    alias_matches = list(dict.fromkeys(alias_matches))
    if len(alias_matches) == 1:
        return alias_matches[0]

    all_matches = list({*matches, *alias_matches})
    if len(all_matches) == 1:
        return all_matches[0]

    return None


@lru_cache(maxsize=1)
def _build_alias_map() -> dict[str, str]:
    """Build a mapping of alias -> canonical class name to recognise common
    abbreviations/variants (e.g. '4 bi', '4bi', '4 erpbi' -> '4 ERP-BI').
    The keys are normalized strings (compatible with `_normalize`)."""
    amap: dict[str, str] = {}
    for classe_nom in _load_known_classes():
        core = _classe_core(classe_nom)
        if not core:
            continue
        tokens = [t for t in core.split() if t]
        # base forms
        amap[core] = classe_nom
        amap[core.replace(" ", "")] = classe_nom
        amap[core.replace(" ", "-")] = classe_nom

        # numeric + token variants: '4 bi', '4bi'
        nums = [t for t in tokens if re.fullmatch(r"\d+", t)]
        others = [t for t in tokens if t not in nums]
        if nums and others:
            n = nums[0]
            for o in others:
                amap[f"{n} {o}"] = classe_nom
                amap[f"{n}{o}"] = classe_nom
                amap[f"{n}-{o}"] = classe_nom

        # concatenated significant tokens (e.g. 'erpbi')
        if len(others) >= 1:
            concat = "".join(others)
            amap[concat] = classe_nom
            amap[" ".join(others)] = classe_nom
            # numeric + concatenation: '4erpbi', '4 erpbi'
            if nums:
                n = nums[0]
                amap[f"{n}{concat}"] = classe_nom
                amap[f"{n} {concat}"] = classe_nom
                amap[f"{n}-{concat}"] = classe_nom

        # also add single-token aliases (avoid pure numbers)
        for o in others:
            if len(o) > 1:
                amap[o] = classe_nom

        # initials (e.g. 'erp bi' -> 'eb') and short-prefix concatenations
        try:
            initials = "".join(t[0] for t in tokens if t)
            if initials and initials not in amap:
                amap[initials] = classe_nom
                if nums:
                    amap[f"{nums[0]}{initials}"] = classe_nom

            # prefix lengths 2 and 3 for each 'other' token, concatenated
            for L in (2, 3):
                pref = "".join((t[:L] for t in others if t))
                if pref and pref not in amap:
                    amap[pref] = classe_nom
                    if nums:
                        amap[f"{nums[0]}{pref}"] = classe_nom
        except Exception:
            # be defensive: never fail alias building for unexpected token shapes
            pass

    return amap


LIST_ALL_KEYWORDS = [
    "liste",
    "toutes les matieres",
    "tous les paniers",
    "tous les modules",
    "l'ensemble des matieres",
    "quelles sont toutes",
    "quels sont toutes",
    "quelles sont les matieres",
    "quels sont les matieres",
    "liste des matieres",
    "liste les matieres",
    "donne la liste",
    # Questions de comparaison/superlatif ("quel panier a le plus d'ECTS ?") :
    # ne visent pas un fait unique mais exigent de comparer TOUTES les
    # fiches d'une classe -- meme besoin que "liste tout" (retrieve_all),
    # sinon le TOP_K=5 ne contient pas forcement le bon panier a comparer,
    # et aucune fiche individuelle ne "ressemble" a une question de
    # comparaison (score de similarite trop bas, reponse en repli a tort).
    "le plus eleve",
    "la plus elevee",
    "le plus haut",
    "la plus haute",
    "le plus grand",
    "la plus grande",
    "le moins eleve",
    "la moins elevee",
    "le plus petit",
    "la plus petite",
    "le maximum",
    "le minimum",
]


def is_list_all_intent(question: str) -> bool:
    """True si la question demande une liste exhaustive OU une comparaison
    (matieres/paniers d'une classe) plutot qu'un fait precis sur une seule
    matiere -- determine si la recherche doit recuperer TOUTES les fiches
    d'une classe plutot que TOP_K."""
    q_norm = _normalize(question)
    # direct keyword match
    if any(keyword in q_norm for keyword in LIST_ALL_KEYWORDS):
        return True

    # common phrasing: "combien de matieres", "combien y a-t-il de modules"
    if re.search(r"\bcombien\b", q_norm) and re.search(r"\b(matieres?|modules?)\b", q_norm):
        return True

    # phrasing: "quelles sont les matieres ..." or "quelles sont les matieres du programme"
    if re.search(r"\bquelles? sont\b", q_norm) and re.search(r"\b(matieres?|modules?)\b", q_norm):
        return True

    return False


def is_count_intent(question: str) -> bool:
    """True si la question cherche un nombre de matieres/modules
    (ex: "Combien de matières...", "Quel est le nombre de modules...")."""
    q_norm = _normalize(question)
    if re.search(r"\bcombien\b", q_norm) and re.search(r"\b(matieres?|modules?)\b", q_norm):
        return True
    if re.search(r"\bnombre\b", q_norm) and re.search(r"\b(matieres?|modules?)\b", q_norm):
        return True
    return False
