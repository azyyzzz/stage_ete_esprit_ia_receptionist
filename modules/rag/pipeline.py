"""
Point d'entrée unique du module RAG : reçoit une question, renvoie une
réponse. C'est cette fonction que les futurs modules (API REST, module de
compréhension) appelleront.
"""

from __future__ import annotations

import re

from modules.rag.config import PROGRAMME_AMBIGUITY_MARGIN, SCORE_THRESHOLD, TOP_K
from modules.rag.fallback import get_fallback_message
from modules.rag.generator import generate_answer
from modules.rag.nlu import detect_classe_mention, detect_option_mention, detect_specialite_tunis_mention, is_list_all_intent
from modules.rag.nlu import is_count_intent, is_list_options_intent, is_list_specialites_intent
from modules.rag.programmes import CAMPUS_LABELS, PROGRAMME_KEYWORDS, mentioned_programme, programme_label
from modules.rag.retriever import retrieve, retrieve_all
from modules.rag.translate import contains_arabic, translate_to_french


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
    labels_per_chunk = [programme_label(c.metadata.get("source", ""), c.metadata.get("titre", "")) for c in top]
    if sum(1 for label in labels_per_chunk if label) < len(top) // 2 + 1:
        return set()

    best_score = chunks[0].score
    labels = set()
    for chunk in chunks:
        if chunk.score < best_score - PROGRAMME_AMBIGUITY_MARGIN:
            continue
        label = programme_label(chunk.metadata.get("source", ""), chunk.metadata.get("titre", ""))
        if label:
            labels.add(label)
    return labels


# Une annee universitaire s'ecrit "20XX-20XX" ou "20XX/20XX" avec exactement
# UNE annee d'ecart (ex. 2024/2025) -- un intervalle plus large (ex.
# "2018-2025" dans le titre d'un historique multi-annees) n'est PAS une
# annee precise mais un ensemble deja exhaustif, jamais ambigu par
# construction (voir _annee_label ci-dessous, qui l'exclut explicitement).
_ANNEE_RE = re.compile(r"\b(20\d{2})[-/](20\d{2})\b")


def _annee_label(titre: str) -> str | None:
    """Renvoie l'annee universitaire precise mentionnee dans le titre d'une
    fiche (ex. "2024/2025"), ou None si le titre n'en mentionne aucune, en
    mentionne plusieurs (titre ambigu en lui-meme -- mieux vaut ne rien
    affirmer que deviner), ou mentionne un intervalle de plusieurs annees
    (fiche "historique", deliberement exhaustive plutot que specifique a une
    seule annee -- ex. "Historique des frais de scolarite ... 2018-2025")."""
    matches = _ANNEE_RE.findall(titre)
    precises = [f"{y1}/{y2}" for y1, y2 in matches if int(y2) - int(y1) == 1]
    return precises[0] if len(precises) == 1 else None


def _ambiguous_annees(chunks: list) -> set[str]:
    """Meme principe que _ambiguous_programmes (fiches concurrentes a la
    marge de score pres), mais SANS le garde-fou de consensus sur le
    top-3 : une fiche specifique a une annee (ex. "... pour l'annee
    2025/2026 ?") est un contenu rare dans la base (une poignee de fiches
    au total, contre des dizaines par programme) -- exiger qu'une MAJORITE
    du top-3 soit deja specifique a une annee ne laisserait quasiment
    jamais passer la detection, meme quand deux fiches d'annees
    differentes sont clairement concurrentes un peu plus bas dans le
    classement (constate en usage reel : une fiche "historique"
    generaliste, jamais specifique a une annee par construction, domine
    systematiquement le top-3 sans jamais etre elle-meme ambigue). Le
    filtre par marge de score ci-dessous (memes fiches candidates que
    _ambiguous_programmes) suffit a ecarter les cas hors-sujet : une fiche
    specifique a une annee n'apparait jamais avec un bon score sur une
    question sans rapport avec les frais/l'inscription."""
    best_score = chunks[0].score
    annees = set()
    for chunk in chunks:
        if chunk.score < best_score - PROGRAMME_AMBIGUITY_MARGIN:
            continue
        label = _annee_label(chunk.metadata.get("titre", ""))
        if label:
            annees.add(label)
    return annees


