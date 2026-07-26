"""
Point d'entrée unique du module RAG : reçoit une question, renvoie une
réponse. C'est cette fonction que les futurs modules (API REST, module de
compréhension) appelleront.
"""

from __future__ import annotations

from modules.rag.config import PROGRAMME_AMBIGUITY_MARGIN, SCORE_THRESHOLD
from modules.rag.fallback import get_fallback_message
from modules.rag.generator import generate_answer
from modules.rag.nlu import detect_classe_mention, is_list_all_intent
from modules.rag.nlu import is_count_intent
from modules.rag.programmes import mentioned_programme, programme_label
from modules.rag.retriever import retrieve, retrieve_all


TOP_N_FOR_CONSENSUS = 3


def _ambiguous_programmes(chunks: list) -> set[str]:
    """Programmes distincts (cours du jour, EMBA...) representes parmi les
    fiches aussi pertinentes que la meilleure (a la marge pres) -- si plus
    d'un, la question est ambigue (ne precise pas de quel programme il
    s'agit).

    Ne se declenche que si une MAJORITE des meilleurs resultats (pas
    seulement le tout premier) sont deja specifiques a un programme : se fier
    au seul chunks[0] est fragile, un ecart de score de 0.001 entre deux
    fiches (bruit d'embedding) suffit a faire basculer un cas non-ambigu
    (ex. question generale sur un service -- stages, carriere...) en fausse
    alerte. Le consensus sur le top N est plus robuste a ce bruit."""
    top = chunks[:TOP_N_FOR_CONSENSUS]
    labels_per_chunk = [programme_label(c.metadata.get("source", "")) for c in top]
    if sum(1 for label in labels_per_chunk if label) < len(top) // 2 + 1:
        return set()

    best_score = chunks[0].score
    labels = set()
    for chunk in chunks:
        if chunk.score < best_score - PROGRAMME_AMBIGUITY_MARGIN:
            continue
        label = programme_label(chunk.metadata.get("source", ""))
        if label:
            labels.add(label)
    return labels


