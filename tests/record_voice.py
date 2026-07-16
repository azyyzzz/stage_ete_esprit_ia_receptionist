"""Enregistre quelques secondes au micro et sauvegarde un fichier .wav sur
le Bureau, sans rien transcrire -- pour enregistrer separement puis tester
ensuite via /docs (POST /api/transcribe).

Lancement :
    python -m tests.record_voice
"""

from pathlib import Path

import sounddevice as sd
import soundfile as sf

SAMPLE_RATE = 16000
RECORD_SECONDS = 6
OUTPUT_PATH = Path.home() / "Desktop" / "test_voix.wav"


def main() -> None:
    input(f"Appuie sur Entree puis parle pendant {RECORD_SECONDS} secondes...")
    print("Enregistrement en cours...")
    audio = sd.rec(int(RECORD_SECONDS * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1)
    sd.wait()
    print("Termine.")

    sf.write(OUTPUT_PATH, audio, SAMPLE_RATE)
    print(f"Fichier sauvegarde ici : {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
