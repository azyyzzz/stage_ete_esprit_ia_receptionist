"""
Protocole de test structuré pour évaluer la qualité du pipeline vocal en
arabe tunisien (dialecte) par rapport au français, sur une série de sujets
représentatifs de la base de connaissances ESPRIT.

Contrairement à tests/test_stt_pipeline.py (test libre, un enregistrement à
la fois), ce script guide l'utilisateur à travers une liste fixe de sujets,
enregistre chaque réponse, l'enchaîne dans le RAG, et sauvegarde un rapport
complet (JSON) pour analyse a posteriori -- plutôt que de juger au cas par
cas pendant l'enregistrement.

Lancement :
    python -m tests.test_language_quality
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime
from pathlib import Path

import sounddevice as sd
import soundfile as sf

from modules.language_detection.detect import detect_language
from modules.rag.pipeline import answer_question
from modules.speech_to_text.config import SAMPLE_RATE
from modules.speech_to_text.transcribe import transcribe

RECORD_SECONDS = 7
OUTPUT_PATH = Path.home() / "Desktop" / "test_arabe_resultats.json"

# Sujets couvrant les principales categories de la base de connaissances.
# Le libelle francais indique QUOI demander -- a poser a l'oral en dialecte
# tunisien, dans les mots naturels de la personne qui parle (pas a lire
# mot pour mot).
SCENARIOS = [
    ("admission", "Comment s'inscrire à ESPRIT ?"),
    ("frais_soir", "Quels sont les frais pour les cours du soir ?"),
    ("paiement", "Peut-on payer les frais de scolarité en plusieurs fois ?"),
    ("calendrier", "Quand commence le prochain semestre ?"),
    ("stage", "Qui contacter pour le département des stages ?"),
    ("documents", "Quels documents faut-il pour s'inscrire ?"),
    ("contact_general", "Comment contacter la réception d'ESPRIT ?"),
    ("hors_sujet", "Une question sans rapport avec ESPRIT (ex : la météo)"),
]


def record_to_wav() -> Path:
    print(f"Enregistrement de {RECORD_SECONDS}s... parlez maintenant.")
    audio = sd.rec(int(RECORD_SECONDS * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1)
    sd.wait()
    print("Termine.")
    tmp_path = Path(tempfile.gettempdir()) / "test_language_quality.wav"
    sf.write(tmp_path, audio, SAMPLE_RATE)
    return tmp_path


def main() -> None:
    print("Test qualite arabe tunisien vs francais -- ", len(SCENARIOS), "sujets.\n")
    print("Pour chaque sujet, pose la question en arabe tunisien (dialecte),")
    print("dans tes propres mots. Ctrl+C a tout moment pour arreter.\n")

    results = []
    for label, prompt_fr in SCENARIOS:
        print(f"\n--- Sujet : {label} ---")
        print(f"A poser (sens) : {prompt_fr}")
        try:
            input("Appuie sur Entree pour enregistrer...")
        except (KeyboardInterrupt, EOFError):
            print("\nArret demande.")
            break

        audio_path = record_to_wav()
        lang_result = detect_language(audio_path)
        stt_result = transcribe(audio_path)
        question = stt_result["text"]
        rag_result = answer_question(question) if question.strip() else None

        print(f"Langue detectee   : {lang_result['language']} ({lang_result['probability']:.2f})")
        print(f"Transcription     : {question}")
        if rag_result:
            print(f"Reponse generee   : {rag_result['answer']}")

        results.append(
            {
                "sujet": label,
                "attendu_fr": prompt_fr,
                "langue_detectee": lang_result["language"],
                "confiance_langue": round(lang_result["probability"], 3),
                "transcription": question,
                "reponse_rag": rag_result["answer"] if rag_result else None,
                "used_fallback": rag_result["used_fallback"] if rag_result else None,
                "needs_clarification": rag_result["needs_clarification"] if rag_result else None,
            }
        )

    report = {"date": datetime.now().isoformat(timespec="seconds"), "resultats": results}
    OUTPUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nRapport sauvegarde : {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
