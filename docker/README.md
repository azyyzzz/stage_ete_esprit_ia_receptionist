# Docker

Statut : fonctionnel, pensé pour lancer tout le projet localement en une
commande (démo/confort), pas pour un vrai déploiement en production
(pas de gestion de secrets, HTTPS, durcissement sécurité...).

## Démarrage

Depuis la racine du projet :

```powershell
docker compose up --build
```

Premier démarrage : plus long que les suivants (téléchargement du modèle
Ollama ~5 Go, indexation de la base de connaissances, téléchargement des
voix Piper) -- compter plusieurs minutes selon la connexion. Les démarrages
suivants sont rapides (tout est conservé dans des volumes Docker).

Une fois lancé :
- Dashboard : http://localhost:5173
- API backend : http://localhost:8000/docs
- Extraction/admin : http://localhost:8001 (identifiants générés au premier
  lancement -- **regarder les logs du conteneur `extraction_app`
  immédiatement**, ils ne sont affichés qu'une seule fois :
  `docker compose logs extraction_app | grep -A3 "Identifiants"`)

## Prérequis GPU (accélération d'Ollama)

Le service `ollama` est configuré pour utiliser un GPU NVIDIA (bien plus
rapide qu'en CPU pur pour un modèle 7B). Ça suppose :
- Docker Desktop en mode WSL2 (Windows) avec un GPU NVIDIA + pilotes à jour
  (le support GPU dans WSL2 est géré directement par Docker Desktop sur les
  installations récentes, pas besoin d'installer le NVIDIA Container Toolkit
  séparément dans la plupart des cas).
- Vérifier que ça fonctionne : `docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi`
  doit afficher le GPU.

**Pas de GPU disponible, ou la configuration échoue ?** Supprimer le bloc
`deploy:` du service `ollama` dans `docker-compose.yml` -- Ollama tourne
alors en CPU (fonctionnel, mais nettement plus lent, quelques dizaines de
secondes par réponse au lieu de quelques secondes).

## Ce qui est persistant (volumes Docker)

| Volume | Contenu | Pourquoi |
|---|---|---|
| `ollama_data` | Modèles Ollama téléchargés | Éviter de re-télécharger ~5 Go à chaque démarrage |
| `vector_store` | Base vectorielle ChromaDB | Éviter de ré-indexer ~1000 fiches à chaque démarrage |
| `voice_models` | Voix Piper (TTS) | Éviter de re-télécharger à chaque démarrage |
| `extraction_data` | Identifiants admin, historique, registres | Sinon un nouveau mot de passe admin serait généré à chaque redémarrage |
| `extraction_uploads` | Fichiers uploadés via l'interface admin | Persistance des documents source |

Le dossier `data/` (base de connaissances JSON, versionnée dans git) est
monté directement depuis l'hôte (`./data:/app/data`) plutôt que copié dans
l'image : une modification faite depuis `extraction_app` ou directement sur
le disque est immédiatement visible sans reconstruire les images.

## Commandes utiles

```powershell
# Tout arrêter (garde les volumes -- redémarrage rapide ensuite)
docker compose down

# Tout arrêter ET supprimer les volumes (repart de zéro -- re-téléchargement complet)
docker compose down -v

# Logs d'un service en particulier
docker compose logs -f backend

# Reconstruire un seul service après une modification du code
docker compose up --build backend

# Forcer une ré-indexation de la base vectorielle (ex. apres avoir modifie
# data/processed/site_esprit_clean.json directement) sans tout redemarrer
docker compose exec backend python -m modules.rag.ingest
```

## Limites connues

- Le dashboard tourne en mode développement (`vite --host`), pas un vrai
  build de production servi par nginx -- suffisant pour une démo, pas pour
  un déploiement réel. Un changement de code dans `dashboard/` nécessite un
  `docker compose up --build dashboard` (pas de rechargement à chaud comme
  en local avec `npm run dev`).
- Aucune gestion HTTPS/reverse proxy -- les 3 ports (5173/8000/8001) sont
  exposés directement, comme en local.
- `/api/converse` (canal audio-vers-audio) n'est pas testé dans ce contexte
  conteneurisé au-delà d'un test manuel de base -- pas de suite de tests
  automatisés dédiée.
