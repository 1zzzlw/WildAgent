import { defineConfig } from 'vite'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const projectRoot = resolve(here, '../../..')

// 单蓝图自包含构建：把天坛渲染页打成单文件（base 相对路径，内联后双击即可打开）。
export default defineConfig({
  root: here,
  base: './',
  resolve: {
    alias: {
      'wild-core': resolve(here, '../../src/wild-core/src/primitive/index.ts'),
      'wild-compiler': resolve(here, '../../src/wild-compiler/index.ts'),
    },
  },
  optimizeDeps: { noDiscovery: true, include: [] },
  build: {
    outDir: resolve(here, 'dist-single'),
    rollupOptions: {
      input: resolve(here, 'single.html'),
    },
  },
  server: {
    host: true,
    port: 5181,
    fs: { allow: [here, projectRoot] },
  },
})
