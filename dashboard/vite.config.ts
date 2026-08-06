import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Frontend public de demo + point d'entree admin pour ESPRIT AI Receptionist.
// Parle directement a backend:8000 (RAG texte + voix, voir src/lib/api.ts) et
// renvoie vers extraction_app:8001 pour l'espace admin (auth Jinja2/cookie
// deja existante, reutilisee telle quelle -- voir src/pages/Admin.tsx).
export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1", // coherent avec backend/extraction_app (uvicorn, 127.0.0.1 explicite) -- par defaut Vite peut se lier a ::1 (IPv6) seul, non joignable via 127.0.0.1
    port: 5173,
    strictPort: true,
  },
});
