"""
Harnais de test manuel pour les modules language_detection et
speech_to_text : enregistre quelques secondes au micro, détecte la langue
puis transcrit.

Prérequis : un microphone fonctionnel. Testable en français, puis en arabe
tunisien, pour comparer la qualité.

Lancement :
    python -m tests.test_stt_pipeline
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import sounddevice as sd
import soundfile as sf

from modules.language_detection.detect import detect_language
from modules.speech_to_text.config import SAMPLE_RATE
from modules.speech_to_text.transcribe import transcribe

RECORD_SECONDS = 5


def record_to_wav() -> Path:
    print(f"Enregistrement de {RECORD_SECONDS} secondes... parlez maintenant.")
    audio = sd.rec(int(RECORD_SECONDS * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1)
    sd.wait()
    print("Enregistrement termine.")

    tmp_path = Path(tempfile.gettempdir()) / "esprit_stt_test.wav"
    sf.write(tmp_path, audio, SAMPLE_RATE)
    return tmp_path


def main() -> None:
    print("Test des modules langue + reconnaissance vocale (Ctrl+C pour quitter)\n")
    while True:
        try:
            input(f"Appuyez sur Entree pour enregistrer {RECORD_SECONDS}s au micro...")
        except (KeyboardInterrupt, EOFError):
            print("\nFin du test.")
            break

        audio_path = record_to_wav()

        lang_result = detect_language(audio_path)
        print(f"\nLangue detectee : {lang_result['language']} (probabilite={lang_result['probability']:.2f})")

        stt_result = transcribe(audio_path)
        print(f"Transcription : {stt_result['text']}\n")


if __name__ == "__main__":
    main()
