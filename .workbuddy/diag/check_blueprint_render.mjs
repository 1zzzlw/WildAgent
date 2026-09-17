/**
 * 用项目真实的编译 + 重建链路体检一份 .wild 蓝图。
 *
 * 为什么需要它：`verify_wild_blueprint.py` 只跑校验器（数据合法性），
 * 校验器全绿**不代表引擎能重建出网格**。这一层只有真跑一遍才知道。
 *
 * 输出：逐网格的 elementId / 元素偏移 / 局部尺寸 / 材质类，加编译与重建诊断，
 * 以及足迹中心偏离世界原点的量（查看器 frameToBox 的归一化依据）。
 *
 * 用法（工作目录必须是 wild-web，否则解析不到 node_modules）：
 *   cd wild-web
 *   <托管node> ../.workbuddy/diag/check_blueprint_render.mjs <蓝图路径...>
 * 退出码 0 = 无 error 级诊断。
 */
const ROOT = 'E:/AgentProject/WildAgent/wild-web'
const { readFile } = await import('node:fs/promises')
const { createServer } = await import(
  'file:///E:/AgentProject/WildAgent/wild-web/node_modules/vite/dist/node/index.js'
)

const targets = process.argv.slice(2)
if (targets.length === 0) {
  console.error('用法: check_blueprint_render.mjs <蓝图路径...>')
  process.exit(2)
}

const server = await createServer({
  root: ROOT,
  appType: 'custom',
  logLevel: 'silent',
  server: { middlewareMode: true },
})

/**
 * 把元素空间的顶点按 three 的默认 XYZ 欧拉序转到世界空间，取 AABB。
 * 关键点：**必须应用 rotation** —— 本项目离线预览曾只加 position 忽略 rotation，
 * 导致左右后墙与全部门窗落在错误位置，基于那些图得出的结论全是错的。
 */
function worldBounds(geometry, position, rotation, scale) {
  const [cx, cy, cz] = rotation
  const [sx, sy, sz] = scale
  const cosx = Math.cos(cx), sinx = Math.sin(cx)
  const cosy = Math.cos(cy), siny = Math.sin(cy)
  const cosz = Math.cos(cz), sinz = Math.sin(cz)
  // R = Rx · Ry · Rz（three 默认 XYZ 序），再乘 scale，最后平移
  const m = [
    cosy * cosz, -cosy * sinz, siny,
    cosx * sinz + sinx * siny * cosz, cosx * cosz - sinx * siny * sinz, -sinx * cosy,
    sinx * sinz - cosx * siny * cosz, sinx * cosz + cosx * siny * sinz, cosx * cosy,
  ]
  const min = [Infinity, Infinity, Infinity]
  const max = [-Infinity, -Infinity, -Infinity]
  const g = geometry
  const n = typeof g.getX === 'function' ? g.count : Math.floor(g.length / 3)
  for (let i = 0; i < n; i += 1) {
    const vx = (typeof g.getX === 'function' ? g.getX(i) : g[i * 3]) * sx
    const vy = (typeof g.getY === 'function' ? g.getY(i) : g[i * 3 + 1]) * sy
    const vz = (typeof g.getZ === 'function' ? g.getZ(i) : g[i * 3 + 2]) * sz
    const wx = m[0] * vx + m[1] * vy + m[2] * vz + position[0]
    const wy = m[3] * vx + m[4] * vy + m[5] * vz + position[1]
    const wz = m[6] * vx + m[7] * vy + m[8] * vz + position[2]
    if (wx < min[0]) min[0] = wx
    if (wy < min[1]) min[1] = wy
    if (wz < min[2]) min[2] = wz
    if (wx > max[0]) max[0] = wx
    if (wy > max[1]) max[1] = wy
    if (wz > max[2]) max[2] = wz
  }
  return { min, max }
}

let exitCode = 0

