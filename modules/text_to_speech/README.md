# Module de synthèse vocale (Text-to-Speech)

Statut : fonctionnel (texte -> audio, français uniquement).

Rôle : transformer la réponse générée par le RAG en voix, pour que
l'appelant entende une réponse parlée plutôt qu'un texte.

Basé sur [Piper](https://github.com/OHF-Voice/piper1-gpl), 100% local et
gratuit (synthèse neuronale via ONNX Runtime, aucune clé API).

## Installation de la voix

Le modèle de voix n'est pas versionné (fichier binaire volumineux, voir
`.gitignore`). À télécharger une seule fois :

```
python -m piper.download_voices fr_FR-siwis-medium --download-dir voice_models
```

## Utilisation

```python
from pathlib import Path
from modules.text_to_speech.synthesize import synthesize_to_wav

synthesize_to_wav("Bonjour, bienvenue à ESPRIT.", Path("reponse.wav"))
```

## Limite connue

Aucune voix arabe tunisienne (dialecte) disponible chez Piper -- seulement
de l'arabe standard moderne, avec un rendu qui ne correspondra pas à
l'accent tunisien. Le module reste donc français uniquement pour l'instant,
comme les autres modules du pipeline vocal (même limite que
`speech_to_text` sur l'arabe tunisien, dans l'autre sens).
