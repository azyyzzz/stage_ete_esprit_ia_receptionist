"""
Configuration centrale du module RAG (génération de réponses).

Regroupe tous les chemins et paramètres ici pour que le reste du module
(ingest.py, retriever.py, generator.py...) n'ait jamais de valeur codée en
dur ailleurs.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Base de connaissances utilisée pour le retrieval : fiches de contenu
# nettoyées (titre + contenu), pas les paires Q/R pré-générées. Voir le
# plan d'implémentation pour la justification de ce choix.
KNOWLEDGE_BASE_PATH = PROJECT_ROOT / "data" / "processed" / "site_esprit_clean.json"

# Dossier de persistance de la base vectorielle ChromaDB (gitignored).
VECTOR_STORE_DIR = PROJECT_ROOT / "vector_store"
COLLECTION_NAME = "esprit_knowledge_base"

# Modèle d'embeddings multilingue (français + arabe), local via
# sentence-transformers.
EMBEDDING_MODEL_NAME = "paraphrase-multilingual-mpnet-base-v2"

# Nombre de fiches récupérées par recherche, et seuil de similarité en
# dessous duquel on considère qu'aucune fiche n'est vraiment pertinente
# (déclenche le message de redirection vers un service humain).
TOP_K = 5
SCORE_THRESHOLD = 0.45

# Marge de score en dessous du meilleur resultat : les fiches dans cette
# marge sont considerees aussi pertinentes que la meilleure (et non filtrees
# par un seuil absolu), pour detecter correctement quand plusieurs
# programmes se disputent la meilleure reponse.
PROGRAMME_AMBIGUITY_MARGIN = 0.08

# Modèle LLM local (via Ollama) utilisé pour générer la réponse finale à
# partir du contexte récupéré. Solution 100% gratuite : aucune clé API,
# tourne entièrement sur la machine. Qwen2.5 a été choisi pour son bon
# support multilingue (français + arabe) parmi les modèles open-source.
OLLAMA_MODEL = "qwen2.5:7b-instruct"
OLLAMA_MAX_TOKENS = 500
