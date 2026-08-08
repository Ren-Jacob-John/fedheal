import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// FedHeal — Federation Map
// Dev server runs on 5173 by default; the FastAPI services (Module 1 on
// 8001, Module 7 on 8005) already open CORS to "*", so no proxy is
// required — see src/api.js for how the base URLs are configured.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
  },
});
