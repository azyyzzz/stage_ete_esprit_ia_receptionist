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


def generate_answer(question: str, chunks: list[RetrievedChunk]) -> str:
    context = _build_context(chunks)
    user_prompt = f"Contexte disponible :\n{context}\n\nQuestion de l'appelant : {question}"

    response = ollama.chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        options={"num_predict": OLLAMA_MAX_TOKENS},
    )
    return response["message"]["content"].strip()
