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
  const texture = { encoding: 'url', uri: '/metric-probe.png', sha256: '0'.repeat(64), mimeType: 'image/png' }
  const metricMaterial = { baseColor: [.5,.5,.5], roughness: .6, metallic: 0, albedo: 1,
    lightingCondition: 'D65_noon', textureSet: 'finish', uvScale: [3,2] }
  const probe = elements => ({ meta: { version: '1.1', type: 'asset', name: '纹理尺度' }, geometry: { elements },
    materials: { finish: metricMaterial }, assets: { finish: { kind: 'pbr_texture_set', maps: { baseColor: texture }, realWorldSizeMeters: [2,4] } } })
  const density = mesh => {
    for (let offset = 0; offset < mesh.indices.length; offset += 3) {
      const [a,b,c] = Array.from(mesh.indices.slice(offset,offset+3))
      const du1=mesh.uvs[b*2]-mesh.uvs[a*2], dv1=mesh.uvs[b*2+1]-mesh.uvs[a*2+1]
      const du2=mesh.uvs[c*2]-mesh.uvs[a*2], dv2=mesh.uvs[c*2+1]-mesh.uvs[a*2+1]
      const det=du1*dv2-du2*dv1
      assert.ok(Math.abs(det)>1e-10, '建筑每个实体面都需要非退化 UV')
      const tangent=[0,1,2].map(axis=>((mesh.geometry[b*3+axis]-mesh.geometry[a*3+axis])*dv2-(mesh.geometry[c*3+axis]-mesh.geometry[a*3+axis])*dv1)/det*mesh.transform.scale[axis])
      const bitangent=[0,1,2].map(axis=>((mesh.geometry[c*3+axis]-mesh.geometry[a*3+axis])*du1-(mesh.geometry[b*3+axis]-mesh.geometry[a*3+axis])*du2)/det*mesh.transform.scale[axis])
      assert.ok(Math.abs(Math.hypot(...tangent)-1)<1e-5, '每 UV 单位沿 U 必须对应一米')
      assert.ok(Math.abs(Math.hypot(...bitangent)-1)<1e-5, '每 UV 单位沿 V 必须对应一米')
    }
  }
  for (const length of [2,7]) for (const angle of [0,Math.PI/2]) {
    const bp=probe([
      {type:'beam',id:'beam',from:[0,0,0],to:[Math.sin(angle)*length,1,Math.cos(angle)*length],crossSection:'rectangular',width:.2,height:.4,material:'finish'},
      {type:'primitive',id:'sweep',shape:'profile_sweep',path:[[0,0,0],[0,0,length]],profile:[[0,0],[.2,0],[.2,.5],[0,.5]],caps:true,material:'finish'},
      {type:'primitive',id:'box',shape:'box',dimensions:[2,3,4],scale:[2,3,.5],rotation:[.2,angle,.3],material:'finish'},
    ])
    const original=JSON.stringify(bp), entity=await reconstructEntity(bp)
    assert.deepEqual(entity.diagnostics.filter(d=>d.level==='error'),[])
    entity.meshes.forEach(density)
    entity.materialParams.forEach(p=>assert.deepEqual(p.uvScale,[1.5,.5], '物理贴图尺寸必须参与重复频率'))
    assert.equal(JSON.stringify(bp),original, 'UV 重建不能改写源蓝图')
  }
  for(const height of [2,5]) {
    const bp=probe([
      {type:'column',id:'column',base:[0,0,0],height,bottomRadius:.3,topRadius:.3,style:'modern',material:'finish'},
      {type:'primitive',id:'cylinder',shape:'cylinder',height,radius:.3,material:'finish'},
      {type:'primitive',id:'sphere',shape:'sphere',radius:.3,scale:[2,2,2],material:'finish'},
    ])
    const entity=await reconstructEntity(bp)
    assert.ok(entity.meshes.every(m=>[...m.uvs,...m.normals].every(Number.isFinite)))
    for(const id of ['column','cylinder']) {
      const mesh=entity.meshes.find(m=>m.elementId===id)
      const maxU=Math.max(...mesh.uvs.filter((_,i)=>i%2===0)), maxV=Math.max(...mesh.uvs.filter((_,i)=>i%2===1))
      assert.ok(Math.abs(maxU-Math.PI*.6)<1e-5)
      assert.ok(Math.abs(maxV-height)<1e-5)
    }
    delete bp.assets
    bp.materials.finish={...metricMaterial,textureSet:undefined,textures:{baseColor:texture}}
    const legacy=await reconstructEntity(bp)
    assert.deepEqual(legacy.materialParams[0].uvScale,[3,2])
    assert.equal(Math.max(...legacy.meshes[0].uvs),1,'旧图片材质保留归一化柱身 UV')
  }
  const brickProbe=probe([{type:'primitive',id:'brick',shape:'profile_sweep',path:[[0,0,0],[0,0,6]],profile:[[0,0],[.2,0],[.2,.5],[0,.5]],caps:true,material:'finish'}])
  brickProbe.materials.finish={...metricMaterial,textureSet:undefined,procedural:{type:'brick',brickSize:[.24,.065]}}
  const brickEntity=await reconstructEntity(brickProbe)
  density(brickEntity.meshes[0])
  results.push('metre UV density, unequal sweep edges, curved surfaces, transform scale, texture asset dimensions, legacy image compatibility')
  const cases = process.argv[2] ? resolve(process.argv[2]) : resolve(root, '../docs/蓝图文档/案例')
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
