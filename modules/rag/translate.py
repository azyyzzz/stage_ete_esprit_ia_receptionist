"""
Traduction arabe -> francais d'une question, pour que la recherche par
similarite (base de connaissances presque entierement en francais) reste
fiable meme quand l'appelant pose sa question en arabe (ou un melange
arabe/francais). Voir modules/rag/pipeline.py::answer_question.

Constate en usage reel : une question en arabe pur matche nettement moins
bien (~0.08 de similarite cosinus en moins, mesure sur un cas reel) la
fiche pertinente que son equivalent francais -- assez pour la faire sortir
du top_k et faire repondre le modele a cote du sujet. Traduire la question
AVANT la recherche (pas apres) corrige ca a la source, au prix d'un appel
LLM supplementaire (donc plus lent pour les questions concernees).
"""

from __future__ import annotations

import re

import ollama

from modules.rag.config import OLLAMA_MODEL

# Plage Unicode de l'alphabet arabe -- simple detection de script, pas une
# vraie detection de langue (suffisant : l'appelant n'utilise que le
# francais, l'arabe, ou un melange des deux, voir generator.py).
_ARABIC_CHAR_RE = re.compile(r"[؀-ۿ]")

_TRANSLATE_SYSTEM_PROMPT = (
    "Tu es un traducteur. Traduis fidèlement en français le texte fourni, "
    "sans l'expliquer, sans ajouter de commentaire, sans guillemets. S'il "
    "contient déjà des mots en français, garde-les tels quels et traduis "
    "uniquement les parties en arabe. Réponds uniquement avec la "
    "traduction, rien d'autre.\n\n"
    "Utilise TOUJOURS le vocabulaire administratif exact utilisé à ESPRIT "
    "plutôt qu'une traduction littérale ou approximative -- une mauvaise "
    "terminologie fait ensuite échouer la recherche dans la base de "
    "connaissances. Lexique de référence :\n"
    "شهادة حضور / وثيقة حضور -> attestation de présence\n"
    "شهادة نجاح -> attestation de réussite\n"
    "كشف نقاط / كشف الأعداد -> relevé de notes\n"
    "مصاريف الدراسة / معاليم -> frais de scolarité\n"
    "تسجيل -> inscription\n"
    "قسط -> tranche\n"
    "شهادة -> attestation ou certificat (selon contexte administratif ESPRIT)"
)


def contains_arabic(text: str) -> bool:
    return bool(_ARABIC_CHAR_RE.search(text))


def translate_to_french(text: str) -> str:
    """Traduit `text` en français via le LLM local (meme modele que le
    RAG, aucune dependance supplementaire). Renvoie le texte original si la
    traduction echoue ou renvoie une chaine vide -- filet de securite, ne
    doit jamais empecher la recherche de se poursuivre."""
    try:
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": _TRANSLATE_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            options={"num_predict": 150},
        )
        translated = response["message"]["content"].strip()
        return translated or text
    except Exception:
        return text
