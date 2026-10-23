import assert from 'node:assert/strict'
import * as THREE from 'three'
import { createServer } from 'vite'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('..', import.meta.url))
const server = await createServer({ root, logLevel: 'error' })
try {
  const core = await server.ssrLoadModule('../wild-core/src/compiler/index.ts')
  const { reconstructEntity } = await server.ssrLoadModule('../wild-core/src/primitive/index.ts')
  const relations = await server.ssrLoadModule('../wild-core/src/relationships.ts')
  const { createGeometryTranslationOperations, getGeometryTranslationIds, createComponentTranslationChanges, createGeometryRotationOperations } = await server.ssrLoadModule('/src/wild/componentDrag.ts')
  const { applyPatchToBlueprint, createGeometryRemovalOperations } = await server.ssrLoadModule('/src/wild/scenePatch.ts')
  const { validateBlueprint } = await server.ssrLoadModule('/src/wild/sceneValidator.ts')
  const source = { meta: { version: '1.1', type: 'building', name: '依附关系回归' }, geometry: {
    elements: [
      { type: 'wall', id: 'wall', from: [0,0,0], to: [8,3,0], thickness: .2 },
      { type: 'floor', id: 'floor', from: [0,0,0], to: [8,0,6], thickness: .2 },
      { type: 'roof', id: 'roof', position: [0,3,0], roofType: 'gable', span: 12, depth: 8, height: 2, thickness: .2 },
    ], components: [
      { type: 'window', id: 'window', parentWall: 'wall', from: [1,1,0], width: 1.5, height: 1 },
      { type: 'railing', id: 'rail', parentFloor: 'floor', path: [[1,0,1],[4,0,1]], height: 1 },
      { type: 'ramp', id: 'ramp', parentFloor: 'floor', from: [1,0,2], to: [3,.5,2], width: 1, thickness: .1 },
      { type: 'chimney', id: 'chimney', parentRoof: 'roof', position: [-1,0,0], width: .6, depth: .6, height: 1 },
      { type: 'cornice', id: 'cornice', parentRoof: 'roof', path: [[-2,.1,1],[2,.1,1]], profile: [[0,0],[.1,0],[.1,.1],[0,.1]] },
    ],
  }, materials: {} }
  const apply = (bp, operations) => applyPatchToBlueprint(bp, { operations })
  const compile = async bp => {
    const compiled = core.compileBlueprintComponents(bp)
    assert.deepEqual(compiled.diagnostics, [])
    const entity = await reconstructEntity(compiled.blueprint)
    assert.deepEqual(entity.diagnostics.filter(d => d.level === 'error'), [])
    return { entity, mapping: compiled.mapping }
  }
  const bounds = (result, id) => {
    const ids = result.mapping.generatedElementIdsByComponentId[id] || [id]
    const box = new THREE.Box3()
    for (const mesh of result.entity.meshes.filter(mesh => ids.includes(mesh.elementId))) {
      const transform = mesh.transform
      const matrix = new THREE.Matrix4().compose(new THREE.Vector3(...transform.position), new THREE.Quaternion().setFromEuler(new THREE.Euler(...transform.rotation)), new THREE.Vector3(...transform.scale))
      for (let i = 0; i < mesh.geometry.length; i += 3) box.expandByPoint(new THREE.Vector3().fromArray(mesh.geometry, i).applyMatrix4(matrix))
    }
    assert.equal(box.isEmpty(), false, id)
    return box
  }
  const delta = [2,1,-3], before = await compile(source), tested = []
  for (const [host, children] of [['wall',['window']], ['floor',['rail','ramp']], ['roof',['chimney','cornice']]]) {
    for (const selected of [[host], [host,...children]]) {
      const input = structuredClone(source)
      const operations = createGeometryTranslationOperations(input, selected, delta)
      assert.deepEqual(input, source, '编辑规划不能改写原输入')
      assert.equal(new Set(operations.map(op => op.id)).size, operations.length, '同一构件不能被移动两次')
      const moved = await compile(apply(input, operations))
      for (const id of children) {
        const actual = bounds(moved, id).getCenter(new THREE.Vector3()).sub(bounds(before, id).getCenter(new THREE.Vector3())).toArray()
        actual.forEach((value, i) => assert.ok(Math.abs(value - delta[i]) < 1e-5, `${selected}: ${id} world delta ${actual}`))
        assert.ok(getGeometryTranslationIds(input, selected).has(id), '预览必须包含局部坐标未变化的附件')
      }
    }
    const removed = apply(source, createGeometryRemovalOperations(source, [host]))
    for (const id of [host,...children]) assert.ok(![...removed.geometry.elements,...removed.geometry.components].some(item => item.id === id))
    assert.deepEqual(relations.validateGeometryRelations(removed.geometry), [])
    tested.push('move/multiselect/delete ' + host)
  }
  const childMove = createGeometryTranslationOperations(source, ['chimney'], [.5,.4,.2])
  assert.deepEqual(createGeometryRotationOperations(source,['floor']),[], '未实现的带附件楼板旋转不能只改宿主')
  assert.deepEqual(createGeometryRotationOperations(source,['roof']),[], '未实现的带附件屋顶旋转不能只改宿主')
  assert.equal(createGeometryRotationOperations(source,['wall']).length,1)
  const movedChild = await compile(apply(source, childMove))
  const actual = bounds(movedChild,'chimney').getCenter(new THREE.Vector3()).sub(bounds(before,'chimney').getCenter(new THREE.Vector3())).toArray()
  actual.forEach((value,i) => assert.ok(Math.abs(value - [.5,.4,.2][i]) < 1e-5, '坡面移动必须保持实际世界位移'))
  const legacy = structuredClone(source)
  legacy.geometry.elements.find(e=>e.id==='roof').position = [100,3,100]
  legacy.geometry.components.find(e=>e.id==='chimney').position = [101,5,100]
  legacy.geometry.components = legacy.geometry.components.filter(e=>e.type!=='cornice')
  const legacyBefore = await compile(legacy)
  const legacyMoved = await compile(apply(legacy, createGeometryTranslationOperations(legacy,['roof','chimney'],delta)))
  bounds(legacyMoved,'chimney').getCenter(new THREE.Vector3()).sub(bounds(legacyBefore,'chimney').getCenter(new THREE.Vector3())).toArray().forEach((value,i)=>assert.ok(Math.abs(value-delta[i])<1e-5))
  for (const wall of [
    {type:'wall',id:'w',from:[0,0,0],to:[6,3,8],thickness:.2},
    {type:'wall',id:'w',from:[5,0,0],to:[0,3,5],thickness:.2,curve:{type:'arc',center:[0,0,0],sweep:90,segments:32}},
    {type:'wall',id:'w',from:[5,0,0],to:[0,3,-5],thickness:.2,curve:{type:'arc',center:[0,0,0],sweep:-90,segments:32}},
  ]) {
    const from=[.3,1,.02], frame=core.createWallCoordinateFrame(wall)
    const direction=frame.directionAt(from[0]), shift=[direction[0]*.02,.4,direction[2]*.02]
    const translated=core.translateWallCoordinates(wall,from,shift)
    const a=frame.pointAt(...from),b=frame.pointAt(...translated)
    b.forEach((value,i)=>assert.ok(Math.abs(value-a[i]-shift[i])<1e-6))
    assert.deepEqual(createComponentTranslationChanges({type:'window',id:'a',parentWall:'w',from,width:1,height:1},shift,[wall]).from,translated)
  }
  assert.throws(()=>createComponentTranslationChanges({type:'opening',id:'raw-arc-opening',parentWall:'w',from:[1,1,0],width:1,height:1},[.1,0,0],[{type:'wall',id:'w',from:[5,0,0],to:[0,3,5],thickness:.2,curve:{type:'arc',center:[0,0,0],sweep:90}}]),/原生曲墙开口/)
  // Metadata attachment and placement chains share the same deletion closure.
  const chain=structuredClone(source)
  chain.geometry.elements.push({type:'dense_brick',id:'detail',attachment:{parent:'window',mapping:'planar'},origin:[0,0,0]})
  chain.geometry.placements=[{id:'tiles',onSurface:{parent:'detail'}}]
  chain.geometry.elements.push({type:'dense_brick',id:'nested',attachment:{parent:'tiles',mapping:'planar'},origin:[0,0,0]})
  const removed=apply(chain,createGeometryRemovalOperations(chain,['wall']))
  assert.ok(!removed.geometry.elements.some(e=>['detail','nested'].includes(e.id)))
  assert.equal(removed.geometry.placements.length,0)
  assert.equal(relations.validateGeometryRelations({elements:[{id:'x',type:'floor',parentFloor:'y'},{id:'y',type:'floor',parentFloor:'x'}]}).length,1)
  for (const bad of [{type:'railing',id:'bad',parentFloor:'missing',path:[[0,0,0],[1,0,0]],height:1},{type:'railing',id:'bad',parentFloor:'wall',path:[[0,0,0],[1,0,0]],height:1}]) {
    const bp=structuredClone(source);bp.geometry.components.push(bad)
    assert.ok(validateBlueprint(bp).some(issue=>issue.elementId==='bad'&&issue.level==='error'))
  }
  core.clearComponentCompilationCache()
  core.compileBlueprintComponents(source)
  const stats=core.getComponentCompilationCacheStats()
  core.compileBlueprintComponents(source)
  assert.ok(core.getComponentCompilationCacheStats().hits>stats.hits)
  const changed=structuredClone(source);changed.geometry.elements.find(e=>e.id==='floor').thickness=.5
  const compiledChanged=await compile(changed)
  assert.ok(Math.abs(bounds(compiledChanged,'rail').min.y-bounds(before,'rail').min.y-.3)<1e-5, '父楼板变化必须使附件缓存失效')
  const canopy={type:'canopy',id:'shade',parentWall:'wall',from:[1,2,0],width:2,depth:1,thickness:.15}
  const envelope=structuredClone(source);envelope.geometry.elements=[source.geometry.elements[0],{type:'wall',id:'other',from:[0,0,8],to:[8,3,8],thickness:.2}];envelope.geometry.components=[canopy]
  const first=core.compileBlueprintComponents(envelope)
  envelope.geometry.elements[1].from[2]=-8;envelope.geometry.elements[1].to[2]=-8
  const second=core.compileBlueprintComponents(envelope)
  assert.notDeepEqual(first.blueprint.geometry.elements.filter(e=>e.id.startsWith('shade__')),second.blueprint.geometry.elements.filter(e=>e.id.startsWith('shade__')), '外围墙改变必须重算雨棚外侧方向')
  assert.ok(core.getComponentCapabilities().every(cap=>cap.editing?.translation&&Array.isArray(cap.editing.parameters)))
  console.log(JSON.stringify({status:'PASS',tested:[...tested,'sloped roof world motion','legacy roof coordinates','straight and signed arc projections','attachment/placement closure','missing/wrong/cyclic hosts','cache invalidation and wall envelope','capability descriptors']},null,2))
} finally { await server.close() }
