/**
 * 门禁：光照/环境/后期链路的**唯一事实源**必须在 `wild-web/src/renderer/`。
 *
 * 背景（P0 缺陷）：引擎的材质层是按"场景里存在 `scene.environment`"设计的 ——
 * 玻璃走 `transmission` + `ior`、金属走 `envMapIntensity`，两者都靠 IBL 出反射。
 * 但生产环境贴图的 `pmremGenerator.fromScene()` 与 `scene.environment = ...` 一度
 * 只写在 `CanvasViewport.vue` 里，于是 `lantu/viewer` 拿不到 IBL，只能**自己造光**补：
 *   - 画面表现：天空黑、玻璃死蓝、金属发暗、没有反射；
 *   - 更严重的是"查看器看到的不是引擎行为，而是本地代码的行为"，违反查看器红线。
 * 同理 AO（接触阴影）也只活在 Vue 组件里，别的渲染方完全没有接触阴影。
 *
 * 本门禁把这件事钉死：任何 **光源构造 / PMREM / scene.environment 赋值 / 合成器构造**
 * 出现在 `src/renderer/` 之外即为失败。
 *
 * 用法：node ../.workbuddy/diag/audit_lighting_single_source.mjs
 * 退出码即结果（0 = 通过）。
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative, sep } from 'node:path'

const WEB = 'E:/AgentProject/WildAgent/wild-web'
const ENGINE_DIR = join(WEB, 'src', 'renderer')
const SCAN_ROOTS = [join(WEB, 'src'), join(WEB, 'lantu')]
const SKIP_DIRS = new Set(['node_modules', 'dist', 'dist-standalone', '.vite', 'renders'])
const EXTS = new Set(['.ts', '.tsx', '.vue', '.mjs', '.js'])

/** 只允许出现在 src/renderer/ 里的构造/赋值。 */
const FORBIDDEN = [
  { name: 'PMREMGenerator 构造', re: /new\s+THREE\.PMREMGenerator\s*\(/ },
  { name: '光源构造', re: /new\s+THREE\.(AmbientLight|HemisphereLight|DirectionalLight|PointLight|SpotLight|RectAreaLight)\s*\(/ },
  { name: 'scene.environment 赋值', re: /\bscene\.environment\s*=/ },
  { name: 'EffectComposer 构造', re: /new\s+EffectComposer\s*\(/ },
  { name: 'SSAOPass 构造', re: /new\s+SSAOPass\s*\(/ },
  { name: 'UnrealBloomPass 构造', re: /new\s+UnrealBloomPass\s*\(/ },
]

/** 两个消费方必须真的接上引擎运行时（否则有人又偷偷写回内联实现）。 */
const CONSUMERS = [
  {
    file: join(WEB, 'src', 'components', 'viewport', 'CanvasViewport.vue'),
    must: ['environmentRuntime', 'lightingRuntime', 'postProcessingRuntime'],
  },
  {
    file: join(WEB, 'lantu', 'viewer', 'main.ts'),
    must: ['environmentRuntime', 'lightingRuntime', 'postProcessingRuntime'],
  },
]

function walk(dir, out = []) {
  let entries
  try {
    entries = readdirSync(dir)
  } catch {
    return out
  }
  for (const entry of entries) {
    if (SKIP_DIRS.has(entry)) continue
    const full = join(dir, entry)
    const st = statSync(full)
    if (st.isDirectory()) walk(full, out)
    else if (EXTS.has(entry.slice(entry.lastIndexOf('.')))) out.push(full)
  }
  return out
}

const violations = []
const scanned = []

for (const root of SCAN_ROOTS) {
  for (const file of walk(root)) {
    scanned.push(file)
    const rel = relative(WEB, file).split(sep).join('/')
    if (file.startsWith(ENGINE_DIR)) continue
    const lines = readFileSync(file, 'utf8').split(/\r?\n/)
    lines.forEach((line, i) => {
      for (const rule of FORBIDDEN) {
        if (rule.re.test(line)) {
          violations.push(`${rel}:${i + 1}  ${rule.name} —— 必须放进 src/renderer/`)
        }
      }
    })
  }
}

const missing = []
for (const consumer of CONSUMERS) {
  let text = ''
  try {
    text = readFileSync(consumer.file, 'utf8')
  } catch {
    missing.push(`${relative(WEB, consumer.file)} 不存在`)
    continue
  }
  for (const token of consumer.must) {
    if (!text.includes(token)) {
      missing.push(`${relative(WEB, consumer.file)} 未引用 ${token}`)
    }
  }
}

console.log(`扫描文件 ${scanned.length} 个（src/ 与 lantu/，跳过 node_modules/dist）`)
console.log(`引擎目录内允许构造，目录外禁止：${FORBIDDEN.map(r => r.name).join(' / ')}`)

if (violations.length === 0 && missing.length === 0) {
  console.log('\n✅ 通过：光照/环境/后期链路唯一事实源在 src/renderer/，两个消费方均已接入。')
  process.exit(0)
}

if (violations.length) {
  console.log('\n❌ 引擎目录外出现光照/环境/后期实现：')
  for (const v of violations) console.log(`  · ${v}`)
}
if (missing.length) {
  console.log('\n❌ 消费方未接入引擎运行时：')
  for (const m of missing) console.log(`  · ${m}`)
}
process.exit(1)
