#!/bin/sh
# Prepare les donnees qui vivent dans des volumes persistants (vector_store,
# voice_models) au premier demarrage du conteneur, avant de lancer l'API --
# ces dossiers sont gitignores localement (regenerables/retelechargeables),
# donc absents d'un volume Docker fraichement cree.
set -e

if [ ! -f /app/vector_store/chroma.sqlite3 ]; then
    echo "[entrypoint] Base vectorielle absente -- indexation initiale (peut prendre plusieurs minutes)..."
    python -m modules.rag.ingest
else
    echo "[entrypoint] Base vectorielle deja presente, indexation ignoree."
fi

if [ ! -f /app/voice_models/fr_FR-siwis-medium.onnx ] || [ ! -f /app/voice_models/ar_JO-kareem-medium.onnx ]; then
    echo "[entrypoint] Voix Piper manquantes -- telechargement..."
    python -m piper.download_voices fr_FR-siwis-medium --download-dir /app/voice_models
    python -m piper.download_voices ar_JO-kareem-medium --download-dir /app/voice_models
else
    echo "[entrypoint] Voix Piper deja presentes, telechargement ignore."
fi

exec "$@"
