/**
 * 判定：一层正立面墙是否真的被 window/door 开了洞。
 *
 * 做法：取 wall_f_l1 的网格，把它变换到世界坐标，统计**落在窗洞矩形范围内
 * 且贴在立面平面（z ≈ 0）上**的三角形数量。
 *   - 有洞：该矩形内几乎无三角形（只有洞口侧壁的进深面，且其 z 不落在立面平面上）
 *   - 无洞：矩形内密布三角形（立面被细分成网格）
 *
 * 用法：cd wild-web && node ../.workbuddy/diag/audit_wall_openings.mjs lantu/modern_pool_villa.wild
 */
const ROOT = 'E:/AgentProject/WildAgent/wild-web'
const CORE = 'E:/AgentProject/WildAgent/wild-core'
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
      'wild-core/compiler': `${CORE}/src/compiler/index.ts`,
      'wild-core/materials': `${CORE}/src/materials/index.ts`,
      'wild-core/world': `${CORE}/src/world/index.ts`,
      'wild-core/primitive': `${CORE}/src/primitive/index.ts`,
      'wild-core/types': `${CORE}/types.ts`,
      'wild-core': `${CORE}/src/index.ts`,
    },
  },
})

/** 把 mesh 的局部顶点变换到世界坐标（含 rotation，绕 Y 轴）。 */
function worldVerts(mesh) {
  const g = mesh.geometry
  const t = mesh.transform ?? {}
  const p = t.position ?? [0, 0, 0]
  const r = t.rotation ?? [0, 0, 0]
  const s = t.scale ?? [1, 1, 1]
  const cy = Math.cos(r[1]), sy = Math.sin(r[1])
  const out = []
  for (let i = 0; i < g.length; i += 3) {
    const x = g[i] * s[0], y = g[i + 1] * s[1], z = g[i + 2] * s[2]
    out.push([
      p[0] + x * cy + z * sy,
      p[1] + y,
      p[2] - x * sy + z * cy,
    ])
  }
  return out
}

const bpText = await readFile(process.argv[2], 'utf8')
try {
  const { parseWildBlueprint, reconstructWildEntity } = await server.ssrLoadModule(
    '/src/renderer/wildCoreAdapter.ts',
  )
  const entity = await reconstructWildEntity(parseWildBlueprint(bpText))
  const byId = {}
  for (const m of entity.meshes) (byId[m.elementId] ??= []).push(m)

  // 一层正立面窗洞（蓝图里声明的 three 个开口 + 门），世界坐标矩形
  const openings = [
    { id: 'window_l1_a', x0: 0.15, x1: 3.75, y0: 0.15, y1: 3.1 },
    { id: 'door_l1_main', x0: 4.4, x1: 7.6, y0: 0.15, y1: 3.1 },
    { id: 'window_l1_b', x0: 8.25, x1: 11.85, y0: 0.15, y1: 3.1 },
  ]

  for (const wallId of ['wall_f_l1', 'wall_f_l2']) {
    const meshes = byId[wallId] ?? []
    let facadeArea = 0
    let holeArea = 0
    const hits = Object.fromEntries(openings.map((o) => [o.id, 0]))

    const triArea = (a, b, c) => {
      const ux = b[0] - a[0], uy = b[1] - a[1]
      const vx = c[0] - a[0], vy = c[1] - a[1]
      return Math.abs(ux * vy - uy * vx) / 2
    }

    for (const mesh of meshes) {
      const v = worldVerts(mesh)
      const idx = mesh.indices
      for (let i = 0; i < idx.length; i += 3) {
        const a = v[idx[i]], b = v[idx[i + 1]], c = v[idx[i + 2]]
        const cz = (a[2] + b[2] + c[2]) / 3
        // 只统计贴在立面平面上的三角形（墙厚 0.24，立面在外侧 ±0.12）
        if (Math.abs(cz) > 0.13) continue
        const area = triArea(a, b, c)
        facadeArea += area
        const cx = (a[0] + b[0] + c[0]) / 3
        const cy = (a[1] + b[1] + c[1]) / 3
        for (const o of openings) {
          if (cx > o.x0 && cx < o.x1 && cy > o.y0 && cy < o.y1) {
            hits[o.id] += 1
            holeArea += area
            break
          }
        }
      }
    }

    const solidFaceArea = 12 * 3.3 * 2
    const openArea = openings.reduce(
      (s, o) => s + (o.x1 - o.x0) * (o.y1 - o.y0),
      0,
    )
    const expectedIfHoled = (12 * 3.3 - openArea) * 2

    console.log(`\n=== ${wallId} ===`)
    console.log(`网格数 ${meshes.length}`)
    console.log(`立面平面上三角形总面积 ${facadeArea.toFixed(2)} m²`)
    console.log(`  若墙体实心（12×3.3×2 面）应为 ${solidFaceArea.toFixed(2)} m²`)
    console.log(`  若开了 3 个洞，应约为 ${expectedIfHoled.toFixed(2)} m²`)
    console.log(`落在窗洞矩形内的三角形面积 ${holeArea.toFixed(2)} m²（应≈0）`)
    for (const [k, n] of Object.entries(hits)) console.log(`   ${k}: ${n} tri`)
    console.log(
      Math.abs(facadeArea - expectedIfHoled) < Math.abs(facadeArea - solidFaceArea)
        ? '   ✅ 立面面积吻合「开了洞」→ 墙体确实被开洞'
        : '   ❌ 立面面积吻合「实心」→ 墙体没开洞',
    )
  }
} finally {
  await server.close()
}
