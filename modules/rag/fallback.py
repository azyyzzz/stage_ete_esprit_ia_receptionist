"""
Messages de redirection vers un service humain, utilisés quand aucune fiche
de la base de connaissances n'est assez pertinente pour répondre (score de
similarité sous le seuil).

La catégorie est devinée par mots-clés simples à partir de la question. Ce
n'est pas une IA : c'est volontairement prévisible et facile à corriger/
étendre au fur et à mesure des retours d'usage.
"""

from __future__ import annotations

FALLBACK_MESSAGES: dict[str, str] = {
    "admission": (
        "Je n'ai pas cette information précise sur les admissions. "
        "Je vous invite à contacter le service admissions, situé au "
        "rez-de-chaussée du bloc E."
    ),
    "faq": (
        "Je n'ai pas trouvé de réponse précise à votre question. "
        "Vous pouvez nous contacter sur nos réseaux sociaux, ou vous "
        "présenter à la réception, à l'entrée du bloc E."
    ),
    "calendrier": (
        "Je n'ai pas cette information de calendrier. "
        "Elle a normalement été communiquée par email ; sinon, le service "
        "de la scolarité pourra vous renseigner."
    ),
    "paiement": (
        "Je n'ai pas cette information sur les paiements. "
        "Je vous invite à contacter le service financier, situé au "
        "premier étage du bloc E."
    ),
    "general": (
        "Je n'ai pas d'information précise à ce sujet. "
        "Je vous invite à contacter directement la réception d'ESPRIT, "
        "à l'entrée du bloc E, qui pourra vous orienter."
    ),
}

# Mots-clés (français + variantes courantes en arabe translittéré) qui
# orientent vers chaque catégorie. Listes volontairement simples : à enrichir
# avec de vrais exemples d'appels une fois le module en usage.
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "admission": ["admission", "inscription", "s'inscrire", "dossier", "concours", "bac"],
    "faq": ["faq", "question fréquente", "aide"],
    "calendrier": ["calendrier", "date", "examen", "vacances", "rentrée", "planning", "semestre"],
    "paiement": ["paiement", "frais", "scolarité", "tranche", "payer", "montant", "facture", "dinars", "dt"],
}


def guess_category(question: str) -> str:
    q = question.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in q for keyword in keywords):
            return category
    return "general"


def get_fallback_message(question: str) -> str:
    category = guess_category(question)
    return FALLBACK_MESSAGES[category]
