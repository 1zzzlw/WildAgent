import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  build: {
    chunkSizeWarningLimit: 600,
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            {
              name: 'three',
              test: /node_modules[\\/]three[\\/]/,
              priority: 40,
            },
            {
              name: 'element-plus',
              test: /node_modules[\\/](@element-plus|element-plus)[\\/]/,
              priority: 30,
            },
            {
              name: 'markdown',
              test: /node_modules[\\/](markdown-it|highlight\.js)[\\/]/,
              priority: 20,
            },
            {
              name: 'vue',
              test: /node_modules[\\/](@vue|vue|pinia)[\\/]/,
              priority: 10,
            },
          ],
        },
      },
    },
  },
  server: {
    // wild-core 是仓库根下的同级包（通过 file: 依赖链接），不落在 vite 默认的
    // workspace root 内，必须显式放行上一级目录，否则 dev server 会拒绝加载它。
    fs: {
      allow: ['..'],
    },
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://127.0.0.1:8000',
        ws: true,
        changeOrigin: true,
      },
    },
  },
})
