/**
 * 临时探针：查 balcony / window 的玻璃材质是否真的落到了 mesh 上。
 * 用法：cd wild-web && node ../.workbuddy/diag/probe_material_binding.mjs lantu/modern_pool_villa.wild
 */
const ROOT = 'E:/AgentProject/WildAgent/wild-web'
const CORE_ROOT = 'E:/AgentProject/WildAgent/wild-core'
const { readFile } = await import('node:fs/promises')
const { createServer } = await import(
  'file:///E:/AgentProject/WildAgent/wild-web/node_modules/vite/dist/node/index.js'
)

const server = await createServer({
  root: ROOT,
  appType: 'custom',
  logLevel: 'silent',
  server: { middlewareMode: true },
  resolve: {
    alias: {
      'wild-core/compiler': `${CORE_ROOT}/src/compiler/index.ts`,
      'wild-core/materials': `${CORE_ROOT}/src/materials/index.ts`,
      'wild-core/world': `${CORE_ROOT}/src/world/index.ts`,
      'wild-core/primitive': `${CORE_ROOT}/src/primitive/index.ts`,
      'wild-core/types': `${CORE_ROOT}/types.ts`,
      'wild-core': `${CORE_ROOT}/src/index.ts`,
    },
  },
})

try {
  const { parseWildBlueprint, reconstructWildEntity } = await server.ssrLoadModule(
    '/src/renderer/wildCoreAdapter.ts',
  )
  const text = await readFile(process.argv[2], 'utf8')
  const bp = parseWildBlueprint(text)
  const entity = await reconstructWildEntity(bp)

  console.log('mesh[0] materialRef:', typeof entity.meshes[0].materialRef, JSON.stringify(entity.meshes[0].materialRef))
  console.log('materialParams[0] ctor:', entity.materialParams[0]?.constructor?.name)
  console.log('entity keys:', Object.keys(entity))
  const refs = new Set(entity.meshes.map((m) => JSON.stringify(m.materialRef)))
  console.log('distinct materialRef:', [...refs].slice(0, 12))
  console.log('materialParams 前 3 项:', entity.materialParams.slice(0, 3).map((p) => JSON.stringify(p)?.slice(0, 180)))
  console.log('materialParams[40..42]:', entity.materialParams.slice(40, 43).map((p) => JSON.stringify(p)?.slice(0, 180)))

  const map = entity.materialParams
  const rows = entity.meshes.map((m, i) => {
    const p = map[m.materialRef] ?? map[i]
    return `${String(m.elementId).padEnd(46)} ref=${JSON.stringify(m.materialRef)} -> ${JSON.stringify(p)?.slice(0, 150)}`
  })
  const interesting = rows.filter((r) => /balcony|window_l1_a|pool_bottom|roof_main|wall_f_l1|deck_pool/.test(r))
  console.log('\n--- 关注构件 ---')
  for (const r of interesting) console.log(r)
} finally {
  await server.close()
}
