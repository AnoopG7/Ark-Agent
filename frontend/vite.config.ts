import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// During development the dashboard talks to the FastAPI backend through this proxy,
// so the browser only ever sees one origin (same as behind nginx in Docker).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Mermaid (graph tab) is loaded lazily; its layout engines are large but never on the main path.
  build: { chunkSizeWarningLimit: 1600 },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: process.env.VITE_API_TARGET ?? 'http://localhost:8000', changeOrigin: true },
    },
  },
})
