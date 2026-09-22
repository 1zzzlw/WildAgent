import { defineConfig } from 'vite'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { readFileSync, writeFileSync, readdirSync, rmSync, existsSync } from 'node:fs'

// ─────────────────────────────────────────────────────────────
// 自包含单文件构建：双击即可打开的查看器。
//
// 为什么需要单独一份 config：
//   常规 `vite build` 产出的 `dist/index.html` 引用**绝对路径** `/assets/…`，
//   用 file:// 打开会解析成 `file:///E:/assets/…` 并被 CORS 拦截（实测白屏、
//   0 个 canvas）。而查看器默认要从 `/bp/<文件>` 取蓝图，那是 dev server 的中间件，
//   静态打开时并不存在。
//
// 所以这里做两件事：
//   ① 构建期把 .wild 文本内联进 HTML（`window.__WILD_INLINE_BLUEPRINT__`），
//      main.ts 见到它就不再 fetch；
//   ② 构建后把 JS / CSS **内联进同一个 HTML**，并删掉 assets 目录 —— 真·单文件。
//
// ⚠️ 不要在这里写 resolve.alias 指向 `../../src/wild-core/...`：
//    wild-core 已拆成与 wild-web 同级的独立包（`file:` 依赖 + 软链），
//    旧路径不存在，写了会让构建直接失败。一律用包名解析。
//
// 用法：
//   cd wild-web/lantu/viewer && node ../../node_modules/vite/bin/vite.js build --config vite.config.standalone.mjs
//   产物：dist-standalone/index.html
// ─────────────────────────────────────────────────────────────

const here = dirname(fileURLToPath(import.meta.url)) // wild-web/lantu/viewer
const repoRoot = resolve(here, '../../..')
const lantuDir = resolve(here, '..')

const BP_FILE = process.env.BP_FILE ?? 'modern_pool_villa.wild'
const BP_LABEL = process.env.BP_LABEL ?? BP_FILE.replace(/\.wild$/, '')

/** 把 JSON 文本安全地放进内联 <script>：`</script>` 会提前闭合脚本标签。 */
function toInlineLiteral(text) {
  return JSON.stringify(text).replace(/<\//g, '<\\/')
}

export default defineConfig({
  root: here,
  base: './',
  plugins: [
    {
      name: 'inline-blueprint-and-assets',
      transformIndexHtml: {
        order: 'pre',
        handler(html) {
          const bpPath = resolve(lantuDir, BP_FILE)
          if (!existsSync(bpPath)) {
            throw new Error(`蓝图不存在：${bpPath}`)
          }
          const raw = readFileSync(bpPath, 'utf8')
          // 先解析一次：内联一份坏 JSON 进 HTML，报错现场会难查得多
          JSON.parse(raw)
          const tag = `<script>window.__WILD_INLINE_BLUEPRINT__=${toInlineLiteral(raw)};`
            + `window.__WILD_INLINE_LABEL__=${toInlineLiteral(BP_LABEL)};</script>`
          return html.replace('</head>', `  ${tag}\n  </head>`)
        },
      },
      // 构建写盘之后把外部资源收进 HTML，并把 assets 目录删掉
      closeBundle() {
        const outDir = resolve(here, 'dist-standalone')
        const htmlPath = resolve(outDir, 'index.html')
        const assetsDir = resolve(outDir, 'assets')
        if (!existsSync(htmlPath)) return
        let html = readFileSync(htmlPath, 'utf8')

        if (!existsSync(assetsDir)) {
          console.log('\n[standalone] 没有独立的 assets 目录，产物已是单文件。')
          return
        }

        const cssFiles = readdirSync(assetsDir).filter((f) => f.endsWith('.css'))
        html = html.replace(/<link[^>]+rel="stylesheet"[^>]*>/g, '')
        if (cssFiles.length > 0) {
          const css = cssFiles
            .map((f) => readFileSync(resolve(assetsDir, f), 'utf8'))
            .join('\n')
          html = html.replace('</head>', `  <style>\n${css}\n  </style>\n  </head>`)
        }

        html = html.replace(
          /<script([^>]*)\ssrc="\.\/assets\/([^"]+)"([^>]*)><\/script>/g,
          (_m, _pre, file) => {
            const js = readFileSync(resolve(assetsDir, file), 'utf8')
            // 内联后不能再带 crossorigin/src —— file:// 下外部模块脚本会被 CORS 拦
            return `<script type="module">\n${js}\n</script>`
          },
        )

        writeFileSync(htmlPath, html)
        rmSync(assetsDir, { recursive: true, force: true })
        // eslint-disable-next-line no-console
        console.log(`\n[standalone] 单文件产物：${htmlPath}`)
        console.log(`[standalone] 蓝图已内联：${BP_FILE}（${readFileSync(resolve(lantuDir, BP_FILE), 'utf8').length} 字符）`)
      },
    },
  ],
  optimizeDeps: { noDiscovery: true, include: [] },
  build: {
    outDir: resolve(here, 'dist-standalone'),
    emptyOutDir: true,
    // 内联要求单块产物，别做代码分割
    cssCodeSplit: false,
    assetsInlineLimit: 100000000,
    rollupOptions: {
      // 内联要求单块产物。新 Rollup 用 codeSplitting:false（旧写法 inlineDynamicImports 会告警）
      output: { codeSplitting: false },
    },
  },
  server: {
    host: true,
    port: 5181,
    fs: { allow: [repoRoot] },
  },
})
