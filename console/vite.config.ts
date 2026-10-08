import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  base: '/console/',
  plugins: [react(), tailwindcss()],
  build: { sourcemap: false },
  server: { proxy: { '/console/api': 'http://127.0.0.1:3001' } },
  test: { environment: 'jsdom', include: ['src/**/*.test.tsx'], restoreMocks: true }
})
