import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
import { launchEditorBrowser } from './editor-browser.mjs'

const output = process.argv[2] || '../.workbuddy/render-upgrade/after'
await mkdir(output, { recursive: true })
const browser = await launchEditorBrowser('http://127.0.0.1:5188/scripts/material-mechanism-preview.html')
try {
  const page = browser.page
  await page.wait('window.ready')
  const result = await page.evaluate(`(async () => {
    const T = window.THREE;
    const { createSceneGroupFromEntity, clearSceneObjectResources } = await import('/src/renderer/renderEntity.ts');
    const { reconstructWildEntity } = await import('/src/renderer/wildCoreAdapter.ts');
    const { renderer, camera, scene, renderHarness: { post } } = window;
    const gl = renderer.getContext(), debug = gl.getExtension('WEBGL_debug_renderer_info');
    scene.add(new T.HemisphereLight(0xffffff, 0x59616f, 2));
    const report = { hardware: debug ? gl.getParameter(debug.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER), size: renderer.getSize(new T.Vector2()).toArray(), scenes: {} };
    const material = { baseColor: [.65,.7,.75], metallic: 0, roughness: .65, albedo: 1, lightingCondition: 'D65_noon' };
    const elements = [];
    for(let x=0; x<32; x++) for(let z=0; z<32; z++) for(let y=0;y<4;y++) {
      elements.push({ type:'primitive', shape:'box', id:'detail_'+x+'_'+z+'_'+y, position:[x*2-31, y*1.3+.6, z*2-31], dimensions:[.65,.8,.65], material:'stone' });
    }
    const fixtures = {
      hiddenInterior: { meta:{version:'1.1',type:'building',name:'大场景遮挡回归'}, materials:{stone:material}, geometry:{elements:[
        {type:'primitive',shape:'box',id:'solid_wall',position:[0,3,34],dimensions:[70,7,.5],material:'stone'}, ...elements.map((e,i)=>({...e,dimensions:[.65+i*.00001,.8,.65]}))
      ]}},
      dispersed: { meta:{version:'1.1',type:'building',name:'空间实例回归'}, materials:{stone:material}, geometry:{elements} }
    };
    const pixels = () => { const p=new Uint8Array(1280*960*4);gl.readPixels(0,0,1280,960,gl.RGBA,gl.UNSIGNED_BYTE,p);return p; };
    for (const [name, blueprint] of Object.entries(fixtures)) {
      const started = performance.now();
      const entity = await reconstructWildEntity(blueprint), root = createSceneGroupFromEntity(entity);scene.add(root);
      const buildMs = performance.now()-started;
      camera.position.set(3,3,48);camera.lookAt(0,3,0);camera.updateMatrixWorld();
      post.setAmbientOcclusion('gtao');post.setBloomEnabled(false);post.setSize(1280,960);
      renderer.shadowMap.enabled=false;
      for(let i=0;i<4;i++)post.render();gl.finish();
      const frames=[];
      for(let i=0;i<18;i++){
        camera.position.x+=.03;camera.lookAt(0,3,0);camera.updateMatrixWorld();renderer.info.reset();
        const t=performance.now();post.render();const submitMs=performance.now()-t;gl.readPixels(0,0,1,1,gl.RGBA,gl.UNSIGNED_BYTE,new Uint8Array(4));
        frames.push({submitMs, completeMs:performance.now()-t,calls:renderer.info.render.calls,triangles:renderer.info.render.triangles});
      }
      let comparison=null;
      if(post.visibility){
        post.visibility.enabled=false;post.render();const original=pixels();
        post.visibility.enabled=true;post.render();const culled=pixels();
        let changed=0,maxDelta=0;for(let i=0;i<original.length;i+=4){const d=Math.max(Math.abs(original[i]-culled[i]),Math.abs(original[i+1]-culled[i+1]),Math.abs(original[i+2]-culled[i+2]));if(d>1)changed++;maxDelta=Math.max(d,maxDelta);}
        comparison={changedPixels:changed,maxDelta,stats:{...post.visibility.stats}};
      }
      report.scenes[name]={meshes:entity.meshes.length,batches:root.children.length,buildMs,frames,comparison};
      if(name==='hiddenInterior') {
        camera.position.set(0,3,10);camera.lookAt(0,2,0);camera.updateMatrixWorld();post.render();
        report.scenes[name].interior=post.visibility?{...post.visibility.stats}:null;
      }
      scene.remove(root);clearSceneObjectResources(root);
    }
    renderer.shadowMap.enabled=true;
    return report;
  })()`)
  assert.deepEqual(page.errors, [])
  for (const scene of Object.values(result.scenes)) {
    if (scene.comparison) assert.equal(scene.comparison.changedPixels, 0, '遮挡优化应保留可见像素')
  }
  await writeFile(output + '/performance.json', JSON.stringify(result, null, 2))
  console.log(JSON.stringify({hardware:result.hardware,scenes:Object.fromEntries(Object.entries(result.scenes).map(([name,row])=>[name,{meshes:row.meshes,batches:row.batches,comparison:row.comparison,interior:row.interior}]))}))
} finally { await browser.close() }
