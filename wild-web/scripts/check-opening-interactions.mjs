import assert from 'node:assert/strict';
import { createServer } from 'vite';
import * as THREE from 'three';
const vite=await createServer({server:{middlewareMode:true}, appType:'custom', logLevel:'error'});
let cases=0;
try {
 const {compileBlueprintComponents}=await vite.ssrLoadModule('../wild-core/src/compiler/index.ts');
 const {reconstructEntity}=await vite.ssrLoadModule('../wild-core/src/primitive/index.ts');
 const {createSceneGroupFromEntity,toggleOpeningInteraction,toggleRuntimeInteraction,updateSceneGroup,clearSceneObjectResources}=await vite.ssrLoadModule('/src/renderer/renderEntity.ts');
 const {MaterialCache,getGlobalMaterialResourceStats}=await vite.ssrLoadModule('/src/renderer/materialAdapter.ts');
 const events=[];let now=0;globalThis.requestAnimationFrame=cb=>{events.push(cb);return events.length};
 const flush=()=>{for(let i=0;events.length&&i<50;i++){now=performance.now()+1000+i*1000;events.splice(0).forEach(cb=>cb(now));}assert.equal(events.length,0)};
 for(const angle of [0,Math.PI/2,-Math.PI/2,Math.PI]) for(const mode of ['swing','slide','lift']) for(const width of [1.2,2.4,4]) {
  const wall={type:'wall',id:'wall',from:[2,0,3],to:[2+8*Math.cos(angle),4,3+8*Math.sin(angle)],thickness:.24,material:'wall'};
  const component={type:'window',id:'window',parentWall:'wall',from:[1,1,0],width,height:1.8,frameWidth:.06,frameDepth:.24,glassDepth:.012,verticalMullions:1,horizontalMullions:1,frameMaterial:'frame',glassMaterial:'glass',interaction:{mode,openDistance:100}};
  const bp={version:'1.1',meta:{name:'regression',unit:'m'},geometry:{elements:[wall],components:[component]},materials:{wall:{baseColor:[.7,.7,.7]},frame:{baseColor:[.2,.2,.2]},glass:{baseColor:[.4,.7,.8],opacity:.4}}};
  const compiled=compileBlueprintComponents(bp);assert.deepEqual(compiled.diagnostics.filter(d=>d.level==='error'),[]);
  const entity=await reconstructEntity(compiled.blueprint);assert.deepEqual(entity.diagnostics.filter(d=>d.level==='error'),[]);
  const sashes=entity.meshes.filter(m=>m.elementId==='window__sash_left'||m.elementId==='window__sash_right'||m.elementId==='window__sash_bottom'||m.elementId==='window__sash_top');assert.equal(sashes.length,2);
  const [a,b]=sashes;
  if(mode!=='swing') {
   assert.ok(Math.abs(a.transform.position[2]-b.transform.position[2])>0.1||Math.abs(a.transform.position[0]-b.transform.position[0])>0.1);
   for(const mesh of entity.meshes.filter(m=>m.interaction)) for(const progress of [0,.25,.5,.75,1]) {
    const offset=mesh.interaction.openOffset;
    for(let i=0;i<mesh.geometry.length;i+=3){
     const x=mesh.geometry[i],y=mesh.geometry[i+1],z=mesh.geometry[i+2];const r=mesh.transform.rotation[1];
     const wx=Math.cos(r)*x+Math.sin(r)*z+mesh.transform.position[0]+(offset?.[0]||0)*progress;
     const wy=y+mesh.transform.position[1]+(offset?.[1]||0)*progress;
     const wz=-Math.sin(r)*x+Math.cos(r)*z+mesh.transform.position[2]+(offset?.[2]||0)*progress;
     const along=(wx-2)*Math.cos(angle)+(wz-3)*Math.sin(angle), normal=-(wx-2)*Math.sin(angle)+(wz-3)*Math.cos(angle);
     assert.ok(along>=1+.06-1e-6&&along<=1+width-.06+1e-6,`${mode} 水平超出洞口 ${along}`);
     assert.ok(wy>=1+.06-1e-6&&wy<=2.8-.06+1e-6,`${mode} 竖向超出洞口 ${wy}`);
     assert.ok(Math.abs(normal)<.12,`${mode} 轨道超出窗框深度 ${normal}`);
    }
   }
   const group=createSceneGroupFromEntity(entity,new MaterialCache());const mesh=group.children.find(o=>o.name===a.elementId);assert.ok(mesh);assert.ok(toggleOpeningInteraction(mesh));flush();
   const members=group.children.filter(o=>o.userData.interaction?.groupId===a.interaction.groupId);assert.equal(members.length,7);assert.ok(members.every(m=>m.userData.interactionProgress===1));
   const other=group.children.filter(o=>o.userData.interaction?.groupId===b.interaction.groupId);assert.ok(other.every(m=>!m.userData.interactionOpen));
  }
  cases++;
 }
 for(const angle of [0,Math.PI/2,Math.PI]) for(const style of ['rectangular','arched']) for(const initiallyOpen of [false,true]) {
  const bp={version:'1.1',meta:{name:'door',unit:'m'},geometry:{elements:[{type:'wall',id:'wall',from:[0,0,0],to:[6*Math.cos(angle),4,6*Math.sin(angle)],thickness:.24}],components:[{type:'door',id:'door',parentWall:'wall',from:[1,0,0],width:2.4,height:3,frameWidth:.08,openingStyle:style,doorStyle:'double',interaction:{mode:'swing',openAngle:85,initiallyOpen}}]},materials:{}};
  const compiled=compileBlueprintComponents(bp),entity=await reconstructEntity(compiled.blueprint);assert.deepEqual(entity.diagnostics.filter(d=>d.level==='error'),[]);
  const leaves=entity.meshes.filter(m=>m.elementId==='door__opening');assert.equal(leaves.length,2);assert.notDeepEqual(leaves[0].interaction.pivot,leaves[1].interaction.pivot);
  const group=createSceneGroupFromEntity(entity,new MaterialCache());const meshes=group.children.filter(m=>m.userData.interaction?.groupId==='door');assert.equal(meshes.length,2);
  assert.ok(meshes.every(m=>!!m.userData.interactionOpen===initiallyOpen));
  if(!initiallyOpen) {
   toggleOpeningInteraction(meshes[0]);events.splice(0).forEach(cb=>cb(performance.now()+100));
   assert.ok(meshes.every(m=>m.userData.interactionProgress>0&&m.userData.interactionProgress<1));
   toggleOpeningInteraction(meshes[1]);flush();assert.ok(meshes.every(m=>m.userData.interactionProgress===0));
  }
  toggleOpeningInteraction(meshes[0]);flush();assert.ok(meshes.every(m=>!!m.userData.interactionOpen===!initiallyOpen));
  toggleOpeningInteraction(meshes[1]);flush();assert.ok(meshes.every(m=>!!m.userData.interactionOpen===initiallyOpen));
  if(!initiallyOpen) meshes.forEach(m=>assert.ok(m.position.distanceTo(new THREE.Vector3(...m.userData.interaction.closedPosition))<1e-8));
  cases++;
 }
 const bp={meta:{version:'1.1',type:'building',name:'增量重建'},geometry:{elements:[
  {type:'wall',id:'wall',from:[0,0,0],to:[6,4,0],thickness:.24},
  ...[0,1,2].map(i=>({type:'primitive',id:'box'+i,shape:'box',dimensions:[.4,.5,.6],position:[i,0,3]})),
  {type:'primitive',id:'lamp',shape:'sphere',radius:.15,position:[0,3,2],lightSource:{intensity:10}},
 ],components:[{type:'door',id:'door',parentWall:'wall',from:[1,0,0],width:1.2,height:2.4}]},materials:{}};
 const build=async()=>reconstructEntity(compileBlueprintComponents(bp).blueprint);
 const cache=new MaterialCache(), statsBefore=getGlobalMaterialResourceStats();
 const group=createSceneGroupFromEntity(await build(),cache);
 const batch=group.children.find(o=>o.isInstancedMesh&&o.userData.instanceElementIds.includes('box0'));
 const door=group.children.find(o=>o.userData.interaction?.kind==='opening');
 const lamp=group.children.find(o=>o.userData.interaction?.kind==='light');
 assert.ok(batch&&door&&lamp);
 toggleOpeningInteraction(door);flush();toggleRuntimeInteraction(lamp);
 const lightLevel=lamp.userData.lightLevel, doorGeometry=door.geometry, batchGeometry=batch.geometry;
 let disposed=0;batchGeometry.addEventListener('dispose',()=>disposed++);
 bp.geometry.elements.find(e=>e.id==='box0').position=[20,0,3];
 updateSceneGroup(group,await build(),cache);
 assert.ok(group.children.includes(batch)&&group.children.includes(door)&&group.children.includes(lamp));
 assert.equal(door.geometry,doorGeometry);assert.equal(batch.geometry,batchGeometry);assert.equal(disposed,0);
 assert.equal(door.userData.interactionProgress,1,'修改其它构件不得关闭已打开的门');
 assert.equal(lamp.userData.lightLevel,lightLevel,'修改其它构件不得重置灯具开关');
 const matrix=new THREE.Matrix4();batch.getMatrixAt(0,matrix);assert.equal(matrix.elements[12],20);
 assert.ok(batch.boundingBox.max.x>20,'实例位置更新后必须更新剔除边界');
 const stableStats=getGlobalMaterialResourceStats();
 for(let i=0;i<3;i++) updateSceneGroup(group,await build(),cache);
 assert.deepEqual(getGlobalMaterialResourceStats(),stableStats,'重复重建不得增加共享资源引用');
 bp.geometry.elements=bp.geometry.elements.filter(e=>e.id!=='box2');
 updateSceneGroup(group,await build(),cache);
 assert.equal(disposed,1,'退出实例桶时必须释放旧几何');assert.ok(!group.children.includes(batch));
 assert.ok(group.children.some(o=>o.userData.elementId==='box0'));
 assert.equal(door.userData.interactionProgress,1);
 clearSceneObjectResources(group);cache.clear();
 assert.deepEqual(getGlobalMaterialResourceStats(),statsBefore,'释放场景后必须归还共享资源');
 console.log(JSON.stringify({passed:cases,incrementalSceneUpdates:true,assertions:'推拉/升降全行程、双扇铰链、网格复用、实例移动与包围盒、交互状态保留、资源释放'}));
} finally {await vite.close()}
