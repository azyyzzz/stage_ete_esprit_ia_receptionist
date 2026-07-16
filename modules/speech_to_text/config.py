"""
Configuration du module de reconnaissance vocale (Speech-to-Text).
"""

# Taille du modele faster-whisper. "medium" donne une meilleure qualite sur
# l'arabe tunisien que "small", au prix d'une transcription plus lente.
MODEL_SIZE = "medium"

# CPU + quantification int8 : evite un conflit de VRAM avec Ollama (module
# RAG) sur une carte graphique a VRAM limitee (4 Go).
DEVICE = "cpu"
COMPUTE_TYPE = "int8"

# Frequence d'echantillonnage attendue par Whisper.
SAMPLE_RATE = 16000

# Vocabulaire du domaine (ESPRIT) + tournures courantes en arabe tunisien,
# pour biaiser le decodage vers les mots attendus. N'apprend pas le dialecte
# a Whisper, mais reduit certaines erreurs sur des termes specifiques
# (noms propres, vocabulaire admissions/scolarite) -- gratuit, sans
# changement de modele. Voir modules/speech_to_text/README.md.
INITIAL_PROMPT = (
    "ESPRIT، تسجيل، مصاريف، قسط، أقساط، دراسة، امتحان، شهادة، تكوين، "
    "باش، نجم، فما، برشة، فلوس، "
    "ESPRIT, inscription, admission, frais de scolarité, tranche, "
    "semestre, cours du soir, cours du jour, stage, EMBA."
)
