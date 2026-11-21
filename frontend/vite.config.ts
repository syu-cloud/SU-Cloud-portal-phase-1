import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: {
      // 브라우저의 Host/Origin을 유지해 Django의 CSRF 검사를 그대로 적용한다.
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: false },
    },
  },
})
