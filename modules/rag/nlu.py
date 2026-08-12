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

# Titre des fiches "Options" (voir data/scripts/scrape_esprit_tunis_options.py) :
# "Option {nom} — {specialite} — ESPRIT Tunis" -- capture la specialite pour
# la metadonnee filtrable "option_specialite" (voir ingest.py, pipeline.py).
TITRE_OPTION_SPECIALITE_PATTERN = re.compile(r"^Option .+ — (.+) — ESPRIT Tunis$")

# Mots-cles reconnaissant une specialite ESPRIT Tunis (celles qui ont des
# "Options" scrapees), independamment de la casse/accents (compares apres
# _normalize). Valeur = nom EXACT de specialite tel que stocke en metadonnee
# (voir data/raw_data/esprit_tunis_options.json).
SPECIALITE_TUNIS_KEYWORDS: dict[str, list[str]] = {
    "Ingénieur en Génie informatique": ["informatique"],
    "Ingénieur en Génie des Télécommunications": ["telecom", "télécom"],
    "Ingénieur en Génie Civil": ["civil"],
    "Ingénieur en Génie Electromécanique": ["electromecanique", "électromécanique"],
}


def detect_specialite_tunis_mention(question: str) -> str | None:
    """Renvoie le nom EXACT (valeur de metadonnee) de la specialite ESPRIT
    Tunis mentionnee dans la question si une SEULE correspond -- sinon None."""
    q_norm = _normalize(question)
    matches = [
        specialite
        for specialite, keywords in SPECIALITE_TUNIS_KEYWORDS.items()
        if any(_normalize(kw) in q_norm for kw in keywords)
    ]
    return matches[0] if len(matches) == 1 else None


@lru_cache(maxsize=1)
def _load_known_options() -> tuple[tuple[str, str], ...]:
    """(nom d'option, specialite exacte) pour chaque fiche categorie
    "Options" -- utilise quand la question ne precise PAS la specialite
    (ex. "score minimum pour l'option Data Analytics and Science ?") mais
    nomme l'option elle-meme, qui peut exister dans PLUSIEURS specialites
    a la fois (ex. "Data Analytics & Science" existe en Informatique ET en
    Telecommunications, sous des ids differents)."""
    records = json.loads(KNOWLEDGE_BASE_PATH.read_text(encoding="utf-8"))
    result: list[tuple[str, str]] = []
    for r in records:
        if r.get("categorie") != "Options":
            continue
        match = TITRE_OPTION_SPECIALITE_PATTERN.match(r.get("titre", ""))
        if not match:
            continue
        specialite = match.group(1)
        titre = r.get("titre", "")
        nom = titre.split("—")[0].strip()
        if nom.lower().startswith("option "):
            nom = nom[len("option "):].strip()
        result.append((nom, specialite))
    return tuple(result)


def detect_option_mention(question: str) -> list[str]:
    """Renvoie la liste des specialites (valeurs EXACTES de metadonnee)
    dont au moins une option correspond au nom mentionne dans la question --
    compare par PRESENCE DE TOUS LES MOTS significatifs (pas une sous-chaine
    exacte) pour tolerer les variantes ("and" vs "&", accents...). Peut
    renvoyer PLUSIEURS specialites si le meme nom d'option existe dans
    plusieurs d'entre elles (voir _load_known_options)."""
    q_tokens = set(_normalize(question).split())
    matches: list[str] = []
    for nom, specialite in _load_known_options():
        nom_tokens = [t for t in _normalize(nom).split() if len(t) > 2]
        if nom_tokens and all(t in q_tokens for t in nom_tokens) and specialite not in matches:
            matches.append(specialite)
    return matches

# Noms de classe qui sont en realite des artefacts d'extraction (page/tableau
# non identifie, marqueur de semestre isole...) -- jamais proposes comme
# filtre, une question ne les mentionnera jamais tels quels.
# Le 2e pattern rejette aussi un nom de classe contenant "semestre" N'IMPORTE
# OU (pas seulement quand il constitue tout le nom) : constate en usage reel
# avec "3B - 2025/2026 Semestre - 5", un doublon corrompu de la classe "3B"
# (qui existe deja proprement par ailleurs) genere par un titre mal parse --
# son alias auto-genere "bse" (prefixe de "b"+"semestre") matchait par
# sous-chaine le mot "absences", filtrant a tort toute question sur les
# absences vers les fiches de la classe 3B.
JUNK_CLASSE_PATTERN = re.compile(r"^(page\d+_tableau\d+|s\d+|semestre.*)$", re.IGNORECASE)
JUNK_CLASSE_CONTAINS_PATTERN = re.compile(r"\bsemestre\b", re.IGNORECASE)


