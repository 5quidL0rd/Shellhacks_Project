import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The API runs separately (backend/: uvicorn app.main:app). In development,
// /api/* is forwarded to it, so the browser talks to one origin.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: process.env.API_URL ?? 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
