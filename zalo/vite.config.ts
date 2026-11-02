import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import zaloMiniApp from 'zmp-vite-plugin'

export default defineConfig({
  base: '',
  plugins: [zaloMiniApp(), react()],
  build: { outDir: 'www', emptyOutDir: true, assetsInlineLimit: 0, target: 'es2020' },
  server: {
    port: 3000,
    // Dev trên trình duyệt: gọi API qua proxy, token Zalo giả lập (TMS_ZALO_MOCK ở backend).
    proxy: {
      '/api': process.env.TMS_API_PROXY ?? 'http://localhost:8000',
      '/tiles': 'http://localhost:58080',
    },
  },
})
