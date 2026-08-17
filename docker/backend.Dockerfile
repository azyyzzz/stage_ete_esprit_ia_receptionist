# Image du backend principal (API RAG texte + vocal, port 8000).
# Construite depuis la RACINE du projet (contexte = ".") car le code
# importe des modules partages (modules/) situes hors du dossier backend/ --
# voir docker-compose.yml (build.context: .).

FROM python:3.13-slim

# libsndfile1 : lecture/ecriture audio (soundfile, STT).
# espeak-ng : phonemisation utilisee par Piper (TTS) pour le francais/l'arabe.
# ffmpeg : decodage de formats audio divers en entree de faster-whisper.
# curl : sonde de sante du conteneur (docker-compose healthcheck).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 espeak-ng ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

# PYTHONUTF8=1 : evite le bug d'encodage console (cp1252) rencontre sous
# Windows en local -- inoffensif ici (Linux est deja en UTF-8), mais garde
# pour la coherence avec le code (voir backend/main.py).
ENV PYTHONUTF8=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code partage + backend uniquement -- pas extraction_app/ ni dashboard/,
# qui ont leurs propres images (voir docker-compose.yml).
COPY modules/ modules/
COPY backend/ backend/
COPY data/ data/
COPY docker/backend-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# vector_store/ et voice_models/ sont des volumes (voir docker-compose.yml) :
# regeneres/retelecharges au premier demarrage par l'entrypoint plutot que
# copies dans l'image, comme en local (gitignores, potentiellement lourds).
VOLUME ["/app/vector_store", "/app/voice_models"]

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
