import assert from 'node:assert/strict'
import { readFile, writeFile, mkdir } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { createServer } from 'vite'
import * as THREE from 'three'
const file='../docs/10月27日/岚石光庭-交互材质别墅.wild',input=await readFile(file,'utf8'),bp=JSON.parse(input)
const vite=await createServer({server:{middlewareMode:true},appType:'custom',logLevel:'error'})
try{
 const {validateBlueprintSchema}=await vite.ssrLoadModule('../wild-core/src/primitive/schema-validator.ts')
 const {compileBlueprintComponents}=await vite.ssrLoadModule('../wild-core/src/compiler/index.ts')
 const {validateGeometryRelations}=await vite.ssrLoadModule('../wild-core/src/relationships.ts')
 const {reconstructEntity}=await vite.ssrLoadModule('../wild-core/src/primitive/index.ts')
 const {meshDataToGeometry}=await vite.ssrLoadModule('/src/renderer/meshDataToGeometry.ts')
 assert.deepEqual(validateBlueprintSchema(bp),[]);assert.deepEqual(validateGeometryRelations(bp.geometry),[])
 const compiled=compileBlueprintComponents(bp);assert.deepEqual(compiled.diagnostics,[])
 const entity=await reconstructEntity(compiled.blueprint);assert.deepEqual(entity.diagnostics.filter(d=>d.level==='error'),[])
 for(const m of entity.meshes){assert.ok(m.geometry.every(Number.isFinite));assert.ok(m.normals.every(Number.isFinite));assert.ok(Object.values(m.transform).flat().every(Number.isFinite));assert.ok(compiled.blueprint.materials[m.materialRef],'编译后材质引用必须存在：'+m.materialRef)}
 const ids=[...bp.geometry.elements,...bp.geometry.components].map(e=>e.id);assert.equal(new Set(ids).size,ids.length)
 const meshes=entity.meshes.map(m=>{const mesh=new THREE.Mesh(meshDataToGeometry(m),new THREE.MeshBasicMaterial({side:THREE.DoubleSide}));mesh.position.fromArray(m.transform.position);mesh.rotation.set(...m.transform.rotation);mesh.scale.fromArray(m.transform.scale);mesh.name=m.elementId;mesh.updateMatrixWorld();return mesh})
 const slab=meshes.filter(m=>m.name==='floor_1'),ray=new THREE.Raycaster()
 for(const [x,z] of [[-6.2,-4.45],[-.7,-5.8]]){ray.set(new THREE.Vector3(x,5,z),new THREE.Vector3(0,-1,0));assert.equal(ray.intersectObjects(slab).length,0,'上层电梯井/楼梯井应为空')}
 ray.set(new THREE.Vector3(4,5,-2),new THREE.Vector3(0,-1,0));const floor=ray.intersectObjects(slab)[0];assert.ok(Math.abs(floor.point.y-3.72)<1e-5)
 for(const level of [0,1]){
  ray.set(new THREE.Vector3(-6.2,.32+level*3.4+1,-2.6),new THREE.Vector3(0,0,-1));assert.equal(ray.intersectObjects(meshes.filter(m=>m.name==='shaft_front_'+level)).length,0,'层门宿主墙应开洞')
 }
 const stair=bp.geometry.elements.find(e=>e.id==='main_stair');assert.ok(Math.abs(stair.from[1]+stair.stepCount*stair.stepHeight-stair.to[1])<1e-9)
 assert.equal(bp.geometry.elements.some(e=>'_interaction' in e),false)
 const result={status:'PASS',inputSha256:createHash('sha256').update(input).digest('hex'),bytes:Buffer.byteLength(input),elements:bp.geometry.elements.length,components:bp.geometry.components.length,compiledElements:compiled.blueprint.geometry.elements.length,meshes:entity.meshes.length,sourceMaterials:Object.keys(bp.materials).length,usedMaterialRefs:new Set(entity.meshes.map(m=>m.materialRef)).size,materialSlots:entity.materialParams.length,diagnostics:entity.diagnostics,checks:['schema','references','unique IDs','component compilation','finite geometry','upper floor shaft/stair openings','landing wall cutouts','stair finish elevation','runtime fields absent'],visual_review:{complete:false,reason:'静态/Core 报告不代替浏览器或用户审图'}}
 await mkdir('../docs/10月27日/验证',{recursive:true});await writeFile('../docs/10月27日/验证/别墅静态与Core验收.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2))
}finally{await vite.close()}
