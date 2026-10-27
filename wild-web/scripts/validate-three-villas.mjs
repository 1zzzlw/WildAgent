import assert from 'node:assert/strict'
import { readFile, writeFile } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { createServer } from 'vite'
import * as THREE from 'three'

const root = '../docs/10月27日/渲染性能光影与三种别墅'
const manifest = JSON.parse(await readFile(root + '/生成清单.json', 'utf8'))
const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom', logLevel: 'error' })
try {
  const { validateBlueprintSchema } = await vite.ssrLoadModule('../wild-core/src/primitive/schema-validator.ts')
  const { compileBlueprintComponents } = await vite.ssrLoadModule('../wild-core/src/compiler/index.ts')
  const { validateGeometryRelations } = await vite.ssrLoadModule('../wild-core/src/relationships.ts')
  const { reconstructEntity } = await vite.ssrLoadModule('../wild-core/src/primitive/index.ts')
  const { meshDataToGeometry } = await vite.ssrLoadModule('/src/renderer/meshDataToGeometry.ts')
  const results = []
  for (const record of manifest.records) {
    const text = await readFile(root + '/' + record.directory + '/' + record.file, 'utf8'), bp = JSON.parse(text)
    assert.equal(createHash('sha256').update(text).digest('hex'), record.sha256)
    const schema = validateBlueprintSchema(bp), relations = validateGeometryRelations(bp.geometry)
    assert.deepEqual(schema, [], record.name + ': Schema'); assert.deepEqual(relations, [], record.name + ': 引用')
    const compiled = compileBlueprintComponents(bp)
    assert.deepEqual(compiled.diagnostics.filter(d => d.level === 'error'), [], record.name + ': 编译')
    const entity = await reconstructEntity(compiled.blueprint)
    assert.deepEqual(entity.diagnostics.filter(d => d.level === 'error'), [], record.name + ': Core')
    const ids = [...bp.geometry.elements, ...bp.geometry.components].map(e => e.id)
    assert.equal(new Set(ids).size, ids.length)
    const meshes = entity.meshes.map(m => {
      assert.ok(m.geometry.every(Number.isFinite)); assert.ok(m.normals.every(Number.isFinite))
      assert.ok(Object.values(m.transform).flat().every(Number.isFinite)); assert.ok(compiled.blueprint.materials[m.materialRef])
      const mesh = new THREE.Mesh(meshDataToGeometry(m), new THREE.MeshBasicMaterial({ side: THREE.DoubleSide }))
      mesh.position.fromArray(m.transform.position); mesh.rotation.set(...m.transform.rotation); mesh.scale.fromArray(m.transform.scale); mesh.name = m.elementId; mesh.updateMatrixWorld(); return mesh
    })
    const ray = new THREE.Raycaster(), holes = []
    for (const floor of bp.geometry.elements.filter(e => e.type === 'floor' && e.holes)) for (const hole of floor.holes) {
      const x = hole.reduce((s,p) => s + p[0], 0) / hole.length + floor.from[0]
      const z = hole.reduce((s,p) => s + p[1], 0) / hole.length + floor.from[2]
      ray.set(new THREE.Vector3(x, floor.from[1] + 1, z), new THREE.Vector3(0, -1, 0))
      assert.equal(ray.intersectObjects(meshes.filter(m => m.name === floor.id)).length, 0, '孔被楼板覆盖: '+floor.id)
      holes.push({ floor: floor.id, center: [x,z], clear: true })
    }
    const stairs = []
    for (const stair of bp.geometry.elements.filter(e => e.type === 'stair')) {
      assert.ok(Math.abs(stair.from[1]+stair.stepHeight*stair.stepCount-stair.to[1]) < 1e-8)
      const dx=stair.to[0]-stair.from[0],dz=stair.to[2]-stair.from[2],len=Math.hypot(dx,dz)
      assert.ok(Math.abs(len-stair.stepDepth*stair.stepCount)<1e-8)
      if (stair.id === 'main_stair') {
        const end = new THREE.Vector3(stair.to[0]+dx/len*.025,stair.to[1]+1,stair.to[2]+dz/len*.025)
        ray.set(end,new THREE.Vector3(0,-1,0))
        const landing=ray.intersectObjects(meshes.filter(m=>m.name==='upper_slab'||m.name==='med_upper'))[0]
        assert.ok(landing && Math.abs(landing.point.y-stair.to[1])<1e-5,'楼梯上口必须接到达板')
      }
      stairs.push({id:stair.id,finishY:stair.to[1],dimensionsClosed:true})
    }
    const bounds=new THREE.Box3();for(const mesh of meshes)bounds.expandByObject(mesh)
    const limit=record.directory.startsWith('02')?15:16,zLimit=record.directory.startsWith('02')?15:14
    assert.ok(bounds.min.x>=-limit-1e-5&&bounds.max.x<=limit+1e-5&&bounds.min.z>=-zLimit-1e-5&&bounds.max.z<=zLimit+1e-5,'构件越出完整地块')
    const result={...record,status:'PASS',compiledElements:compiled.blueprint.geometry.elements.length,meshes:entity.meshes.length,diagnostics:[...compiled.diagnostics,...entity.diagnostics],holes,stairs,bounds:{min:bounds.min.toArray(),max:bounds.max.toArray()},checks:['raw Schema','unique IDs','references','Core compilation/reconstruction','finite geometry and material refs','real mesh floor holes','stair dimensions and upper landing','whole site bounds'],visual_review:{complete:false,reason:'此报告为静态/Core检查；真实渲染和人工审图另记'}}
    await writeFile(root+'/'+record.directory+'/静态与Core验收.json',JSON.stringify(result,null,2));results.push(result)
    for(const mesh of meshes){mesh.geometry.dispose();mesh.material.dispose()}
  }
  await writeFile(root+'/验证/三种别墅静态与Core.json',JSON.stringify({status:'PASS',results},null,2))
  console.log(JSON.stringify(results.map(r=>({name:r.name,status:r.status,meshes:r.meshes,diagnostics:r.diagnostics})),null,2))
} finally { await vite.close() }
