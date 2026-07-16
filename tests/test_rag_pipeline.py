"""
Harnais de test manuel pour le pipeline RAG : pose une question, affiche les
fiches récupérées et la réponse générée. Sert à valider le module avant de
le brancher sur les futurs modules voix (STT/TTS).

Prérequis : avoir lancé `python -m modules.rag.ingest` au moins une fois, et
Ollama démarré avec le modèle configuré dans modules/rag/config.py
(`ollama pull qwen2.5:7b-instruct`).

Lancement :
    python -m tests.test_rag_pipeline
"""

from modules.rag.pipeline import answer_question


def main() -> None:
    print("Test du pipeline RAG ESPRIT AI Receptionist (Ctrl+C pour quitter)\n")
    while True:
        try:
            question = input("Question : ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nFin du test.")
            break
        if not question:
            continue

        result = answer_question(question)

        print(f"\nRéponse : {result['answer']}")
        if result["used_fallback"]:
            print("(redirection vers un service humain, aucune fiche pertinente trouvee)")
        else:
            print("\nSources utilisees :")
            for source in result["sources"]:
                print(f"  - {source['titre']} (score={source['score']})")
        print()


if __name__ == "__main__":
    main()
