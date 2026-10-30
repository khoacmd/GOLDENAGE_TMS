import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    // Gọi API qua proxy để tránh CORS khi dev.
    // /tiles: bản đồ tự host (service `tiles` trong infra/docker-compose.yml).
    proxy: { '/api': 'http://localhost:8000', '/tiles': 'http://localhost:58080' },
  },
})
