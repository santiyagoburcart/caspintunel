import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev: proxy API + Django static/media to the backend container.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: process.env.API_TARGET || 'http://web:8000', changeOrigin: true },
      '/media': { target: process.env.API_TARGET || 'http://web:8000', changeOrigin: true },
    },
  },
  build: { outDir: 'dist', sourcemap: false },
})
