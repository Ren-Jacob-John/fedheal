import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// FedHeal — Federation Map
// Dev server runs on 5173 by default. The FastAPI services (Module 1 on
// 8001, Module 7 on 8005) allow this origin via FEDHEAL_DASHBOARD_ORIGIN
// (defaults to http://localhost:5173, matching this port) — see
// src/api.js for how the base URLs are configured, and each module's
// README for how to set FEDHEAL_DASHBOARD_ORIGIN for a non-default port
// or a deployed origin.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
  },
});
