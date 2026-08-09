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
#
# Inclut aussi des PHRASES d'exemple qui melangent arabe et francais dans la
# meme phrase (code-switching), pas seulement une liste de mots isoles --
# Whisper utilise ce texte comme contexte precedent pour orienter son
# decodage, donc lui montrer le STYLE attendu (alternance de langue au sein
# d'une meme phrase, comme parle vraiment un appelant tunisien) aide plus
# qu'un simple lexique a lui faire accepter ce melange plutot que de forcer
# toute la phrase dans une seule langue.
INITIAL_PROMPT = (
    "ESPRIT، تسجيل، مصاريف، قسط، أقساط، دراسة، امتحان، شهادة، تكوين، "
    "باش، نجم، فما، برشة، فلوس، "
    "ESPRIT, inscription, admission, frais de scolarité, tranche, "
    "semestre, cours du soir, cours du jour, stage, EMBA. "
    "شني هي les frais متاع l'inscription في ESPRIT؟ "
    "نحب نعرف la tranche الأولى متاع frais de scolarité. "
    "قداش تكلف l'inscription في cycle préparatoire؟ "
    "واش فما remise لل étudiants الجداد؟"
)
