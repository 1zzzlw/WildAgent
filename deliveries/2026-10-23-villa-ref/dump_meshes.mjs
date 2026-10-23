/**
 * 把 WILD 用真实 Core 编译成世界坐标三角形，导出 JSON 供离线几何投影使用。
 * 这不是 WebGL 渲染，只是同一份引擎网格的可见性/比例检查。
 */
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const WEB = 'C:/Users/Administrator/.workbuddy/skills/wild-blueprint-authoring/references/blueprint-kit/核心资料/wild-web'
const CORE = 'C:/Users/Administrator/.workbuddy/skills/wild-blueprint-authoring/references/blueprint-kit/核心资料/wild-core'
const { build } = await import(pathToFileURL(join(WEB, 'node_modules/vite/dist/node/index.js')).href)

const target = process.argv[2]
const out = process.argv[3]
if (!target || !out) {
  console.error('用法: node dump_meshes.mjs <建筑.wild> <out.json>')
  process.exit(2)
}

const slash = (p) => p.replaceAll('\\', '/')
const virtualEntry = `
export { parseBlueprint } from 'wildsrc:parser';
export { reconstructEntity } from 'wildsrc:core';
export { compileBlueprintComponents } from 'wildsrc:compiler';
`
const dir = await mkdtemp(join(tmpdir(), 'wild-dump-'))
try {
  await build({
    root: WEB,
    logLevel: 'silent',
    plugins: [{
      name: 'wild-dump-entry',
      resolveId(id) {
        if (id === 'virtual:wild-dump') return '\0virtual:wild-dump'
        if (id === 'wildsrc:parser') return slash(join(CORE, 'src/primitive/parser.ts'))
        if (id === 'wildsrc:core') return slash(join(CORE, 'src/primitive/index.ts'))
        if (id === 'wildsrc:compiler') return slash(join(CORE, 'src/compiler/index.ts'))
      },
      load(id) {
        if (id === '\0virtual:wild-dump') return virtualEntry
      },
    }],
    build: {
      outDir: dir, emptyOutDir: false, minify: false,
      rollupOptions: {
        input: 'virtual:wild-dump', preserveEntrySignatures: 'exports-only',
        output: { format: 'es', entryFileNames: 'wild-dump.mjs' },
      },
    },
  })
  const core = await import(`${pathToFileURL(join(dir, 'wild-dump.mjs')).href}?t=${Date.now()}`)
  const blueprint = core.parseBlueprint(await readFile(target, 'utf8'))
  const compilation = core.compileBlueprintComponents(blueprint)
  const entity = await core.reconstructEntity(compilation.blueprint)

  const materials = blueprint.materials || {}
  const tri = []
  const color = []
  const origin = []
  for (const mesh of entity.meshes) {
    const g = mesh.geometry
    const idx = mesh.indices
    const t = mesh.transform
    const [rx, ry, rz] = t.rotation || [0, 0, 0]
    const [sx, sy, sz] = t.scale || [1, 1, 1]
    const [px, py, pz] = t.position || [0, 0, 0]
    const cos = [Math.cos(rx), Math.cos(ry), Math.cos(rz)]
    const sin = [Math.sin(rx), Math.sin(ry), Math.sin(rz)]
    const mat = materials[mesh.materialRef] || null
    const rgb = mat && Array.isArray(mat.baseColor) ? mat.baseColor : [0.72, 0.72, 0.72]
    const emissive = mat && Array.isArray(mat.emissive) ? 1 : 0
    const glass = mat && (mat.materialClass === 'glass') ? 1 : 0
    const count = g.length / 3
    // 顶点：先缩放 → 欧拉 XYZ 旋转 → 平移
    const world = new Float64Array(g.length)
    for (let i = 0; i < count; i++) {
      let x = g[i * 3] * sx, y = g[i * 3 + 1] * sy, z = g[i * 3 + 2] * sz
      let y1 = y * cos[0] - z * sin[0], z1 = y * sin[0] + z * cos[0]
      let x2 = x * cos[1] + z1 * sin[1], z2 = -x * sin[1] + z1 * cos[1]
      let x3 = x2 * cos[2] - y1 * sin[2], y3 = x2 * sin[2] + y1 * cos[2]
      world[i * 3] = x3 + px
      world[i * 3 + 1] = y3 + py
      world[i * 3 + 2] = z2 + pz
    }
    const indices = idx ? Array.from(idx) : null
    const n = indices ? indices.length : count
    for (let i = 0; i < n; i += 3) {
      const a = indices ? indices[i] : i
      const b = indices ? indices[i + 1] : i + 1
      const c = indices ? indices[i + 2] : i + 2
      for (const v of [a, b, c]) tri.push(+world[v * 3].toFixed(4), +world[v * 3 + 1].toFixed(4), +world[v * 3 + 2].toFixed(4))
      color.push(rgb[0], rgb[1], rgb[2])
      origin.push(emissive, glass)
    }
  }
  await writeFile(out, JSON.stringify({
    tri, color, origin,
    bounds: entity.boundingBox,
    meshCount: entity.meshes.length,
    materialCount: entity.materialParams.length,
  }))
  console.log(`meshes=${entity.meshes.length} triangles=${tri.length / 9} -> ${out}`)
} finally {
  await rm(dir, { recursive: true, force: true })
}
