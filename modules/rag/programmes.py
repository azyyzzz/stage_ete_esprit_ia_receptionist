"""
Détection du programme concerné par une fiche de la base de connaissances,
à partir de son URL source -- sert à repérer quand une question générique
("combien ça coûte ?") pourrait concerner plusieurs programmes différents
avec des tarifs/modalités propres (cours du jour, cours du soir, EMBA...),
pour demander une précision plutôt que de répondre avec les infos d'un seul
programme au hasard.
"""

from __future__ import annotations

# Segment d'URL le plus specifique -> libelle humain. Seuls les programmes
# ayant des modalites propres (tarifs, admission...) sont listes ici ; les
# pages generiques (FAQ, infos pratiques, gouvernance...) ne sont pas des
# "programmes" concurrents et sont ignorees (programme_label renvoie None).
PROGRAMME_LABELS: dict[str, str] = {
    "cours-du-jour-tunisiens": "Cours du jour (étudiants tunisiens)",
    "cours-du-jour-internationaux": "Cours du jour (étudiants internationaux)",
    "cours-du-soir": "Cours du soir",
    "emba-esprit-tunis": "EMBA / Executive",
    "formation-en-alternance": "Formation en alternance",
    "esprit-prepa": "Classe préparatoire (PREPA)",
    "esprit-monastir": "Campus Monastir",
    "esprit-monastir-esprim": "Campus Monastir",
    # Page racine des specialites d'ingenieur ESPRIT Tunis (nos-programmes/
    # programmes-dingenieur/) -- doit rester un label DISTINCT de "Campus
    # Monastir" et "Classe preparatoire (PREPA)" pour que _ambiguous_programmes
    # (pipeline.py) detecte bien une question sur une specialite qui existe
    # sous des noms proches dans plusieurs ecoles (ex. "informatique" =
    # Specialite Informatique a Tunis vs Genie Informatique a Monastir) et
    # demande une precision au lieu de melanger les deux campus.
    "programmes-dingenieur": "ESPRIT Tunis",
    "bac5-master": "ESPRIT School of Business - Master",
    "bac3-bachelor-esb": "ESPRIT School of Business - Bachelor",
    "classe-internationale-2": "Classe internationale",
}


# Les reglements (chartes, articles) sont scrapes depuis des PDF dont
# l'URL ("Reglement-scolarite-24-25-cs.pdf") ne contient AUCUN segment de
# PROGRAMME_LABELS -- programme_label() base sur l'URL seule renvoie donc
# systematiquement None pour TOUTE fiche de reglement, meme quand son
# TITRE dit explicitement de quel programme il s'agit ("Cours du soir -
# Article 4 : ..."). Constate en usage reel : une question generale sur
# les horaires ("a quelle heure commencent les etudes ?") remonte a la
# fois une fiche EMBA (URL reconnue) et "Cours du soir - Article 4" (URL
# PDF non reconnue) parmi ses meilleurs resultats, mais _ambiguous_
# programmes (pipeline.py) ne detectait qu'UN SEUL programme (EMBA) --
# l'autre etant invisible -- et ne demandait donc jamais de precision
# jour/soir. Prefixe de titre -> label, verifie en dernier recours si le
# titre commence par exactement ce prefixe suivi de " - Article " (evite
# les faux positifs sur un titre qui mentionnerait "cours du soir" en
# milieu de phrase, sans etre reellement un article de reglement de ce
# programme).
TITRE_REGLEMENT_PREFIXES: dict[str, str] = {
    "Cours du jour (English)": "Cours du jour (étudiants internationaux)",
    "Cours du jour": "Cours du jour (étudiants tunisiens)",
    "Cours du soir": "Cours du soir",
    "Formation en alternance": "Formation en alternance",
}