def _is_junk_classe(classe_nom: str) -> bool:
    stripped = classe_nom.strip()
    return bool(JUNK_CLASSE_PATTERN.match(stripped) or JUNK_CLASSE_CONTAINS_PATTERN.search(stripped))


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
    # _normalize() a deja remplace "-"/"/" par des espaces, donc un
    # intervalle d'annees ("2025/2026", "25-26") apparait ici separe par un
    # espace, pas par le separateur d'origine -- le motif doit matcher
    # l'espace, pas [-/] (bug constate : la fiche "3B - 2025/2026 Semestre -
    # 5" gardait "2025 2026" dans son coeur faute de matcher).
    norm = re.sub(r"\b(20)?\d{2}\s+(20)?\d{2}\b", "", norm)
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
        if _is_junk_classe(classe_nom):
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
                        if classe_nom and classe_nom not in seen and not _is_junk_classe(classe_nom):
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
                            if candidate and candidate not in seen and not _is_junk_classe(candidate):
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
    exact_matches: list[str] = []
    heuristic_matches: list[str] = []
    for classe_nom in _load_known_classes():
        core = _classe_core(classe_nom)
        if not core:
            continue

        # exact core phrase match
        if re.search(rf"\b{re.escape(core)}\b", q_norm):
            exact_matches.append(classe_nom)
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
                # Check for at least one additional non-numeric token overlap
                # -- token d'1 seul caractere (ex. "a" pour la classe "3A")
                # exclu : "a"/"à" (sans accent) est un mot autonome courant
                # en francais ("il y A", "A esprit"), donc n'importe quelle
                # question mentionnant un numero ET contenant "a esprit"
                # matchait a tort la classe "3A" (constate en usage reel sur
                # "la classe 3AI", "en 3eme annee" -- aucun rapport avec la
                # classe 3A du programme d'etudes).
                if any(t in q_tokens for t in core_tokens if t not in numeric_tokens and len(t) > 1):
                    heuristic_matches.append(classe_nom)
                    continue

    # A unique exact match always wins over looser heuristics.
    if len(exact_matches) == 1:
        return exact_matches[0]
    if len(exact_matches) > 1:
        return None

    # If the heuristic already identifies a single class, trust it before
    # falling back to broader alias matching. This keeps short forms like
    # "4 BI" working without letting ambiguous aliases override them.
    if len(heuristic_matches) == 1:
        return heuristic_matches[0]

    # consult alias map for common abbreviated forms (e.g. '4bi', '4 erpbi')
    alias_map = _build_alias_map()
    alias_matches: list[str] = []
    # check longer aliases first
    for alias, canon in sorted(alias_map.items(), key=lambda kv: -len(kv[0])):
        if " " in alias:
            if re.search(rf"\b{re.escape(alias)}\b", q_norm):
                alias_matches.append(canon)
        else:
            # Un alias court (ex. "b", genere pour une classe comme "3B"
            # dont la seule partie non numerique est une lettre isolee, via
            # le prefixe de longueur 2/3 qui degenere sur un token d'1
            # caractere) matche par SOUS-CHAINE n'importe quel mot qui le
            # contient -- "b" matchait "club", faisant detecter a tort la
            # classe 3B dans une question sur un club etudiant (constate en
            # usage reel). Exiger un mot entier (pas une sous-chaine) en
            # dessous de 3 caracteres NE SUFFIT PAS : un alias d'1 SEUL
            # caractere comme "a" (classe "3A") matche alors le mot "a"
            # ou "à" (sans accent apres normalisation) -- omnipresent en
            # francais ("il y A", "A ESPRIT"...) -- constate en usage reel
            # sur "Y a-t-il une salle de sport A esprit ?". Les alias d'1
            # caractere sont donc purement et simplement ignores ; ceux de
            # 2 caracteres restent exiges en mot entier.
            if len(alias) < 2:
                continue
            if len(alias) < 3:
                if re.search(rf"\b{re.escape(alias)}\b", q_norm):
                    alias_matches.append(canon)
            elif alias in q_norm:
                alias_matches.append(canon)

    # deduplicate while preserving order
    alias_matches = list(dict.fromkeys(alias_matches))
    if len(alias_matches) == 1:
        return alias_matches[0]

    all_matches = list(dict.fromkeys([*exact_matches, *heuristic_matches, *alias_matches]))
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
            if len(o) > 3:
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

    # phrasing: "quels sont les paniers ..." or "quels paniers ..."
    if re.search(r"\bquels? sont\b", q_norm) and re.search(r"\b(paniers?|matieres?|modules?)\b", q_norm):
        return True
    if re.search(r"\bquels? paniers?\b", q_norm):
        return True

    if (
        re.search(r"\b(c\s*est\s*quoi|qu\s*est\s*ce\s*que|quest\s*ce\s*que)\b", q_norm)
        and ("mati" in q_norm or "module" in q_norm or "panier" in q_norm)
    ):
        return True
    if re.search(r"\b(jetudie|etudie)\b", q_norm) and ("mati" in q_norm or "module" in q_norm or "panier" in q_norm):
        return True

    return False


