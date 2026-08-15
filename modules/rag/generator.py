"""
Génère la réponse finale à partir de la question de l'appelant et des
fiches récupérées dans la base de connaissances, via un LLM local (Ollama,
gratuit, aucune clé API).
"""

from __future__ import annotations

import re

import ollama

from modules.rag.config import OLLAMA_MAX_TOKENS, OLLAMA_MODEL
from modules.rag.retriever import RetrievedChunk

SYSTEM_PROMPT = """Tu es l'assistant vocal de la réception de l'école d'ingénieurs ESPRIT, en Tunisie.
Tu réponds à des étudiants et des parents qui appellent par téléphone, en français ou en arabe.

Règles :
- Réponds uniquement à partir des informations fournies dans le contexte ci-dessous. N'invente jamais d'information.
- Si le contexte ne permet pas de répondre précisément, dis-le clairement plutôt que de deviner.
- Langue de la réponse (règle stricte) : si la question est posée en français, réponds en français.
  Si la question est posée en arabe -- que ce soit en arabe standard (fusha) OU en dialecte tunisien
  (mélangé ou non avec du français) -- réponds TOUJOURS en arabe standard (فصحى), jamais en dialecte
  tunisien. Même si l'appelant t'écrit ou te parle en dialecte, NE COPIE PAS son registre : traduis
  mentalement ta réponse en arabe standard correct avant de répondre. Aucune autre langue/dialecte
  n'est acceptable en sortie.
- Formule des réponses courtes et naturelles à l'oral (pas de listes à puces, pas de mise en forme markdown), comme dans une vraie conversation téléphonique.
- Si le contexte décrit plusieurs cas, conditions ou étapes distincts (ex. plusieurs itérations, configurations, ou "si... sinon..."), énumère-les TOUS dans ta réponse, avec des transitions orales ("d'abord... ensuite... enfin...", "premièrement... deuxièmement..."), plutôt que de les résumer en une seule phrase vague qui perd l'information précise -- c'est souvent un règlement qui régit un droit de l'étudiant, l'exactitude prime sur la brièveté.
"""

# Sépare les phrases (. ! ?) suivies d'une majuscule/lettre arabe -- ne coupe
# pas sur les points internes aux nombres/dates du domaine (dates en JJ/MM/AAAA,
# montants avec virgule décimale), qui ne sont jamais suivis de "espace + majuscule".
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-ÖØ-Þ؀-ۿ])")


def _one_sentence_per_line(text: str) -> str:
    """Force un saut de ligne apres chaque phrase, au sein de chaque
    paragraphe deja produit par le modele -- le prompt seul (regle, exemple,
    few-shot conversationnel) ne suffit pas a faire respecter ce format de
    maniere fiable par ce modele 7B quantifie/degrade (CPU+GPU), donc on le
    garantit ici de facon deterministe plutot que de dependre du modele."""
    paragraphs = text.split("\n\n")
    result_paragraphs = []
    for paragraph in paragraphs:
        sentences = _SENTENCE_SPLIT_RE.split(paragraph.strip())
        result_paragraphs.append("\n".join(s.strip() for s in sentences if s.strip()))
    return "\n\n".join(result_paragraphs)


def _build_context(chunks: list[RetrievedChunk]) -> str:
    parts = []
    for i, chunk in enumerate(chunks, start=1):
        titre = chunk.metadata.get("titre", "")
        parts.append(f"[Extrait {i} - {titre}]\n{chunk.content}")
    return "\n\n".join(parts)


AMBIGUOUS_PROGRAMME_NOTE = (
    "\n\nNote : la question ne précise pas de quel programme/campus il "
    "s'agit, et le contexte ci-dessus couvre plusieurs programmes "
    "différents (regarde bien le nom du campus/programme indiqué dans le "
    "titre de chaque extrait -- ne le confonds pas avec un autre). Ne "
    "demande pas de précision (l'appelant ne peut pas te répondre) : "
    "réponds séparément pour CHAQUE programme/campus concerné, en le "
    "nommant explicitement à chaque fois (ex. \"À ESPRIT Tunis, ... ; à "
    "ESPRIT Monastir, ...\"). N'attribue jamais une information à un "
    "programme/campus si l'extrait correspondant ne le mentionne pas "
    "explicitement -- si un extrait ne concerne qu'un seul campus, ne "
    "dis rien sur les autres pour ce point précis plutôt que de deviner."
)


LIST_ALL_NOTE = (
    "\n\nNote : le contexte ci-dessus contient TOUTES les fiches de la classe "
    "concernée (pas une sélection partielle) car la question demande une liste "
    "exhaustive. Énumère bien tous les paniers/matières présents dans le "
    "contexte, sans en résumer ou en omettre une partie."
)


def generate_answer(
    question: str,
    chunks: list[RetrievedChunk],
    ambiguous_programme: bool = False,
    list_all: bool = False,
) -> str:
    context = _build_context(chunks)
    user_prompt = f"Contexte disponible :\n{context}\n\nQuestion de l'appelant : {question}"
    if ambiguous_programme:
        user_prompt += AMBIGUOUS_PROGRAMME_NOTE
    if list_all:
        user_prompt += LIST_ALL_NOTE

    response = ollama.chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        options={"num_predict": OLLAMA_MAX_TOKENS},
    )
    return _one_sentence_per_line(response["message"]["content"].strip())