def _mentioned_annee(question: str, candidates: set[str]) -> str | None:
    """Si la question mentionne explicitement l'une des annees candidates
    (et une seule), la renvoie -- sinon None. Exige la paire complete
    (ex. "2025-2026" ou "2025/2026"), pas juste l'un des deux nombres seuls :
    "2025" a lui seul apparait a la fois dans "2024/2025" et "2025/2026",
    le mentionner seul ne leve donc pas l'ambiguite."""
    q_norm = re.sub(r"[-/]", "/", question)
    matches = [annee for annee in candidates if annee in q_norm]
    return matches[0] if len(matches) == 1 else None


def _extract_panier_label(chunk) -> str:
    titre = chunk.metadata.get("titre", "")
    if "—" in titre:
        return titre.split("—")[-1].strip() or titre.strip()
    return titre.strip()


def _extract_panier_details(content: str) -> str:
    import re

    content = re.sub(r"^Programme d'étude\s+—\s+.+?\s*:\s*", "", content, flags=re.IGNORECASE | re.DOTALL)
    marker = re.search(r"l['’]unité d['’]enseignement", content, flags=re.IGNORECASE)
    if marker:
        content = content[marker.start():]
    match = re.search(
        r"comprend(?: les)?(?: mati[èe]res suivantes)?[:\s]*(.*?)(?:Total ECTS(?: de ce panier)?|$)",
        content,
        flags=re.IGNORECASE | re.DOTALL,
    )
    details = match.group(1).strip() if match else content.strip()
    details = re.sub(r"\s+", " ", details)
    return details.rstrip(" ;.")


def _build_exhaustive_answer(classe: str, chunks: list) -> str:
    lines = [f"Pour la classe {classe}, tu dois valider les paniers suivants :"]
    seen_panier = set()

    for chunk in chunks:
        panier = _extract_panier_label(chunk)
        panier_lower = panier.lower()
        if "liste complète des matières" in panier_lower or "liste complete des matieres" in panier_lower:
            continue
        if not panier or panier in seen_panier:
            continue
        seen_panier.add(panier)
        details = _extract_panier_details(chunk.content)
        if details:
            lines.append(f"Le panier « {panier} » contient : {details}.")
        else:
            lines.append(f"Le panier « {panier} » est listé dans le programme de la classe {classe}.")

    return " ".join(lines)


def _specialites_names(chunks: list) -> list[str]:
    seen: set[str] = set()
    names: list[str] = []
    for chunk in chunks:
        titre = chunk.metadata.get("titre", "")
        nom = titre.split("—")[0].strip() if "—" in titre else titre.strip()
        if not nom or nom in seen or nom.lower().startswith(("présentation", "presentation")):
            continue
        seen.add(nom)
        names.append(nom)
    return names


def _build_specialites_answer(campus: str, chunks: list) -> str:
    names = _specialites_names(chunks)
    display_name = CAMPUS_DISPLAY_NAMES.get(campus, campus)
    if not names:
        return f"Je n'ai pas trouvé de liste détaillée des spécialités pour {display_name}."
    lines = [f"Les spécialités proposées par {display_name} sont :"]
    lines.extend(f"- {nom}" for nom in names)
    return "\n".join(lines)



# Libelle interne (programmes.py, utilise pour le filtre metadonnee "campus")
# -> nom d'ecole naturel a afficher dans la reponse.
CAMPUS_DISPLAY_NAMES: dict[str, str] = {
    "ESPRIT Tunis": "ESPRIT Tunis",
    "Campus Monastir": "ESPRIT Monastir (ESPRIM)",
    "Classe préparatoire (PREPA)": "ESPRIT Prépa",
}


def _build_all_specialites_answer(chunks_by_campus: dict[str, list]) -> str:
    """Question generique ("quelles specialites propose ESPRIT ?") sans
    campus precise : ESPRIT est une marque qui recouvre 3 ecoles distinctes
    (Tunis, Monastir, Prepa) -- la reponse complete et correcte liste donc
    les specialites de CHACUNE, regroupees par ecole, plutot que de risquer
    une recherche par similarite noyee parmi du contenu sans rapport (voir
    l'incident constate : contexte domine par des fiches "mission/valeurs"
    et des extraits de PDF de programme, aucune fiche de specialite dans le
    top 5)."""
    lines = ["Voici les spécialités proposées par ESPRIT, selon l'école :"]
    for campus, chunks in chunks_by_campus.items():
        names = _specialites_names(chunks)
        if not names:
            continue
        campus = CAMPUS_DISPLAY_NAMES.get(campus, campus)
        lines.append(f"\n{campus} :")
        lines.extend(f"- {nom}" for nom in names)
    return "\n".join(lines)


