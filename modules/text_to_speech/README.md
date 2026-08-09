# Module de synthèse vocale (Text-to-Speech)

Statut : fonctionnel (texte -> audio, français ou arabe -- voix choisie
automatiquement selon le script dominant du texte).

Rôle : transformer la réponse générée par le RAG en voix, pour que
l'appelant entende une réponse parlée plutôt qu'un texte.

Basé sur [Piper](https://github.com/OHF-Voice/piper1-gpl), 100% local et
gratuit (synthèse neuronale via ONNX Runtime, aucune clé API).

## Installation de la voix

Le modèle de voix n'est pas versionné (fichier binaire volumineux, voir
`.gitignore`). À télécharger une seule fois :

```
python -m piper.download_voices fr_FR-siwis-medium --download-dir voice_models
python -m piper.download_voices ar_JO-kareem-medium --download-dir voice_models
```

## Utilisation

```python
from pathlib import Path
from modules.text_to_speech.synthesize import synthesize_to_wav

synthesize_to_wav("Bonjour, bienvenue à ESPRIT.", Path("reponse.wav"))  # voix FR
synthesize_to_wav("مرحبا بكم في ESPRIT.", Path("reponse_ar.wav"))  # voix AR
```

`synthesize_to_wav` choisit automatiquement la voix (`modules/text_to_speech/
synthesize.py::_is_mostly_arabic`) en comptant le ratio de lettres en script
arabe dans le texte -- pas une vraie detection de langue, un simple
comptage de script Unicode, suffisant puisque l'appelant n'utilise que le
francais, l'arabe, ou un melange des deux (voir `modules/rag/generator.py`).
Pour un texte majoritairement melange, la voix choisie est celle de la
langue dominante -- les mots de l'autre langue dans le texte restant seront
lus (mal) avec cette voix, aucune segmentation phrase par phrase n'est
faite.

## Limite connue

Aucune voix arabe tunisienne (dialecte) disponible chez Piper -- seulement
de l'arabe standard **jordanien** (`ar_JO-kareem-medium`), avec un rendu et
un accent qui ne correspondront pas au tunisien. Avant ce choix de voix
automatique, un texte en arabe etait toujours lu avec la voix francaise :
aucune erreur technique (le fichier audio se generait normalement), mais un
son incomprehensible -- une voix francaise prononcant phonetiquement de
l'arabe. Meme limite que `speech_to_text` sur l'arabe tunisien, dans
l'autre sens.
