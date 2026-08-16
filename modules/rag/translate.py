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
    "RÈGLES ABSOLUES (violées à plusieurs reprises en usage réel -- lire attentivement) :\n"
    "1. Tu TRADUIS la question, tu n'y RÉPONDS JAMAIS. Même si la question semble "
    "fermée (oui/non, \"y a-t-il...\", \"هل توجد...\", \"فما...\"), ta sortie doit "
    "rester une QUESTION en français, jamais une affirmation ou une négation "
    "(ex. \"هل توجد قسم تحضيري ؟\" -> \"Y a-t-il une classe préparatoire ?\" -- "
    "JAMAIS \"Il n'y a pas de classe préparatoire.\", qui serait une réponse "
    "inventée, pas une traduction).\n"
    "2. N'invente JAMAIS un code de classe précis (3A, 3B, 3AI, 4DS...) si le texte "
    "original n'en mentionne aucun explicitement. \"la troisième année\" / "
    "\"السنة الثالثة\" reste générique (\"la troisième année\"), ne devient JAMAIS "
    "\"classe 3A\" ou \"classe 3B\" sans code explicite dans le texte source.\n"
    "3. Si la phrase originale est une question, la traduction DOIT rester une "
    "question de même forme (pas de groupe nominal tronqué) -- "
    "\"ما هو قسم 3AI؟\" -> \"Qu'est-ce que la classe 3AI ?\", jamais juste \"classe 3AI\".\n"
    "4. Les noms propres et acronymes (AWS, CCNA, Marateck, ESPRIT...) ne se "
    "traduisent JAMAIS et ne se remplacent JAMAIS par un mot générique -- s'ils "
    "n'ont pas de sens clair pour toi, recopie-les tels quels plutôt que de "
    "deviner un autre mot à la place.\n\n"
    "Utilise TOUJOURS le vocabulaire administratif exact utilisé à ESPRIT "
    "plutôt qu'une traduction littérale ou approximative -- une mauvaise "
    "terminologie fait ensuite échouer la recherche dans la base de "
    "connaissances. Lexique de référence :\n"
    "شهادة حضور / وثيقة حضور -> attestation de présence\n"
    "شهادة نجاح -> attestation de réussite\n"
    "كشف نقاط / كشف الأعداد -> relevé de notes\n"
    "مصاريف الدراسة / معاليم -> frais de scolarité\n"
    "تسجيل -> inscription\n"
    "وثيقة / وثائق -> document(s) (PAS \"attestation\" -- une wathiqa administrative "
    "generale est un document, pas forcement une attestation)\n"
    "قسط -> tranche\n"
    "شهادة -> attestation ou certificat (selon contexte administratif ESPRIT)\n"
    "بانييه / البانييه -> panier (unité d'enseignement, terme du programme d'études ESPRIT)\n"
    "ماتيار / الماتيار -> matière(s)\n"
    "أوبسيون -> option (de spécialisation)\n"
    "اختصاص / اختصاصات -> spécialité / spécialités (PAS \"option\" -- une \"spécialité\" "
    "et une \"option\" sont deux niveaux différents à ESPRIT : spécialité = filière "
    "d'ingénieur, ex. Génie Informatique ; option = sous-spécialisation en 3A/3B)\n"
    "سكور -> score\n"
    "قسم (suivi d'un code comme 3A, 3B, 3AI) -> classe (garder le code tel quel, ex. \"قسم 3AI\" -> \"classe 3AI\") "
    "-- mais voir la règle absolue n°2 ci-dessus : sans code explicite, ne pas en inventer un\n"
    "قسم تحضيري -> classe préparatoire\n"
    "التوجيه -> orientation\n"
    "المعدل -> la moyenne\n"
    "الاختيار / بالاختيار -> le choix / par choix\n"
    "فوروم توظيف / فوروم الشركات -> forum entreprises (forum de recrutement organisé par l'école)\n"
    "نخلص / نخلص المعلوم -> payer / régler les frais de scolarité (نخلص = payer en dialecte tunisien, PAS \"terminer\")\n"
    "المعلوم -> les frais (de scolarité)\n"
    "برا تونس / وأنا برا تونس -> depuis l'étranger / en étant hors de Tunisie\n"
    "دروس استدراك / دروس تدارك -> cours de soutien (cours de rattrapage en cas de difficulté)\n"
    "قداش -> combien (mot tunisien très courant, JAMAIS \"exempté\" ou autre sens)\n"
    "يتحمل (une absence/un nombre) -> tolère / supporte\n"
    "غياب / غيابات -> absence(s)\n"
    "عقوبة -> sanction\n"
    "رسوب / الرسوب -> redoublement, échec (PAS \"retard\")\n"
    "نادي / نوادي / كلوب / كلوبات -> club / clubs (associations étudiantes)\n"
    "التنقل الدولي -> mobilité internationale (PAS \"passeport\")\n"
    "الماراتيك -> Marateck (nom propre : hackathon de programmation organisé à ESPRIT -- ne jamais traduire ce mot)\n"
    "إخوة -> frères et sœurs (fratrie)\n"
    "تخفيض -> réduction\n\n"
    "Attention : ne traduis JAMAIS mot à mot un verbe dialectal tunisien qui ressemble à un "
    "autre mot de l'arabe standard (ex. نخلص vient de la racine خلص qui veut dire \"finir\" en "
    "arabe standard, mais en tunisien نخلص signifie \"payer/régler\" -- utilise TOUJOURS le sens "
    "tunisien dans ce contexte administratif). Si le sens t'échappe, garde la traduction la plus "
    "littérale possible plutôt que d'inventer un sens proche mais différent."
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
            # temperature=0 : une traduction n'est pas une tache creative,
            # le tirage aleatoire par defaut (voir generator.py) a deja
            # produit une traduction qui melangeait un vrai texte traduit
            # avec une fausse remarque "il n'y a pas d'information
            # disponible" (hallucination du modele de traduction lui-meme,
            # constate en usage reel sur un nom propre anglais integre a
            # une phrase arabe) -- viser systematiquement le mot le plus
            # probable reduit ce risque et rend la traduction reproductible.
            options={"num_predict": 150, "temperature": 0},
        )
        translated = response["message"]["content"].strip()
        return translated or text
    except Exception:
        return text