def is_list_specialites_intent(question: str) -> bool:
    """True si la question demande la liste des spécialités d'un campus
    ESPRIT (Tunis/Monastir/Prépa) plutôt qu'un fait précis sur une
    spécialité en particulier -- détermine si la recherche doit récupérer
    TOUTES les fiches "Programmes" de ce campus (voir pipeline.py, filtre
    metadonnee "campus") plutôt que se limiter à TOP_K, qui en omettrait
    mécaniquement une partie (ex. ESPRIT Monastir a 4 spécialités
    d'ingénieur, TOP_K=5 les noie parmi des fiches non pertinentes)."""
    q_norm = _normalize(question)
    if "specialite" not in q_norm:
        return False
    return _has_list_wording(q_norm)


def _has_list_wording(q_norm: str) -> bool:
    """Formulation "liste tout" -- se base sur le NOMBRE du pronom
    interrogatif, pas sur le verbe qui suit : "quels"/"quelles" (pluriel)
    signale une liste ("quelles specialites PROPOSE...", "quelles sont
    les options...") quel que soit le verbe, alors que "quel"/"quelle"
    (singulier, ex. "quel EST le score minimum") signale un fait precis --
    a ne surtout pas confondre en imposant un verbe specifique comme
    "sont" (exclurait a tort "quelles ... propose").

    "toutes"/"tous" seuls ont ete retires du declencheur (faux positif
    constate en usage reel : "Le tarif est-il le meme pour TOUTES les
    specialites ?" n'est PAS une demande de liste, mais une comparaison a
    travers les specialites -- le mot apparait dans bien d'autres
    tournures que "liste tout"). "quelles ... toutes les specialites"
    reste couvert par le test quel(s|les) ci-dessus, donc rien n'est perdu
    pour la vraie formulation de liste exhaustive.

    "c'est quoi les X" (normalise en "c est quoi les X", tres frequent a
    l'oral/dans le jeu de test) suit la meme logique que quel(s|les) :
    l'article pluriel "les" juste apres "quoi" signale une liste ("c'est
    quoi LES specialites qu'ESPRIT propose" == "quelles sont les
    specialites"), alors que l'article singulier ("c'est quoi LA classe
    3AI") signale un fait precis sur une seule chose -- meme distinction
    exactement, portee par l'article plutot que par quel/quels."""
    return bool(
        re.search(r"\bquel(s|les)\b", q_norm)
        or re.search(r"\bliste\b", q_norm)
        or re.search(r"\bquoi les\b", q_norm)
    )


def is_list_options_intent(question: str) -> bool:
    """True si la question demande la liste des options de specialisation
    d'une specialite ESPRIT Tunis (voir data/scripts/scrape_esprit_tunis_
    options.py) plutot qu'un fait precis sur une option en particulier --
    meme logique que is_list_specialites_intent, un niveau en dessous
    (options au sein d'une specialite plutot que specialites d'un campus)."""
    q_norm = _normalize(question)
    if "option" not in q_norm:
        return False
    return _has_list_wording(q_norm)


def is_count_intent(question: str) -> bool:
    """True si la question cherche un nombre de matieres/modules
    (ex: "Combien de matières...", "Quel est le nombre de modules...")."""
    q_norm = _normalize(question)
    if re.search(r"\bcombien\b", q_norm) and re.search(r"\b(matieres?|modules?)\b", q_norm):
        return True
    if re.search(r"\bnombre\b", q_norm) and re.search(r"\b(matieres?|modules?)\b", q_norm):
        return True
    return False
