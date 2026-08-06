# Frontend — ESPRIT AI Receptionist

Frontend public de démo/test de l'assistant, plus un point d'entrée vers
l'espace admin (`extraction_app`, port 8001). Stack : React + TypeScript +
Vite + Tailwind CSS.

Ne contient **aucune logique métier** : c'est une interface pure au-dessus
des deux APIs FastAPI déjà existantes (`backend/`, `extraction_app/`).

## Ce que ça fait

- **Démo texte** (`/`) : pose une question à l'assistant, reçoit la réponse
  générée par le RAG avec ses sources — appelle `POST /api/ask` du backend.
- **Démo voix** (`/`, onglet Voix) : enregistre une question au micro,
  affiche la transcription + la réponse texte, puis synthétise et joue la
  réponse à l'oral — enchaîne `POST /api/voice-ask` puis `POST /api/speak`.
- **Espace admin** (`/admin`) : ne recrée AUCUNE authentification — un
  simple lien vers `extraction_app` (port 8001), qui a déjà tout
  (compte unique, session cookie, voir `extraction_app/auth.py`). Une
  navigation classique suffit, le cookie de session est géré nativement par
  le navigateur une fois connecté là-bas.

## Pourquoi pas de proxy/SSO entre les deux apps

`extraction_app` reste une application FastAPI + Jinja2 totalement séparée,
sur son propre port, avec sa propre session. Ce frontend ne fait que
naviguer vers elle (lien `<a href>`) plutôt que d'essayer de dupliquer ou de
faire transiter son authentification — plus simple, rien à synchroniser,
zéro risque de désynchronisation entre deux systèmes d'auth.

## Lancement

```bash
cd dashboard
npm install
npm run dev
```

Ouvre <http://localhost:5173> — nécessite que `backend` (port 8000) tourne
pour que la démo fonctionne (voir README.md à la racine). `extraction_app`
(port 8001) n'est nécessaire que pour l'espace admin.

Build de production :

```bash
npm run build      # -> dashboard/dist/
npm run preview    # sert le build sur http://localhost:4173
```

## Configuration

Les URLs des deux APIs sont surchargeables sans toucher au code, via
`.env.local` (copier `.env.example`) :

```
VITE_BACKEND_URL=http://127.0.0.1:8000
VITE_EXTRACTION_APP_URL=http://127.0.0.1:8001
```

## CORS

`backend/main.py` autorise explicitement les origines `localhost:5173`
(dev) et `localhost:4173` (preview) via `CORSMiddleware` — à étendre si le
frontend est un jour déployé sur un autre domaine. `extraction_app` n'a
besoin d'aucun CORS : le frontend ne lui fait jamais d'appel `fetch`
cross-origin, seulement des navigations classiques (voir `src/pages/Admin.tsx`).

## Système de design

Direction "Signal" : fond quasi-noir (`ink`), rouge signal (`signal`, clin
d'œil au rouge ESPRIT sans copier son identité visuelle) pour les actions
principales, cyan électrique (`volt`) pour tout ce qui touche à la voix/IA
en action. Typographies Sora (titres) + Inter (texte) + JetBrains Mono
(sources, statuts techniques). Palette et tokens dans `tailwind.config.js`.

## Arborescence

```
src/
  main.tsx, App.tsx        point d'entree + routage (react-router-dom)
  index.css                 Tailwind + classes utilitaires (.glass-panel, .btn-primary...)
  lib/
    config.ts                URLs des deux APIs (surchargeables via .env.local)
    api.ts                    client typé pour backend:8000 (ask, voiceAsk, converse, speak)
    useRecorder.ts             hook d'enregistrement micro (MediaRecorder)
  components/
    Layout.tsx                nav + footer + indicateur d'état backend
    Logo.tsx, GlowBackground.tsx
    ChatDemo.tsx               démo texte
    VoiceDemo.tsx              démo voix
  pages/
    Home.tsx                   landing + bascule Texte/Voix
    Admin.tsx                   point d'entrée vers extraction_app
```
