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
        if core and re.search(rf"\b{re.escape(core)}\b", q_norm):
            matches.append(classe_nom)
    if len(matches) == 1:
        return matches[0]
    return None


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
]


def is_list_all_intent(question: str) -> bool:
    """True si la question demande une liste exhaustive (matieres/paniers
    d'une classe) plutot qu'un fait precis sur une matiere -- determine
    si la recherche doit recuperer TOUTES les fiches d'une classe plutot
    que TOP_K."""
    q_norm = _normalize(question)
    return any(keyword in q_norm for keyword in LIST_ALL_KEYWORDS)
