# Image de extraction_app (interface d'administration/extraction de la base
# de connaissances, port 8001). Construite depuis la RACINE du projet (le
# code importe modules/rag/ pour la dedup semantique) -- voir docker-compose.yml.

FROM python:3.13-slim

# tesseract-ocr + le pack de langue francaise : necessaires a l'OCR des PDF
# scannes et des images (voir extraction_app/services/pdf_extractor.py,
# image_extractor.py) -- remplace le dossier tessdata/ gitignore utilise en
# local sous Windows, pytesseract detecte automatiquement le binaire/pack
# systeme (voir _ensure_tesseract_configured()).
# curl : sonde de sante du conteneur.
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-fra curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUTF8=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY modules/ modules/
COPY extraction_app/ extraction_app/
COPY data/ data/

# extraction_app/data/ (identifiants, historique, registres...) et
# extraction_app/uploads/ (fichiers uploades) sont des volumes persistants
# (voir docker-compose.yml) -- sinon un mot de passe admin different serait
# regenere a chaque redemarrage du conteneur.
VOLUME ["/app/extraction_app/data", "/app/extraction_app/uploads"]

EXPOSE 8001

CMD ["python", "-m", "uvicorn", "extraction_app.main:app", "--host", "0.0.0.0", "--port", "8001"]
