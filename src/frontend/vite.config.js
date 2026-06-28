import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vitejs.dev/config/
export default defineConfig({
  root: fileURLToPath(new URL('.', import.meta.url)),
  base: "./",
  build: {
    outDir: '../../build/frontend'
  },
  plugins: [
    vue(),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      '~/': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  css: {
    preprocessorOptions: {
      scss: {
        additionalData: `@use "@/assets/scss/tokens" as *;`,
      },
    },
  },
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:25556",
        changeOrigin: true,
        secure: false,
      },
    },
  }
})

