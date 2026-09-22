import { defineConfig } from 'vite'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { existsSync, createReadStream } from 'node:fs'

const here = dirname(fileURLToPath(import.meta.url)) // wild-web/lantu/viewer
const repoRoot = resolve(here, '../../..')           // 仓库根：覆盖 wild-web 与 wild-core
const lantuDir = resolve(here, '..')                 // wild-web/lantu（.wild 存放处）

// ─────────────────────────────────────────────────────────────
// 独立查看器：直接接入项目的渲染引擎
//
//   wild-core                    → parseBlueprint / reconstructEntity
//   wild-web/src/renderer        → wildCoreAdapter / BlueprintRenderInstance
//                                  （编辑器视口用的同一条链路，不另起一套）
//
// ⚠️ 这里**刻意不写 resolve.alias**。
//    历史版本的 config 把 'wild-core' 指向 ../../src/wild-core/src/primitive/index.ts，
//    而 wild-core 拆成独立包后该路径已不存在 —— 那会让 dev server 直接启动失败。
//    现在一律用包名，由 wild-web/node_modules/wild-core（file: 依赖的软链）解析。
//
// ⚠️ fs.allow 必须放到仓库根：wild-core 是 wild-web 的**同级目录**，
//    软链被 vite 解析成真实路径后落在 wild-web 之外。
// ─────────────────────────────────────────────────────────────
export default defineConfig({
  root: here,
  plugins: [
    {
      // 蓝图以静态资源提供：GET /bp/<文件名> → wild-web/lantu/<文件名>
      // 用中间件而不是 publicDir，是为了让 .wild 和 viewer 分处两层目录仍能原地编辑。
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
    fs: { allow: [repoRoot] },
  },
  // three 以原生 ESM 单文件提供，关掉依赖预构建即可跳过 .vite/deps 缓存写入。
  // 注意：旧的 optimizeDeps.disabled 在 Vite 5.1 起已移除，官方替代是 noDiscovery + 空 include。
  optimizeDeps: { noDiscovery: true, include: [] },
  build: {
    outDir: resolve(here, 'dist'),
  },
})
