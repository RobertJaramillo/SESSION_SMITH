import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// With VITE_USE_MOCKS=false, keep the browser on one origin during local
// development and forward API requests to FastAPI (port 8000 by default).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/v1": {
        target: process.env.VITE_API_PROXY_TARGET ?? "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      // Google OAuth login/callback + session endpoints (backend/auth.py).
      // Proxied for the same reason as /v1: keeps the session cookie on one
      // origin (this Vite server) instead of splitting it across :5173/:8000.
      '/auth': {
        target: process.env.VITE_API_PROXY_TARGET ?? 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
});
