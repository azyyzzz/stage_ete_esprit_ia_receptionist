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
    "bac5-master": "ESPRIT School of Business - Master",
    "bac3-bachelor-esb": "ESPRIT School of Business - Bachelor",
    "classe-internationale-2": "Classe internationale",
}


def programme_label(source_url: str) -> str | None:
    """Renvoie le libellé du programme concerné par cette URL, ou None si la
    page n'est pas spécifique à un programme (FAQ générale, infos
    pratiques...)."""
    segments = [s for s in source_url.rstrip("/").split("/") if s]
    for segment in reversed(segments):
        if segment in PROGRAMME_LABELS:
            return PROGRAMME_LABELS[segment]
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
    "Campus Monastir": ["monastir"],
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
