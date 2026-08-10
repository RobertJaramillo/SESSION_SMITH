import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// With VITE_USE_MOCKS=false, keep the browser on one origin during local
// development and forward API requests to FastAPI (port 8000 by default).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/v1': {
        target: process.env.VITE_API_PROXY_TARGET ?? 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
});
