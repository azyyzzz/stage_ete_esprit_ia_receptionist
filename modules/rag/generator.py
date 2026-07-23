"""
Génère la réponse finale à partir de la question de l'appelant et des
fiches récupérées dans la base de connaissances, via un LLM local (Ollama,
gratuit, aucune clé API).
"""

from __future__ import annotations

import ollama

from modules.rag.config import OLLAMA_MAX_TOKENS, OLLAMA_MODEL
from modules.rag.retriever import RetrievedChunk

SYSTEM_PROMPT = """Tu es l'assistant vocal de la réception de l'école d'ingénieurs ESPRIT, en Tunisie.
Tu réponds à des étudiants et des parents qui appellent par téléphone, en français ou en arabe tunisien (dialecte).

Règles :
- Réponds uniquement à partir des informations fournies dans le contexte ci-dessous. N'invente jamais d'information.
- Si le contexte ne permet pas de répondre précisément, dis-le clairement plutôt que de deviner.
- Réponds dans la même langue que la question (français ou arabe tunisien).
- Formule des réponses courtes et naturelles à l'oral (pas de listes à puces, pas de mise en forme markdown), comme dans une vraie conversation téléphonique.
"""


def _build_context(chunks: list[RetrievedChunk]) -> str:
    parts = []
    for i, chunk in enumerate(chunks, start=1):
        titre = chunk.metadata.get("titre", "")
        parts.append(f"[Extrait {i} - {titre}]\n{chunk.content}")
    return "\n\n".join(parts)


AMBIGUOUS_PROGRAMME_NOTE = (
    "\n\nNote : la question ne précise pas de quel programme il s'agit, et le "
    "contexte ci-dessus couvre plusieurs programmes différents. Ne demande "
    "pas de précision (l'appelant ne peut pas te répondre) : donne une "
    "réponse utile qui couvre les principaux cas, en mentionnant brièvement "
    "que ça varie selon le programme si les montants ou modalités diffèrent."
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
    return response["message"]["content"].strip()
