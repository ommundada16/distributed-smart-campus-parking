import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Dev-time proxy so the frontend can call /api/... and /ws without CORS
// or hardcoding the gateway's host — mirrors how it would sit behind a
// single origin in production.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
})