def answer_question(question: str, allow_clarification: bool = True, structured: bool = False) -> dict:
    """
    allow_clarification=False : ne renvoie jamais de demande de precision --
    utilise pour les canaux a un seul aller-retour (ex. /api/converse en
    vocal) ou l'appelant n'a pas moyen de repondre a une question de
    clarification. Le LLM synthetise alors une reponse couvrant les
    principaux programmes a partir du meme contexte recupere.
    """
    # Detection de classe (programme d'etude) : filtre la recherche par
    # metadonnee plutot que de compter uniquement sur l'embedding, qui
    # confond facilement deux classes voisines (ex. "4 ERP-BI" / "5 ERP-BI",
    # signal distinctif = un seul chiffre). Ne s'applique que si une SEULE
    # classe est reconnue sans ambiguite (voir nlu.detect_classe_mention) --
    # sinon comportement inchange (pas de clarification demandee).
    classe = detect_classe_mention(question)
    list_all = False
    count_intent = is_count_intent(question)
    if classe and is_list_all_intent(question):
        list_all = True
        chunks = retrieve_all(question, where={"classe": classe})
    elif classe and count_intent:
        # For counting, retrieve all fiches for the class to compute an accurate total
        list_all = True
        chunks = retrieve_all(question, where={"classe": classe})
    elif classe:
        chunks = retrieve(question, where={"classe": classe})
    else:
        chunks = retrieve(question)

    if classe and not chunks:
        # Filet de securite : ne devrait pas arriver (la classe vient de la
        # base connue), mais si le filtre ne renvoie rien, on retombe sur la
        # recherche globale plutot que de renvoyer un fallback a tort.
        chunks = retrieve(question)

    best_score = chunks[0].score if chunks else 0.0

    # Le seuil de score ne s'applique pas quand list_all est actif : la
    # classe a deja ete identifiee de facon sure et symbolique (nom de
    # classe reconnu, pas une similarite floue), donc les fiches recuperees
    # sont pertinentes par construction. Une question de comparaison/liste
    # ("quel panier a le plus d'ECTS ?") ne "ressemble" a aucune fiche en
    # particulier -- chaque fiche individuelle score alors normalement en
    # dessous du seuil (constate : ~0.43 vs seuil 0.45) sans que ce ne soit
    # un signe de hors-sujet, contrairement au cas general.
    if not chunks or (not list_all and best_score < SCORE_THRESHOLD):
        return {
            "answer": get_fallback_message(question),
            "sources": [],
            "used_fallback": True,
            "needs_clarification": False,
        }

    programmes = _ambiguous_programmes(chunks)
    is_ambiguous = len(programmes) >= 2 and not mentioned_programme(question, programmes)

    if is_ambiguous and allow_clarification:
        options = ", ".join(sorted(programmes))
        return {
            "answer": (
                "Cette information dépend du programme concerné. "
                f"Pouvez-vous préciser lequel vous intéresse : {options} ?"
            ),
            "sources": [],
            "used_fallback": False,
            "needs_clarification": True,
        }

    answer = generate_answer(question, chunks, ambiguous_programme=is_ambiguous, list_all=list_all)
    # If the user asked for a count only (no explicit 'list' intent), compute a conservative unique-module count
    if count_intent:
        import re
        modules = set()

        for c in chunks:
            text = c.content
            # remove parenthesis content to avoid splitting inside (21h, ...)
            text_no_paren = re.sub(r"\([^)]*\)", "", text)

            # try to extract the list area between known markers
            m = re.search(r"comprend(?: les)?(?: unit[eéi]s d'enseignement| les matieres suivantes)[:\s]*(.*?)(?:Total ECTS|Total ECTS de ce panier|Total ECTS|$)", text_no_paren, flags=re.IGNORECASE | re.DOTALL)
            if m:
                part = m.group(1)
            else:
                # fallback: take after first ':' if present, but strip trailing phrases
                parts = text_no_paren.split(':', 1)
                part = parts[1] if len(parts) > 1 else text_no_paren
                part = re.sub(r"Total ECTS.*$", "", part, flags=re.IGNORECASE)

            # split by semicolon first (primary separator), then by line breaks
            items = re.split(r";|\n", part)
            for it in items:
                # further split by ' - ' or ' / ' or ', ' but avoid splitting short phrases
                subitems = re.split(r",\s+|/| - ", it)
                for si in subitems:
                    item = si.strip()
                    # remove leftover connectors like 'et' at the start/end
                    item = re.sub(r"^et\s+|\s+et$", "", item, flags=re.IGNORECASE).strip()
                    if len(item) > 2 and not re.search(r"^Total ECTS|ECTS$|^Total$", item, flags=re.IGNORECASE):
                        # normalize internal whitespace
                        item = re.sub(r"\s+", " ", item)
                        modules.add(item)

        count = len(modules)
        if count == 0:
            count = len(chunks)

        # If the user only asked for the count (no list intent), return concise answer
        if not is_list_all_intent(question):
            return {
                "answer": f"Il y a {count} matières dans le programme {classe}.",
                "sources": [
                    {"titre": c.metadata.get("titre", ""), "source": c.metadata.get("source", ""), "score": round(c.score, 3)}
                    for c in chunks
                ],
                "used_fallback": False,
                "needs_clarification": False,
            }
    result = {
        "answer": answer,
        "sources": [
            {"titre": c.metadata.get("titre", ""), "source": c.metadata.get("source", ""), "score": round(c.score, 3)}
            for c in chunks
        ],
        "used_fallback": False,
        "needs_clarification": False,
    }

    # If structured output requested and we retrieved multiple chunks, build modules grouped by panier
    if structured and chunks:
        import re

        modules_by_panier = []
        seen_panier = set()
        for c in chunks:
            # derive panier label from metadata titre (last part after '—')
            titre = c.metadata.get("titre", "")
            panier = titre.split("—")[-1].strip() if "—" in titre else titre
            if panier in seen_panier:
                continue
            seen_panier.add(panier)

            text = c.content
            text_no_paren = re.sub(r"\([^)]*\)", "", text)
            m = re.search(r"comprend(?: les)?(?: unit[eéi]s d'enseignement| les matieres suivantes)[:\s]*(.*?)(?:Total ECTS|Total ECTS de ce panier|Total ECTS|$)", text_no_paren, flags=re.IGNORECASE | re.DOTALL)
            if m:
                part = m.group(1)
            else:
                parts = text_no_paren.split(':', 1)
                part = parts[1] if len(parts) > 1 else text_no_paren
                part = re.sub(r"Total ECTS.*$", "", part, flags=re.IGNORECASE)

            items = re.split(r";|\n", part)
            matieres = []
            for it in items:
                subitems = re.split(r",\s+|/| - ", it)
                for si in subitems:
                    item = si.strip()
                    item = re.sub(r"^et\s+|\s+et$", "", item, flags=re.IGNORECASE).strip()
                    if len(item) > 2 and not re.search(r"^Total ECTS|ECTS$|^Total$", item, flags=re.IGNORECASE):
                        item = re.sub(r"\s+", " ", item)
                        if item not in matieres:
                            matieres.append(item)

            modules_by_panier.append({"panier": panier or titre, "matieres": matieres})

        result["modules"] = modules_by_panier

    return result
