import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [tailwindcss(), react()],
  server: {
    port: 5175,
    proxy: {
      '/api/auth': {
        target: 'http://localhost:8006',
        rewrite: (path) => path.replace(/^\/api\/auth/, ''),
      },
      '/api/wallet': {
        target: 'http://localhost:8003',
        rewrite: (path) => path.replace(/^\/api\/wallet/, ''),
      },
      '/api': {
        target: 'http://localhost:8000',
      },
    },
  },
})
