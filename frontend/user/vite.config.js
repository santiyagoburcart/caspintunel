import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev: proxy API + Django static/media to the backend container.
// allowedHosts comes from the ALLOWED_HOSTS env (same var Django uses); a
// leading-dot entry is added so sub-domains of the site domain are allowed too.
const hosts = (process.env.ALLOWED_HOSTS || '')
  .split(',').map((s) => s.trim()).filter(Boolean)
const domain = process.env.DOMAIN
const allowedHosts = hosts.length
  ? [...new Set([...hosts, ...(domain ? [`.${domain}`] : [])])]
  : true

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    allowedHosts,
    proxy: {
      '/api': { target: process.env.API_TARGET || 'http://web:8000', changeOrigin: true },
      '/media': { target: process.env.API_TARGET || 'http://web:8000', changeOrigin: true },
    },
  },
  build: { outDir: 'dist', sourcemap: false },
})
