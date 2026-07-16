"""
Configuration du module de synthèse vocale (Text-to-Speech).
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Modeles de voix Piper (telecharges via `python -m piper.download_voices`,
# voir README.md du module), gitignores car volumineux.
VOICE_MODELS_DIR = PROJECT_ROOT / "voice_models"

# Voix francaise utilisee pour la synthese. Tunisien dialectal non
# disponible chez Piper : voir README.md pour la limite connue.
VOICE_MODEL_NAME = "fr_FR-siwis-medium"
VOICE_MODEL_PATH = VOICE_MODELS_DIR / f"{VOICE_MODEL_NAME}.onnx"

# Multiplicateur de duree de la parole : 1.0 = vitesse par defaut du modele,
# plus eleve = plus lent. Augmente car la voix par defaut parlait trop vite
# pour un appelant au telephone.
SPEECH_LENGTH_SCALE = 1.25
