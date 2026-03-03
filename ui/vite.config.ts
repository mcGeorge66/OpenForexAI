import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // Proxy all API calls to the FastAPI backend during dev
      '/agents': 'http://127.0.0.1:8765',
      '/health': 'http://127.0.0.1:8765',
      '/version': 'http://127.0.0.1:8765',
      '/metrics': 'http://127.0.0.1:8765',
      '/routing': 'http://127.0.0.1:8765',
      '/events': 'http://127.0.0.1:8765',
      '/monitoring': 'http://127.0.0.1:8765',
      '/indicators': 'http://127.0.0.1:8765',
      '/tools': 'http://127.0.0.1:8765',
      '/config': 'http://127.0.0.1:8765',
      '/runtime': 'http://127.0.0.1:8765',
      '/ws': {
        target: 'ws://127.0.0.1:8765',
        ws: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
