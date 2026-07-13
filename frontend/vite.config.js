import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev server on 5173 (matches backend CORS defaults). `host: true` so the
// container-published port works in Docker (Step 5).
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
  },
})