def _build_options_answer(specialite: str, chunks: list) -> str:
    names: list[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        titre = chunk.metadata.get("titre", "")
        nom = titre.split("—")[0].strip() if "—" in titre else titre.strip()
        if nom.lower().startswith("option "):
            nom = nom[len("option "):].strip()
        if not nom or nom in seen:
            continue
        seen.add(nom)
        names.append(nom)

    if not names:
        return f"Je n'ai pas trouvé de liste détaillée des options pour {specialite}."
    lines = [f"Les options de spécialisation pour {specialite} (ESPRIT Tunis) sont :"]
    lines.extend(f"- {nom}" for nom in names)
    return "\n".join(lines)


def answer_question(question: str, allow_clarification: bool = True, structured: bool = False) -> dict:
    """
    allow_clarification=False : ne renvoie jamais de demande de precision --
    utilise pour les canaux a un seul aller-retour (ex. /api/converse en
    vocal) ou l'appelant n'a pas moyen de repondre a une question de
    clarification. Le LLM synthetise alors une reponse couvrant les
    principaux programmes a partir du meme contexte recupere.
    """
    # Question contenant de l'arabe : traduite en francais AVANT toute
    # recherche/detection d'intention -- la base et les motifs de
    # nlu.py/programmes.py sont presque entierement en francais, donc une
    # question en arabe pur ou melangee matche nettement moins bien qu'une
    # question equivalente en francais (voir modules/rag/translate.py).
    # `question` (traduite) sert a TOUTE la logique interne ci-dessous ;
    # `original_question` (jamais modifiee) est celle transmise au LLM pour
    # qu'il reponde dans la langue effectivement utilisee par l'appelant.
    original_question = question
    if contains_arabic(question):
        question = translate_to_french(question)

    # Question "quelles sont les options de <specialite> ?" : meme logique
    # que la liste des specialites par campus (ci-dessous), un niveau en
    # dessous -- recupere TOUTES les fiches "Options" de la specialite
    # mentionnee (metadonnee "option_specialite", voir ingest.py) plutot que
    # de se limiter a TOP_K, qui n'en remonterait qu'une partie (constate en
    # usage reel : "options de Genie Civil" ne remontait que 1 option sur 3).
    if is_list_options_intent(question):
        specialite = detect_specialite_tunis_mention(question)
        if specialite:
            option_chunks = retrieve_all(question, where={"option_specialite": specialite})
            if option_chunks:
                return {
                    "answer": _build_options_answer(specialite, option_chunks),
                    "sources": [
                        {"titre": c.metadata.get("titre", ""), "source": c.metadata.get("source", ""), "score": round(c.score, 3)}
                        for c in option_chunks
                    ],
                    "used_fallback": False,
                    "needs_clarification": False,
                }

    # Question sur UNE option precise ("c'est quoi les modules de l'option X
    # en 4eme annee en specialite Y ?") : pas une liste exhaustive (pas
    # traite ci-dessus), mais la specialite EST mentionnee -- on restreint
    # quand meme la recherche par similarite aux fiches "Options" de CETTE
    # specialite uniquement (metadonnee "option_specialite"). Sans ce filtre,
    # deux options au nom quasi identique dans des specialites differentes
    # (ex. "Data Analytics & Science" a Informatique vs "... Telecom" a
    # Telecom) se font concurrence dans le TOP_K et la mauvaise peut
    # l'emporter -- constate en usage reel.
    elif "option" in question.lower():
        specialite = detect_specialite_tunis_mention(question)
        # Si la specialite n'est pas nommee explicitement, essaie de la
        # deduire du nom d'option lui-meme (ex. "l'option Data Analytics and
        # Science" sans dire "informatique") -- peut renvoyer PLUSIEURS
        # specialites si le meme nom d'option existe dans plusieurs d'entre
        # elles (voir nlu.detect_option_mention).
        candidates = [specialite] if specialite else detect_option_mention(question)

        if len(candidates) == 1:
            option_chunks = retrieve(question, where={"option_specialite": candidates[0]})
            if option_chunks:
                answer = generate_answer(original_question, option_chunks)
                return {
                    "answer": answer,
                    "sources": [
                        {"titre": c.metadata.get("titre", ""), "source": c.metadata.get("source", ""), "score": round(c.score, 3)}
                        for c in option_chunks
                    ],
                    "used_fallback": False,
                    "needs_clarification": False,
                }
        elif len(candidates) > 1:
            # Le meme nom d'option existe dans plusieurs specialites (ex.
            # "Data Analytics & Science" en Informatique ET en Telecom) --
            # recupere les fiches "Options" des DEUX, le LLM distingue via
            # le titre de chaque extrait (voir AMBIGUOUS_PROGRAMME_NOTE).
            combined_chunks = [
                c for cand in candidates for c in retrieve(question, where={"option_specialite": cand})
            ]
            if combined_chunks:
                answer = generate_answer(original_question, combined_chunks, ambiguous_programme=True)
                return {
                    "answer": answer,
                    "sources": [
                        {"titre": c.metadata.get("titre", ""), "source": c.metadata.get("source", ""), "score": round(c.score, 3)}
                        for c in combined_chunks
                    ],
                    "used_fallback": False,
                    "needs_clarification": False,
                }

    # Question "quelles specialites propose ESPRIT <campus> ?" : le campus
    # est deja identifie sans ambiguite (mot-cle explicite), donc on
    # recupere TOUTES les fiches "Programmes" de ce campus (metadonnee
    # "campus", voir ingest.py) plutot que de se limiter a TOP_K -- sinon
    # une liste de 4 specialites peut se retrouver noyee parmi des fiches
    # sans rapport (ex. FAQ, autres programmes) et la reponse est
    # incomplete alors que la donnee existe bien dans la base.
    if is_list_specialites_intent(question):
        campus = mentioned_programme(question, CAMPUS_LABELS)
        if campus:
            campus_chunks = retrieve_all(question, where={"campus": campus})
            if campus_chunks:
                return {
                    "answer": _build_specialites_answer(campus, campus_chunks),
                    "sources": [
                        {"titre": c.metadata.get("titre", ""), "source": c.metadata.get("source", ""), "score": round(c.score, 3)}
                        for c in campus_chunks
                    ],
                    "used_fallback": False,
                    "needs_clarification": False,
                }
        else:
            # Aucun campus precise ("ESPRIT" tout court) : ESPRIT recouvre 3
            # ecoles distinctes, chacune avec ses propres specialites -- on
            # les recupere toutes plutot que de laisser une recherche par
            # similarite generique manquer les fiches de specialites (voir
            # docstring de _build_all_specialites_answer).
            chunks_by_campus = {c: retrieve_all(question, where={"campus": c}) for c in CAMPUS_LABELS}
            all_chunks = [c for chunks in chunks_by_campus.values() for c in chunks]
            if all_chunks:
                return {
                    "answer": _build_all_specialites_answer(chunks_by_campus),
                    "sources": [
                        {"titre": c.metadata.get("titre", ""), "source": c.metadata.get("source", ""), "score": round(c.score, 3)}
                        for c in all_chunks
                    ],
                    "used_fallback": False,
                    "needs_clarification": False,
                }

    # Detection de classe (programme d'etude) : filtre la recherche par
    # metadonnee plutot que de compter uniquement sur l'embedding, qui
    # confond facilement deux classes voisines (ex. "4 ERP-BI" / "5 ERP-BI",
    # signal distinctif = un seul chiffre). Ne s'applique que si une SEULE
    # classe est reconnue sans ambiguite (voir nlu.detect_classe_mention) --
    # sinon comportement inchange (pas de clarification demandee).
    classe = detect_classe_mention(question)
    list_all = False
    count_intent = is_count_intent(question)
    # Pool plus large que le TOP_K normal (5), utilise UNIQUEMENT pour
    # detecter une ambiguite programme/annee (_ambiguous_programmes,
    # _ambiguous_annees ci-dessous) -- jamais pour construire la reponse
    # elle-meme (qui continue a n'utiliser que les 5 meilleures, via
    # `chunks`). Constate en usage reel : une fiche specifique a une annee
    # (ex. "... pour l'annee 2025/2026 ?") peut se classer 6e ou 7e,
    # juste sous le TOP_K=5, concurrencee par une fiche "historique"
    # generaliste qui score mieux mais ne permet jamais de detecter
    # l'ambiguite (une fiche multi-annees n'est pas specifique a UNE
    # annee, voir _annee_label) -- sans ce pool elargi, l'ambiguite passe
    # inapercue et le LLM choisit une annee au hasard sans le signaler.
    AMBIGUITY_TOP_K = 10
    ambiguity_pool: list = []
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
        ambiguity_pool = retrieve(question, top_k=AMBIGUITY_TOP_K)
        chunks = ambiguity_pool[:TOP_K]

    if classe and not chunks:
        # Filet de securite : ne devrait pas arriver (la classe vient de la
        # base connue), mais si le filtre ne renvoie rien, on retombe sur la
        # recherche globale plutot que de renvoyer un fallback a tort.
        ambiguity_pool = retrieve(question, top_k=AMBIGUITY_TOP_K)
        chunks = ambiguity_pool[:TOP_K]

    if not ambiguity_pool:
        ambiguity_pool = chunks

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

    programmes = _ambiguous_programmes(ambiguity_pool)
    # Verifie aussi contre TOUS les programmes connus, pas seulement ceux
    # detectes dans ce top_k precis : la recherche peut rester "confuse"
    # (rester dominee par un autre programme) meme apres que l'appelant a
    # explicitement precise le sien en reponse a une premiere demande de
    # clarification (ex. "(cours du jour)" ajoute a la question, mais le
    # cours du jour ne remonte toujours pas dans le top 3) -- sans ce
    # filet, mentioned_programme(question, programmes) renverrait None
    # (le programme mentionne n'etant pas dans l'ensemble ambigu detecte)
    # et redemanderait indefiniment la meme precision (constate en usage
    # reel). Des que l'appelant nomme explicitement UN programme connu, on
    # fait confiance a son intention plutot qu'au classement de la
    # recherche.
    is_ambiguous = len(programmes) >= 2 and not (
        mentioned_programme(question, programmes) or mentioned_programme(question, set(PROGRAMME_KEYWORDS.keys()))
    )

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

    # Meme logique que ci-dessus, sur l'axe "annee universitaire" plutot que
    # "programme" -- verifiee SEULEMENT si le programme n'est pas (ou plus)
    # ambigu : un prix qui differe a la fois par programme ET par annee est
    # d'abord desambiguise sur le programme (axe le plus large), l'annee
    # etant reverifiee au tour suivant une fois le programme precise (voir
    # commentaire ci-dessus sur le filet contre la reclarification infinie,
    # meme raison ici).
    annees = _ambiguous_annees(ambiguity_pool)
    is_annee_ambiguous = len(annees) >= 2 and not _mentioned_annee(question, annees)

    if is_annee_ambiguous and allow_clarification:
        options = ", ".join(sorted(annees))
        return {
            "answer": (
                "Cette information dépend de l'année universitaire concernée. "
                f"Pouvez-vous préciser laquelle vous intéresse : {options} ?"
            ),
            "sources": [],
            "used_fallback": False,
            "needs_clarification": True,
        }

    if count_intent and not list_all:
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
        if not list_all:
            return {
                "answer": f"Il y a {count} matières dans le programme {classe}.",
                "sources": [
                    {"titre": c.metadata.get("titre", ""), "source": c.metadata.get("source", ""), "score": round(c.score, 3)}
                    for c in chunks
                ],
                "used_fallback": False,
                "needs_clarification": False,
            }

    if list_all and classe:
        answer = _build_exhaustive_answer(classe, chunks)
        return {
            "answer": answer,
            "sources": [
                {"titre": c.metadata.get("titre", ""), "source": c.metadata.get("source", ""), "score": round(c.score, 3)}
                for c in chunks
            ],
            "used_fallback": False,
            "needs_clarification": False,
        }

    answer = generate_answer(
        original_question, chunks, ambiguous_programme=is_ambiguous, ambiguous_annee=is_annee_ambiguous, list_all=list_all
    )
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
