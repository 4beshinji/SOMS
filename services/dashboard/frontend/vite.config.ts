import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { copyFileSync, mkdirSync, existsSync } from 'fs'
import { dirname, join } from 'path'
import { createRequire } from 'module'
import { mockApiPlugin } from './dev-mocks'

// Copy VAD + ONNX Runtime assets to public/vad/ so Vite serves them
const require = createRequire(import.meta.url)
const vadDist = join(dirname(require.resolve('@ricky0123/vad-web')), '..', 'dist')
const vadRequire = createRequire(require.resolve('@ricky0123/vad-web'))
const ortDist = dirname(vadRequire.resolve('onnxruntime-web'))

const vadPublic = join(import.meta.dirname!, 'public', 'vad')
if (!existsSync(vadPublic)) mkdirSync(vadPublic, { recursive: true })
for (const [dir, file] of [
  [vadDist, 'silero_vad_v5.onnx'],
  [vadDist, 'vad.worklet.bundle.min.js'],
  [ortDist, 'ort-wasm-simd-threaded.wasm'],
  [ortDist, 'ort-wasm-simd-threaded.mjs'],
] as const) {
  const src = join(dir, file)
  const dst = join(vadPublic, file)
  if (existsSync(src) && !existsSync(dst)) copyFileSync(src, dst)
}

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    mockApiPlugin(),  // Dev-only API mocks; remove to use real backend via proxy below
    react(),
    tailwindcss(),
  ],
  server: {
    host: true, // Needed for Docker
    port: 5173,
    watch: {
      usePolling: true
    },
    proxy: {
      '/api/auth': {
        target: 'http://localhost:8006',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/auth/, ''),
      },
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    }
  }
})
