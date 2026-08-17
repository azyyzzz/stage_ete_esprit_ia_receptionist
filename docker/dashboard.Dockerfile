# Image du dashboard React (port 5173). Contexte de build = dashboard/ (voir
# docker-compose.yml) -- ce Dockerfile ne depend d'aucun autre dossier du
# projet, contrairement a backend/extraction_app.
#
# Lance le serveur de dev Vite (pas un build de production servi par nginx) :
# priorite donnee au confort de lancement local/demo (un seul `docker-compose
# up`), pas a un vrai deploiement -- voir docker/README.md.

FROM node:20-slim

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .

EXPOSE 5173

# --host 0.0.0.0 : surcharge le `host: "127.0.0.1"` de vite.config.ts (voulu
# pour l'usage local direct hors Docker) sans toucher au fichier -- sinon le
# port publie par Docker ne repondrait jamais (127.0.0.1 dans le conteneur
# n'est joignable que depuis l'interieur du conteneur lui-meme).
CMD ["npx", "vite", "--host", "0.0.0.0", "--port", "5173"]
