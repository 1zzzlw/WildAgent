import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
import { launchEditorBrowser } from './editor-browser.mjs'
const output=process.argv[2]||'../docs/10月27日/验证';await mkdir(output,{recursive:true});
const browser=await launchEditorBrowser('http://127.0.0.1:5178/scripts/material-mechanism-preview.html');
try{
 const p=browser.page;await p.wait('window.ready');
 const surfaces=await p.evaluate('window.materialProbe()');assert.equal(surfaces.length,13);
 for(const s of surfaces){if(s.pattern)assert.ok(s.changedPixels>100, s.id+' 图案必须改变真实像素');if(s.id.startsWith('glass'))assert.ok(s.transmission>.8);}
 assert.ok(surfaces.find(s=>s.id==='metal_brushed').anisotropy>.6);assert.ok(surfaces.find(s=>s.id==='fabric_linen').sheen>.4);
 const bricks=await p.evaluate(`(async()=>{
  const {PROCEDURAL_BRICK_PRESETS}=await import('/src/wild/proceduralMaterialPresets.ts'),{reconstructWildEntity}=await import('/src/renderer/wildCoreAdapter.ts'),{createSceneGroupFromEntity,clearSceneObjectResources}=await import('/src/renderer/renderEntity.ts');
  const THREE=window.THREE,scene=new THREE.Scene(),eye=new THREE.PerspectiveCamera(36,4/3,.01,10);scene.background=new THREE.Color('#303944');scene.environment=window.scene.environment;scene.add(new THREE.HemisphereLight(0xffffff,0x777777,1.5));const key=new THREE.DirectionalLight(0xffffff,2);key.position.set(1,2,3);scene.add(key);eye.position.set(.3,.1,2);eye.lookAt(0,0,0);const results=[];
  for(const preset of PROCEDURAL_BRICK_PRESETS){const e=await reconstructWildEntity({meta:{version:'1.1',type:'asset',name:preset.name},geometry:{elements:[{type:'primitive',id:'brick',shape:'box',dimensions:[1.4,1,.12],material:preset.id}]},materials:{[preset.id]:preset.material}}),g=createSceneGroupFromEntity(e);scene.add(g);window.renderer.render(scene,eye);const gl=window.renderer.getContext(),pixels=new Uint8Array(1280*960*4);gl.readPixels(0,0,1280,960,gl.RGBA,gl.UNSIGNED_BYTE,pixels);let hash=2166136261;for(const value of pixels)hash=Math.imul(hash^value,16777619);results.push({id:preset.id,pixelDigest:hash>>>0,proceduralType:e.materialParams[0].procedural.type});const f=document.createElement('figure');f.innerHTML='<img src="'+window.renderer.domElement.toDataURL('image/png')+'"><figcaption>'+preset.name+'</figcaption>';document.querySelector('#gallery').append(f);scene.remove(g);clearSceneObjectResources(g)}return results;
 })()`);
 assert.equal(bricks.length,3);assert.equal(new Set(bricks.map(b=>b.pixelDigest)).size,3);assert.ok(bricks.every(b=>b.proceduralType==='brick'));
 await p.screenshot(output+'/材质库-真实管线预览.png');
 const occlusion=await p.evaluate('window.occlusionProbe()');for(const tier of ['low','medium','high']){const a=occlusion.find(s=>s.quality===tier&&!s.glass),b=occlusion.find(s=>s.quality===tier&&s.glass);assert.equal(a.active,a.shadows);assert.ok(a.rgb.reduce((x,y)=>x+y,0)+150<b.rgb.reduce((x,y)=>x+y,0),JSON.stringify({a,b}));assert.equal(a.wallCasts,true);assert.equal(b.wallCasts,false);}
 assert.deepEqual(p.errors,[]);const result={status:'PASS',surfaces,bricks,occlusion,shaderErrors:p.errors};await writeFile(output+'/材质与遮光GPU回归.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));
}finally{await browser.close()}
