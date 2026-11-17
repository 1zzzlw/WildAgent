import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
import { launchEditorBrowser } from './editor-browser.mjs'

const output='../.workbuddy/render-upgrade/contracts'
await mkdir(output,{recursive:true})
const browser=await launchEditorBrowser('http://127.0.0.1:5188/scripts/material-mechanism-preview.html')
try {
  const p=browser.page
  await p.wait('window.ready')
  const result=await p.evaluate(`(async()=>{
    const T=window.THREE, {renderer,scene,camera,renderHarness:{post}}=window;
    const {WorldVisibilityRuntime}=await import('/src/renderer/visibilityRuntime.ts');
    const visibility=new WorldVisibilityRuntime(), root=new T.Group();root.userData.wildRenderRoot=true;scene.add(root);
    const material=new T.MeshStandardMaterial({color:0xd5dbe1,roughness:.8});
    const geometry=new T.BoxGeometry(.4,.4,.4);
    for(let i=0;i<100;i++) {const mesh=new T.Mesh(geometry,material);mesh.position.set(i%10-4.5,Math.floor(i/10)*.25,.01*(i%3));mesh.castShadow=true;root.add(mesh)}
    const wall=new T.Mesh(new T.BoxGeometry(15,12,.4),material.clone());wall.position.set(0,2,4);wall.castShadow=true;root.add(wall);
    scene.add(new T.HemisphereLight(0xffffff,0x657180,2));
    const light=new T.DirectionalLight(0xffffff,2);light.castShadow=true;light.position.set(-5,8,10);scene.add(light);
    light.shadow.camera.left=-12;light.shadow.camera.right=12;light.shadow.camera.top=12;light.shadow.camera.bottom=-12;light.shadow.camera.far=40;
    const floor=new T.Mesh(new T.PlaneGeometry(24,24),material);floor.rotation.x=-Math.PI/2;floor.position.y=-1;floor.receiveShadow=true;scene.add(floor);
    camera.position.set(1,2,12);camera.lookAt(0,2,0);camera.updateMatrixWorld();
    post.setAmbientOcclusion('gtao');post.setBloomEnabled(false);post.visibility.enabled=false;
    const gl=renderer.getContext(),pixels=()=>{const data=new Uint8Array(1280*960*4);gl.readPixels(0,0,1280,960,gl.RGBA,gl.UNSIGNED_BYTE,data);return data};
    const compare=name=>{
      renderer.shadowMap.needsUpdate=true;post.render();const before=pixels();
      renderer.shadowMap.needsUpdate=true;visibility.render(renderer,scene,camera,()=>post.render());const after=pixels();
      let changed=0,maxDelta=0;for(let i=0;i<before.length;i+=4){const delta=Math.max(Math.abs(before[i]-after[i]),Math.abs(before[i+1]-after[i+1]),Math.abs(before[i+2]-after[i+2]));if(delta>1)changed++;maxDelta=Math.max(delta,maxDelta)}
      return {name,changed,maxDelta,stats:{...visibility.stats},restored:root.children.every(mesh=>mesh.visible)};
    };
    const cases=[compare('solid-wall-and-shadows')];
    wall.material.transparent=true;wall.material.opacity=.25;wall.material.needsUpdate=true;cases.push(compare('material-becomes-transparent'));
    wall.material=material.clone();wall.material.depthWrite=false;cases.push(compare('non-depth-writing-material'));
    wall.material=material.clone();wall.layers.set(1);cases.push(compare('occluder-layer-disabled'));wall.layers.set(0);
    wall.material=new T.MeshPhysicalMaterial({transmission:1,roughness:0});cases.push(compare('transmissive-glass'));
    wall.material=material.clone();wall.position.x=20;cases.push(compare('open-wall'));wall.position.x=0;
    wall.scale.x=-1;cases.push(compare('negative-scale'));wall.scale.x=1;
    camera.position.set(0,2,1.5);camera.lookAt(0,2,0);camera.updateMatrixWorld();cases.push(compare('inside-building'));
    camera.position.set(0,2,4.1);camera.lookAt(0,2,0);camera.updateMatrixWorld();cases.push(compare('near-plane-intersection'));
    camera.position.set(1,2,12);camera.lookAt(0,2,0);camera.updateMatrixWorld();
    renderer.clippingPlanes=[new T.Plane(new T.Vector3(0,-1,0),2)];cases.push(compare('section-cut'));renderer.clippingPlanes=[];
    const {BlueprintAssemblyRuntime}=await import('/src/renderer/blueprintAssemblyRuntime.ts');
    const assembly=new BlueprintAssemblyRuntime(root);assembly.start();assembly.tick(1);cases.push(compare('assembly-animation'));assembly.finish();
    // 拆成真实门洞的左右墙与门楣，不能以整面包围盒遮住洞内构件。
    root.remove(wall);
    for(const [x,y,width,height] of [[-4.5,2,6,12],[4.5,2,6,12],[0,6,3,4]]){
      const part=new T.Mesh(new T.BoxGeometry(width,height,.4),material);part.position.set(x,y,4);part.castShadow=true;root.add(part)
    }
    cases.push(compare('real-door-opening'));
    let restoredOnError=false;const shadowRender=renderer.shadowMap.render;
    try { visibility.render(renderer,scene,camera,()=>{throw Error('draw failed')}) } catch {restoredOnError=root.children.every(mesh=>mesh.visible)&&scene.matrixWorldAutoUpdate&&renderer.shadowMap.render===shadowRender}
    root.clear();cases.push(compare('cleared-root'));
    return {cases,restoredOnError};
  })()`)
  assert.deepEqual(p.errors,[])
  for(const entry of result.cases){assert.equal(entry.changed,0,entry.name);assert.equal(entry.restored,true,entry.name)}
  assert.ok(result.cases[0].stats.occluded>50,'必须实际省去被墙遮住的内部绘制')
  assert.equal(result.cases.find(c=>c.name==='material-becomes-transparent').stats.occluded,0)
  assert.equal(result.cases.find(c=>c.name==='occluder-layer-disabled').stats.occluded,0)
  assert.equal(result.restoredOnError,true)
  await writeFile(output+'/visibility.json',JSON.stringify(result,null,2))
  console.log(JSON.stringify(result))
}finally{await browser.close()}
