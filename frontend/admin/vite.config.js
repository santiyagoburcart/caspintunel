import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const hosts = (process.env.ALLOWED_HOSTS || '')
  .split(',').map((s) => s.trim()).filter(Boolean)
const domain = process.env.DOMAIN
const allowedHosts = hosts.length
  ? [...new Set([...hosts, ...(domain ? [`.${domain}`] : [])])]
  : true

export default defineConfig({
  plugins: [react()],
  // VITE_BASE is only set for the preview build (scripts/preview.sh → /preview-panel/)
  base: process.env.VITE_BASE || '/panel/',
  server: {
    port: 5174,
    allowedHosts,
    proxy: {
      '/api': { target: process.env.API_TARGET || 'http://web:8000', changeOrigin: true },
      '/media': { target: process.env.API_TARGET || 'http://web:8000', changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist', sourcemap: false,
    // 3D illustrations stay separate files (loaded only where shown), never
    // base64-inlined into the JS bundle
    assetsInlineLimit: (file) => (file.endsWith('.webp') ? false : undefined),
  },
})