try {
  const { parseWildBlueprint, reconstructWildEntity } = await server.ssrLoadModule(
    '/src/renderer/wildCoreAdapter.ts',
  )
  const { compileBlueprintComponents } = await server.ssrLoadModule(
    '/src/wild-compiler/index.ts',
  )

  for (const target of targets) {
    console.log('='.repeat(76))
    console.log(target)
    console.log('='.repeat(76))

    let text
    try {
      text = await readFile(target, 'utf8')
    } catch (err) {
      console.log(`  ❌ 读取失败：${err.message}`)
      exitCode = 1
      continue
    }

    let entity
    let compile
    try {
      const bp = parseWildBlueprint(text)
      compile = compileBlueprintComponents(bp)
      // 关键：reconstruct 会把渲染私有字段原地写进 compiled.blueprint，
      // 另开一次 compile 拿到的是干净副本，看不到 _eave 之类。
      entity = await reconstructWildEntity(compile.blueprint)
    } catch (err) {
      console.log(`  ❌ 链路抛异常：${err?.message ?? err}`)
      exitCode = 1
      continue
    }

    const count = (list, level) => (list || []).filter((d) => d.level === level).length
    const cmpErr = count(compile.diagnostics, 'error')
    const cmpWarn = count(compile.diagnostics, 'warning')
    const recErr = (entity.diagnostics || []).filter((d) => d.level === 'error')
    const recWarn = (entity.diagnostics || []).filter((d) => d.level === 'warning')

    console.log(`  网格 ${entity.meshes.length} / 材质 ${entity.materialParams.length}`)
    console.log(`  组件编译诊断：错误 ${cmpErr} / 警告 ${cmpWarn}`)
    console.log(`  重建诊断：错误 ${recErr.length} / 警告 ${recWarn.length}`)
    for (const d of [...recErr, ...recWarn].slice(0, 20)) {
      console.log(`      [${d.level}] ${d.elementId ?? '-'}: ${d.message}`)
    }

    const bb = entity.boundingBox
    if (bb) {
      const size = [0, 1, 2].map((i) => (bb.max[i] - bb.min[i]).toFixed(2))
      console.log(
        `  包围盒 X[${bb.min[0].toFixed(2)}, ${bb.max[0].toFixed(2)}] ` +
          `Y[${bb.min[1].toFixed(2)}, ${bb.max[1].toFixed(2)}] ` +
          `Z[${bb.min[2].toFixed(2)}, ${bb.max[2].toFixed(2)}]  尺寸 ${size.join(' × ')} m`,
      )
      const cx = (bb.min[0] + bb.max[0]) / 2
      const cz = (bb.min[2] + bb.max[2]) / 2
      console.log(
        `  足迹中心 (${cx.toFixed(3)}, ${cz.toFixed(3)}) ⇒ 偏离世界原点 ` +
          `${Math.hypot(cx, cz).toFixed(3)} m（查看器据此平移归一化）`,
      )
    }

    // 逐元素聚合：同一 elementId 可能有多个网格（如屋顶 = 屋面 + 檐口线脚）。
    // 用**世界包围盒**而不是 transform.position —— 后者对 box 是中心，
    // 容易被当成"底面标高"读错（这个坑本项目踩过）。
    const byElement = new Map()
    entity.meshes.forEach((mesh, i) => {
      const id = mesh.elementId ?? `#${i}`
      const t = mesh.transform || {}
      const p = t.position || [0, 0, 0]
      const s = t.scale || [1, 1, 1]
      const r = t.rotation || [0, 0, 0]
      const bounds = worldBounds(mesh.geometry, p, r, s)
      const entry = byElement.get(id) || {
        count: 0,
        min: [Infinity, Infinity, Infinity],
        max: [-Infinity, -Infinity, -Infinity],
        mats: new Set(),
      }
      entry.count += 1
      for (let k = 0; k < 3; k += 1) {
        entry.min[k] = Math.min(entry.min[k], bounds.min[k])
        entry.max[k] = Math.max(entry.max[k], bounds.max[k])
      }
      entry.mats.add(entity.materialParams[i]?.materialClass ?? 'standard')
      byElement.set(id, entry)
    })
    console.log('  ── 逐元素世界包围盒（元素空间 → 世界，含 rotation/scale）')
    for (const [id, e] of byElement) {
      const fmt = (k) =>
        `[${e.min[k].toFixed(2)}, ${e.max[k].toFixed(2)}]`.padEnd(15)
      console.log(
        `     ${id.padEnd(38)} 网格${String(e.count).padStart(3)}  ` +
          `X${fmt(0)} Y${fmt(1)} Z${fmt(2)} ${[...e.mats].join(',')}`,
      )
    }

    if (recErr.length > 0 || cmpErr > 0) {
      console.log('  — 结果：FAIL（存在 error 级诊断）')
      exitCode = 1
    } else {
      console.log('  — 结果：PASS')
    }
  }
} finally {
  await server.close()
}

process.exit(exitCode)