# Marqueurs lexicaux tres caracteristiques du tunisien (dialecte), absents
# ou rares en arabe standard (fusha) -- ex. "قداش" (combien) au lieu de
# "كم", "شنو" (quoi) au lieu de "ماذا", "باهي" (d'accord/bien), "فما" (il y
# a) au lieu de "يوجد"... Liste volontairement courte et haute-confiance :
# mieux vaut classer "fusha" par defaut sur une phrase ambigue que
# sur-detecter le tunisien avec des mots communs aux deux registres.
_TOUNSI_MARKERS = [
    "قداش", "شنو", "شنية", "شنوة", "علاش", "كيفاش", "وقتاش", "فما", "فمة",
    "برشة", "ياسر", "توا", "الوقتي", "باهي", "زعمة", "نجم", "يجم", "نجمو",
    "موش", "مانيش", "ماهوش", "زوز", "برا", "عندي", "حاجة", "نحكي", "نحب",
    "خويا", "وختي", "معلش", "إسبري",
]
_TOUNSI_MARKER_RE = re.compile("|".join(_TOUNSI_MARKERS))


def detect_text_language(text: str) -> str:
    """Classe un texte ecrit en "fr" / "ar_fusha" / "ar_tounsi" -- utilise
    pour journaliser automatiquement la langue des questions posees en
    conditions reelles (voir extraction_app/services/quality_test.py::
    append_live_result). Heuristique par mots-cles, PAS une vraie detection
    de dialecte (qui n'existe pas de facon fiable pour du texte court) :
    fr/arabe est fiable (script different), mais fusha/tounsi est une
    estimation approximative assumee comme telle -- l'admin peut corriger
    en le voyant sur /qualite si besoin."""
    if not contains_arabic(text):
        return "fr"
    return "ar_tounsi" if _TOUNSI_MARKER_RE.search(text) else "ar_fusha"
