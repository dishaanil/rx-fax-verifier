import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const projectDirectory = fileURLToPath(new URL('.', import.meta.url))

export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://127.0.0.1:8000', '/faxes': 'http://127.0.0.1:8000', '/processed': 'http://127.0.0.1:8000' } },
  // Serve the backend-owned contract fixture directly; do not duplicate it in the UI.
  publicDir: resolve(projectDirectory, '../fixtures'),
})
