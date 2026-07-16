# Module de détection de langue

Statut : fonctionnel.

Rôle : détecter si l'audio entrant est en français ou en arabe, avant de
router vers le bon pipeline de reconnaissance vocale et de génération de
réponse.

Réutilise le modèle Whisper chargé par `modules/speech_to_text/model.py`
(pas de modèle séparé) : un appel léger sur un court échantillon audio, sans
transcrire tout le fichier.

## Utilisation

```python
from modules.language_detection.detect import detect_language

result = detect_language("chemin/vers/audio.wav")
# {"language": "fr", "probability": 0.97}
```

## Limite connue

Whisper distingue les langues (codes ISO), pas les dialectes : l'arabe
tunisien est détecté comme "ar" (arabe), sans distinction avec l'arabe
standard. Suffisant pour router français / arabe, pas pour identifier
finement le dialecte.
