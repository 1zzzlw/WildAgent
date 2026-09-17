import { defineConfig } from 'vite'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { existsSync, createReadStream } from 'node:fs'

const here = dirname(fileURLToPath(import.meta.url))
const projectRoot = resolve(here, '../../..')
const lantuDir = resolve(here, '..')

// 独立查看器：直接接入项目的渲染引擎
//   - wild-core    (src/wild-core/src/primitive/index.ts)  -> parseBlueprint / reconstructEntity
//   - wild-compiler(src/wild-compiler/index.ts)            -> compileBlueprintComponents
//   - 项目渲染层    (src/renderer/meshDataToGeometry.ts)     -> MeshData -> THREE.BufferGeometry
export default defineConfig({
  root: here,
  resolve: {
    alias: {
      'wild-core': resolve(here, '../../src/wild-core/src/primitive/index.ts'),
      'wild-compiler': resolve(here, '../../src/wild-compiler/index.ts'),
    },
  },
  plugins: [
    {
      name: 'serve-blueprints',
      configureServer(server) {
        server.middlewares.use('/bp', (req, res, next) => {
          const name = decodeURIComponent((req.url || '').split('?')[0].replace(/^\/+/, ''))
          const safe = name.replace(/[^a-zA-Z0-9_.\-\u4e00-\u9fa5]/g, '')
          const filePath = resolve(lantuDir, safe)
          if (!filePath.startsWith(lantuDir) || !existsSync(filePath)) {
            res.statusCode = 404
            return res.end('blueprint not found')
          }
          res.setHeader('Content-Type', 'application/json; charset=utf-8')
          createReadStream(filePath).pipe(res)
        })
      },
    },
  ],
  server: {
    host: true,
    port: 5180,
    fs: { allow: [here, projectRoot] },
  },
  // 直接以原生 ESM 提供 three（three/build/three.module.js 为单文件），
  // 关闭依赖预构建即可跳过 .vite/deps 缓存写入，避免环境安全删除门禁。
  // 注意：旧的 `optimizeDeps.disabled` 在 Vite 5.1 起已被移除（本机 Vite 8.x 会
  // 打印废弃警告后忽略它，等于没生效），官方替代写法是 noDiscovery + 空 include。
  optimizeDeps: { noDiscovery: true, include: [] },
  build: {
    outDir: resolve(here, 'dist'),
  },
})
