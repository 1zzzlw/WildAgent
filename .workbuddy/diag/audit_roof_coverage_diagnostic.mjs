/**
 * 屋顶覆盖诊断（RECONSTRUCTION_ROOF_COVERAGE）的回归门禁。
 *
 * 背景：历史实现拿**每一块**屋顶去比**全楼墙并集**，于是任何多体量建筑
 * （L 形 / 退台 / 主体+门廊）每一块屋顶都会被判"未完全覆盖"。实测一栋
 * 3 块屋顶的别墅 3 块全报 warning，但 Python 侧 7e 校验器 PASS、真实渲染正常
 * —— 全是误报。同时，用全量墙并集还会把泳池矮墙（高 1.5m）撑进范围，
 * 让任何屋顶都不可能盖住。
 *
 * 修法（`wild-web/src/renderer/reconstructionDiagnostics.ts`）：
 *   ① 只算**结构性墙**（高 ≥1.8m 且厚 ≥0.1m）；
 *   ② 比**屋顶并集**，不再逐块比；
 *   ③ 只报 ⚠️ 不报 ❌。
 *
 * 本脚本同时钉住两件事：
 *   正例 —— 多体量分段屋顶**不许**报警（误报回归）
 *   反例 —— 真缺一块屋顶**必须**报警（失效回归）
 *
 * 用法：cd wild-web && node ../.workbuddy/diag/audit_roof_coverage_diagnostic.mjs
 * 退出码 0 = 全部符合预期。
 */
const ROOT = 'E:/AgentProject/WildAgent/wild-web'
const CORE = 'E:/AgentProject/WildAgent/wild-core'
const BP = `${ROOT}/lantu/modern_pool_villa.wild`

const { readFile } = await import('node:fs/promises')
const { createServer } = await import(
  `file:///${ROOT}/node_modules/vite/dist/node/index.js`
)

const server = await createServer({
  root: ROOT,
  appType: 'custom',
  logLevel: 'silent',
  server: { middlewareMode: true },
  resolve: {
    alias: {
      'wild-core/compiler': `${CORE}/src/compiler/index.ts`,
      'wild-core/materials': `${CORE}/src/materials/index.ts`,
      'wild-core/world': `${CORE}/src/world/index.ts`,
      'wild-core/primitive': `${CORE}/src/primitive/index.ts`,
      'wild-core/types': `${CORE}/types.ts`,
      'wild-core': `${CORE}/src/index.ts`,
    },
  },
})

const failures = []
const check = (label, condition, detail) => {
  if (condition) {
    console.log(`  ✅ ${label}`)
  } else {
    console.log(`  ❌ ${label}  ${detail ?? ''}`)
    failures.push(label)
  }
}

const roofWarnings = (entity) =>
  entity.diagnostics.filter((d) => d.code === 'RECONSTRUCTION_ROOF_COVERAGE')

try {
  const { parseWildBlueprint, reconstructWildEntity } = await server.ssrLoadModule(
    '/src/renderer/wildCoreAdapter.ts',
  )
  const base = JSON.parse(await readFile(BP, 'utf8'))

  // ── 正例：多体量分段屋顶 ──────────────────────────────────
  console.log('\n【正例】原蓝图（3 块屋顶分段覆盖 3 个体量）')
  {
    const entity = await reconstructWildEntity(parseWildBlueprint(JSON.stringify(base)))
    const ids = base.geometry.elements.filter((e) => e.type === 'roof').map((e) => e.id)
    console.log(`  roofs = ${ids.join(', ')}`)
    const warns = roofWarnings(entity)
    check(
      '多体量分段屋顶不报 RECONSTRUCTION_ROOF_COVERAGE',
      warns.length === 0,
      warns.map((w) => w.message).join(' | '),
    )
    check(
      '泳池矮墙（高 1.5m）不被算进覆盖范围',
      warns.length === 0,
      '泳池四壁若被当结构墙，任何屋顶都盖不住',
    )
  }

  // ── 反例 1：抽掉一整块体量的屋顶 ──────────────────────────
  console.log('\n【反例 1】删掉 roof_b（门廊体量整块裸露）')
  {
    const mutated = structuredClone(base)
    mutated.geometry.elements = mutated.geometry.elements.filter((e) => e.id !== 'roof_b')
    const entity = await reconstructWildEntity(parseWildBlueprint(JSON.stringify(mutated)))
    const warns = roofWarnings(entity)
    check('真缺一块屋顶时报警', warns.length === 1, `实际 ${warns.length} 条`)
    check('恰好一条聚合警告（不是逐块各报一条）', warns.length === 1)
    if (warns[0]) {
      console.log(`     消息：${warns[0].message}`)
      check('消息指明缺口方向', /缺 .*m/.test(warns[0].message), warns[0].message)
    }
  }

  // ── 反例 2：屋顶缩到盖不住自己的墙 ────────────────────────
  console.log('\n【反例 2】把 roof_main 的 span 缩到 8（盖不住 12m 主体）')
  {
    const mutated = structuredClone(base)
    for (const el of mutated.geometry.elements) {
      if (el.id === 'roof_main') el.span = 8
    }
    const entity = await reconstructWildEntity(parseWildBlueprint(JSON.stringify(mutated)))
    const warns = roofWarnings(entity)
    check('屋顶明显不够大时报警', warns.length === 1, `实际 ${warns.length} 条`)
    if (warns[0]) console.log(`     消息：${warns[0].message}`)
  }

  // ── 边界：只有矮墙、没有结构墙时不该报 ────────────────────
  console.log('\n【边界】所有墙都改成矮墙（不构成建筑）→ 跳过判定')
  {
    const mutated = structuredClone(base)
    // 去掉组合构件：矮墙会让门窗"超出父墙垂直范围"，那些 error 会淹没本用例的结论
    mutated.geometry.components = []
    for (const el of mutated.geometry.elements) {
      if (el.type === 'wall') el.to = [el.to[0], el.from[1] + 1.2, el.to[2]]
      if (el.type === 'roof') el.span = 1
    }
    const entity = await reconstructWildEntity(parseWildBlueprint(JSON.stringify(mutated)))
    check(
      '无结构墙时不产生覆盖警告（避免对纯构件/场地场景打扰）',
      roofWarnings(entity).length === 0,
      roofWarnings(entity).map((w) => w.message).join(' | '),
    )
  }
} finally {
  await server.close()
}

console.log('\n' + '─'.repeat(60))
if (failures.length > 0) {
  console.log(`❌ 失败 ${failures.length} 项：`)
  for (const f of failures) console.log(`   · ${f}`)
  process.exit(1)
}
console.log('✅ 屋顶覆盖诊断回归全部符合预期')
