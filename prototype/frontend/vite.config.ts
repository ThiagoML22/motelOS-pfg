import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Variables de entorno de Node sin depender de @types/node.
const entorno = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env ?? {}

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    // En Docker Desktop sobre Windows la carpeta montada no avisa los cambios de archivos: con
    // VITE_USE_POLLING=true (docker-compose.yml) el servidor de desarrollo los detecta por sondeo.
    watch: entorno.VITE_USE_POLLING === 'true' ? { usePolling: true, interval: 500 } : undefined,
  },
})
