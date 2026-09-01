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
  base: '/panel/',
  server: {
    port: 5174,
    allowedHosts,
    proxy: {
      '/api': { target: process.env.API_TARGET || 'http://web:8000', changeOrigin: true },
      '/media': { target: process.env.API_TARGET || 'http://web:8000', changeOrigin: true },
    },
  },
  build: { outDir: 'dist', sourcemap: false },
})
