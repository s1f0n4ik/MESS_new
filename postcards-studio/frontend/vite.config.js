import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8081',
      '/assets': 'http://127.0.0.1:8081',
      '/ws': { target: 'ws://127.0.0.1:8081', ws: true },
      '/collaboration': { target: 'ws://127.0.0.1:1234', ws: true },
    },
  },
})
