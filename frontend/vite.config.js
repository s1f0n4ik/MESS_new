import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const API_TARGET = process.env.VITE_API_PROXY_TARGET || 'http://backend:8787'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    allowedHosts: true,
    hmr: {
      host: '192.168.88.116',
      protocol: 'ws',
      clientPort: 5173,
    },
    proxy: {
      '/api':  { target: API_TARGET, changeOrigin: true },
      '/pdfs': { target: API_TARGET, changeOrigin: true },
      '/ws':   { target: API_TARGET, changeOrigin: true, ws: true },
    },
  },
})