def programme_label(source_url: str, titre: str = "") -> str | None:
    """Renvoie le libellé du programme concerné par cette fiche (URL en
    priorité, titre en repli pour les reglements PDF -- voir
    TITRE_REGLEMENT_PREFIXES), ou None si elle n'est spécifique à aucun
    programme (FAQ générale, infos pratiques...)."""
    segments = [s for s in source_url.rstrip("/").split("/") if s]
    for segment in reversed(segments):
        if segment in PROGRAMME_LABELS:
            return PROGRAMME_LABELS[segment]

    # Les cles les plus longues d'abord : "Cours du jour (English)" doit
    # matcher avant "Cours du jour" pour un titre qui commence par le
    # prefixe anglais.
    for prefixe in sorted(TITRE_REGLEMENT_PREFIXES, key=len, reverse=True):
        if titre.startswith(prefixe + " - Article "):
            return TITRE_REGLEMENT_PREFIXES[prefixe]

    # Quelques fiches (documents a fournir, grilles tarifaires...) portent
    # le programme comme SUFFIXE de titre plutot que dans l'URL source (ex.
    # "Documents à fournir pour l'inscription (étudiants tunisiens)" a une
    # URL generique "admissions/informations-pratiques/", non reconnue) --
    # constate en usage reel : sans ce repli, la version "tunisiens" restait
    # invisible a la detection d'ambiguite alors que sa jumelle
    # "internationaux" (URL specifique reconnue) l'etait, empechant de
    # detecter que la question ("quels documents fournir ?", sans preciser
    # la nationalite) est ambigue entre les deux -- le LLM choisissait alors
    # la mauvaise (constate : documents "internationaux" -- passeport, visa
    # -- donnes en reponse a un etudiant tunisien).
    if titre.rstrip().endswith("(étudiants tunisiens)"):
        return "Cours du jour (étudiants tunisiens)"
    if titre.rstrip().endswith("(étudiants internationaux)"):
        return "Cours du jour (étudiants internationaux)"
    return None


# Mots-clés qui, s'ils apparaissent dans la question, indiquent que
# l'appelant a déjà précisé de quel programme il parle -- évite de demander
# une clarification inutile quand ce n'est pas ambigu pour lui.
PROGRAMME_KEYWORDS: dict[str, list[str]] = {
    "Cours du jour (étudiants tunisiens)": ["jour"],
    "Cours du jour (étudiants internationaux)": ["international", "internationaux", "étranger", "etranger"],
    "Cours du soir": ["soir"],
    "EMBA / Executive": ["emba", "executive"],
    "Formation en alternance": ["alternance"],
    "Campus Monastir": ["monastir", "esprim"],
    "ESPRIT Tunis": ["tunis"],
    "ESPRIT School of Business - Master": ["master", "bac+5", "bac 5"],
    "ESPRIT School of Business - Bachelor": ["bachelor", "bac+3", "bac 3"],
    "Classe internationale": ["classe internationale"],
    "Classe préparatoire (PREPA)": ["prepa", "prépa", "préparatoire"],
}


def mentioned_programme(question: str, candidates: set[str]) -> str | None:
    """Si la question mentionne explicitement l'un des programmes candidats
    (et un seul), le renvoie -- sinon None (question réellement ambiguë)."""
    q = question.lower()
    matches = [
        label
        for label in candidates
        if any(keyword in q for keyword in PROGRAMME_KEYWORDS.get(label, []))
    ]
    return matches[0] if len(matches) == 1 else None


# Les 3 "campus"/programmes d'ingenieur ESPRIT ayant chacun leurs propres
# specialites -- utilise par ingest.py (metadonnee "campus" filtrable) et
# pipeline.py (question "quelles specialites propose ESPRIT <campus> ?") pour
# recuperer TOUTES les fiches de specialites du campus mentionne plutot que de
# se limiter a TOP_K, qui en omettrait mecaniquement une partie.
CAMPUS_LABELS: frozenset[str] = frozenset(
    {"ESPRIT Tunis", "Campus Monastir", "Classe préparatoire (PREPA)"}
)
