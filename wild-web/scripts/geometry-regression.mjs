import assert from 'node:assert/strict'
import { readFile, readdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { resolve, join } from 'node:path'
import { createServer } from 'vite'

const root = fileURLToPath(new URL('..', import.meta.url))
const server = await createServer({ root, logLevel: 'error' })
const results = []
try {
  const { buildFloor } = await server.ssrLoadModule('../wild-core/src/primitive/geometry/floor.ts')
  const { buildPrimitive } = await server.ssrLoadModule('../wild-core/src/primitive/geometry/primitive.ts')
  const { validateBlueprintSchema } = await server.ssrLoadModule('../wild-core/src/primitive/schema-validator.ts')
  const { parseBlueprint, reconstructEntity } = await server.ssrLoadModule('../wild-core/src/primitive/index.ts')
  const { compileBlueprintComponents } = await server.ssrLoadModule('../wild-core/src/compiler/index.ts')
  const closedVolume = mesh => {
    const edges = new Map()
    let volume = 0
    for (let i = 0; i < mesh.geometry.length; i += 9) {
      const [a, b, c] = [0, 3, 6].map(offset => Array.from(mesh.geometry.slice(i + offset, i + offset + 3)))
      for (const [p, q] of [[a, b], [b, c], [c, a]]) {
        const key = [p.join(','), q.join(',')].sort().join('|')
        edges.set(key, (edges.get(key) || 0) + 1)
      }
      volume += (a[0] * (b[1] * c[2] - b[2] * c[1]) + a[1] * (b[2] * c[0] - b[0] * c[2]) + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6
    }
    assert.ok([...edges.values()].every(count => count === 2), '每条实体边必须恰好属于两个三角面')
    assert.ok(volume > 0, '封闭实体绕序必须朝外')
    return volume
  }
  const outer = [[0, 0], [8, 0], [8, 6], [0, 6]]
  const hole = [[2, 2], [4, 2], [4, 4], [2, 4]]
  for (const reversed of [false, true]) {
    const params = { type: 'floor', id: 'slab', shape: 'polygon', from: [10, 3, -7], thickness: 0.25,
      polygon: reversed ? [...outer].reverse() : outer, holes: [reversed ? [...hole].reverse() : hole] }
    const blueprint = { meta: { version: '1.1', type: 'building', name: '回归' }, geometry: { elements: [params] } }
    assert.deepEqual(validateBlueprintSchema(blueprint), [])
    const [mesh] = buildFloor(params)
    assert.ok(Math.abs(closedVolume(mesh) - 11) < 1e-5)
    assert.deepEqual(mesh.transform.position, params.from)
    assert.equal(Math.max(...mesh.geometry.filter((_, i) => i % 3 === 1)), 0.25)
    const isInsideTriangle = (p, a, b, c) => {
      const side = (u, v) => (v[0] - u[0]) * (p[1] - u[1]) - (v[1] - u[1]) * (p[0] - u[0])
      const signs = [side(a, b), side(b, c), side(c, a)]
      return signs.every(v => v >= -1e-7) || signs.every(v => v <= 1e-7)
    }
    for (let i = 0; i < mesh.geometry.length; i += 9) {
      if (mesh.normals[i + 1] < 0.99) continue
      const points = [0, 3, 6].map(offset => [mesh.geometry[i + offset], mesh.geometry[i + offset + 2]])
      assert.equal(isInsideTriangle([3, 3], ...points), false, '孔洞中心不能被顶面覆盖')
    }
    results.push('polygon hole winding ' + reversed)
  }
  const [concave] = buildFloor({ type: 'floor', id: 'L', from: [0, 0, 0], shape: 'polygon', thickness: 0.2,
    polygon: [[0, 0], [6, 0], [6, 2], [2, 2], [2, 6], [0, 6]] })
  assert.ok(Math.abs(closedVolume(concave) - 4) < 1e-5)
  for (const polygon of [[[0, 0], [4, 4], [0, 4], [4, 0]], [[0, 0], [1, 0], [2, 0]]]) {
    assert.throws(() => buildFloor({ type: 'floor', id: 'invalid', from: [0, 0, 0], thickness: 0.2, shape: 'polygon', polygon }))
  }
  for (const invalidHole of [[[7, 2], [9, 2], [9, 4], [7, 4]], [[0, 2], [2, 2], [2, 4], [0, 4]]]) {
    assert.throws(() => buildFloor({ type: 'floor', id: 'invalid', from: [0, 0, 0], thickness: 0.2, shape: 'polygon', polygon: outer, holes: [invalidHole] }))
  }
  const [circle] = buildFloor({ type: 'floor', id: 'circle', from: [1, 3, 2], thickness: 0.4, shape: 'circle', radius: 2 })
  assert.throws(() => buildFloor({ type: 'floor', id: 'ignored-hole', from: [0, 0, 0], to: [8, 0, 6], thickness: .2, holes: [hole] }), '不能静默忽略矩形上的孔洞')
  assert.ok(Math.abs(Math.max(...circle.geometry.filter((_, i) => i % 3 === 1)) + circle.transform.position[1] - 3.4) < 1e-6)
  closedVolume(circle)
  for (const profile of [[[0, 0], [2, 0], [2, 1], [0, 1]], [[0, 0], [0, 1], [2, 1], [2, 0]], [[0, 0], [2, 0], [2, 1], [1, 1], [1, 2], [0, 2]]]) {
    const params = { type: 'primitive', id: 'capped', shape: 'profile_sweep', profile, path: [[0, 0, 0], [0, 0, 3]], caps: true }
    assert.deepEqual(validateBlueprintSchema({ meta: { version: '1.1', type: 'building', name: '扫掠' }, geometry: { elements: [params] } }), [])
    const [mesh] = buildPrimitive(params)
    const area = profile.length === 6 ? 3 : 2
    assert.ok(Math.abs(closedVolume(mesh) - area * 3) < 1e-5)
  }
  assert.throws(() => buildPrimitive({ type: 'primitive', id: 'invalid', shape: 'profile_sweep', profile: [[0, 0], [1, 0]], path: [[0, 0, 0], [0, 1, 0]], closedProfile: false, caps: true }))
  results.push('concave slab, invalid polygons, circular slab height, capped sweeps')
  const cases = resolve(root, '../docs/10月23日/蓝图文档/案例')
  const legacy = []
  for (const entry of await readdir(cases, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue
    for (const file of await readdir(join(cases, entry.name))) {
      if (!file.endsWith('.wild')) continue
      const blueprint = parseBlueprint(await readFile(join(cases, entry.name, file), 'utf8'))
      const compilation = compileBlueprintComponents(blueprint)
      const entity = await reconstructEntity(compilation.blueprint)
      assert.deepEqual(compilation.diagnostics.filter(d => d.level === 'error'), [], file)
      assert.deepEqual(entity.diagnostics.filter(d => d.level === 'error'), [], file)
      assert.ok(entity.meshes.length > 0 && entity.meshes.every(mesh => [...mesh.geometry].every(Number.isFinite)), file)
      legacy.push({ file, meshes: entity.meshes.length })
    }
  }
  console.log(JSON.stringify({ status: 'PASS', geometry: results, legacy }, null, 2))
} finally { await server.close() }
