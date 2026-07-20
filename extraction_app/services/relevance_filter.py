"""
Filtrage de pertinence -- premier garde-fou avant sauvegarde.

Verifie que le titre ou le contenu d'une fiche candidate contient au moins
un mot-cle d'un des domaines couverts par l'assistant ESPRIT
(RELEVANCE_KEYWORDS dans config.py). Simple correspondance de mots-clefs,
volontairement predictible -- voir README.md pour les limites assumees de
cette approche (pas de comprehension semantique a ce stade, c'est le role
du garde-fou suivant, la verification semantique).
"""

from __future__ import annotations

import unicodedata

from extraction_app.config import RELEVANCE_KEYWORDS


def _normalize(text: str) -> str:
    """Minuscules + accents retires, pour un matching robuste face a un OCR
    ou un scraping qui n'a pas toujours des accents propres."""
    text = text.lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text


def is_relevant(titre: str, contenu: str) -> bool:
    """True si au moins un mot-cle d'un domaine ESPRIT est present dans le
    titre ou le contenu (comparaison insensible a la casse et aux accents)."""
    haystack = _normalize(f"{titre} {contenu}")
    for keywords in RELEVANCE_KEYWORDS.values():
        for keyword in keywords:
            if _normalize(keyword) in haystack:
                return True
    return False


def matched_domains(titre: str, contenu: str) -> list[str]:
    """Liste des domaines (cles de RELEVANCE_KEYWORDS) dont au moins un
    mot-cle apparait -- utile pour le journal d'historique."""
    haystack = _normalize(f"{titre} {contenu}")
    domains = []
    for domain, keywords in RELEVANCE_KEYWORDS.items():
        if any(_normalize(keyword) in haystack for keyword in keywords):
            domains.append(domain)
    return domains
