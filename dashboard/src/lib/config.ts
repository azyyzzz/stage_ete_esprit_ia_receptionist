// URLs des deux APIs backend existantes -- surchargeables via variables
// d'environnement Vite (.env.local) pour un deploiement hors localhost,
// sans jamais toucher au code. Par defaut : les ports utilises partout
// ailleurs dans le projet (voir README.md racine, scripts/start_services.ps1).
export const BACKEND_URL: string = import.meta.env.VITE_BACKEND_URL ?? "http://127.0.0.1:8000";
export const EXTRACTION_APP_URL: string = import.meta.env.VITE_EXTRACTION_APP_URL ?? "http://127.0.0.1:8001";
