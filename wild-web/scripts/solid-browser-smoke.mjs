import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { mkdir, readFile, readdir, writeFile } from 'node:fs/promises'
import { resolve, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createServer, preview } from 'vite'
import { launchEditorBrowser } from './editor-browser.mjs'

const root = fileURLToPath(new URL('..', import.meta.url))
const pack = resolve(process.argv[2])
const output = resolve(process.argv[3] || '../output/nov03-render')
await mkdir(output, { recursive: true })
const server = await createServer({ root, logLevel: 'error', server: { host: '127.0.0.1', port: 0 } })
await server.listen()
const browser = await launchEditorBrowser(server.resolvedUrls.local[0] + 'scripts/presentation-preview.html')
let production
const p = browser.page
const report = { samples: [], interactions: [], productionWorker: null }
try {
  await p.wait('window.ready')
  for (const [file, image] of [
    ['新增实体体块展示.wild', 'solid-showcase.png'],
    ['穹庭自然研学馆-新实体建筑示例.wild', 'solid-building.png'],
    ['文衡堂-斗拱雕花古建.wild', 'carved-openings.png']
  ]) {
    const source = await readFile(join(pack, file), 'utf8')
    const result = await p.evaluate(`(async () => {
      const { parseWildBlueprint } = await import('/src/renderer/wildCoreAdapter.ts');
      const loaded = await presentationTest.scene.loadBlueprint(parseWildBlueprint(${JSON.stringify(source)}));
      const s = document.querySelector('.canvas-viewport').__vueParentComponent.setupState;
      s.finishEntrance(); s.markNeedsRender();
      await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
      const entity = presentationTest.scene.reconstructed;
      return { loaded, meshes: entity.meshes.length, hidden: entity.hiddenElementIds.length,
        errors: entity.diagnostics.filter(d => d.level === 'error') };
    })()`)
    assert.equal(result.loaded, true, file)
    assert.ok(result.meshes > 0)
    assert.deepEqual(result.errors, [], file)
    await p.wait(
      'document.querySelector(".canvas-viewport").__vueParentComponent.setupState.renderer.info.render.calls > 0'
    )
    await p.screenshot(join(output, image))
    report.samples.push({ file, sha256: createHash('sha256').update(source).digest('hex'), ...result })
  }

  report.interactions = await p.evaluate(`(async () => {
    const THREE = await import('/node_modules/three/build/three.module.js');
    const { toggleOpeningInteraction } = await import('/src/renderer/renderEntity.ts');
    const results = [];
    for (const variant of ['door', 'window', 'legacyDoor']) for (const mode of ['swing', 'slide', 'lift']) {
      const type=variant==='legacyDoor'?'door':variant;
      const parts = [
        { shape:'box', dimensions:[.3,.8,.04], position:[.2,.6,0], rotation:[.4,.3,-.2] },
        { shape:'box', dimensions:[.04,.2,.04], position:[.4,.8,.04], rotation:[.1,-.2,.3] },
      ];
      const bp = { meta:{version:'1.1',type:'asset',name:'倾斜雕花开合'}, geometry:{
        elements:[{type:'wall',id:'wall',from:[0,0,0],to:[6,3,3],thickness:.2}],
        components:[{type,id:'opening',parentWall:'wall',from:[1,.2,0],width:2.4,height:2.4,
          doorStyle:'double', interaction:{mode,openAngle:80},
          leaves:Array.from({length:type==='door' && mode!=='swing'?1:2},()=>({parts}))}] } };
      if(variant==='legacyDoor') {
        delete bp.geometry.components[0].leaves;
        bp.geometry.components[0].leafParts=[{id:'handle',position:[.25,1,.04],dimensions:[.03,.25,.04],material:'metal'}];
        if(mode==='swing')bp.geometry.components[0].leafParts.push({id:'second',leaf:1,position:[-.25,1,.04],dimensions:[.03,.25,.04],material:'metal'});
        bp.materials={metal:{baseColor:[.5,.5,.5],roughness:.3,metallic:.8,albedo:1,lightingCondition:'D65_noon'}};
      }
      if (!await presentationTest.scene.loadBlueprint(bp)) throw Error('load failed');
      if(presentationTest.scene.reconstructed.diagnostics.some(d=>d.level==='error'))throw Error('opening reconstruction failed');
      await new Promise(r=>requestAnimationFrame(r));
      const s = document.querySelector('.canvas-viewport').__vueParentComponent.setupState;
      s.finishEntrance();
      const group = s.sceneGroup;
      const members = group.children.filter(m=>m.userData.interaction?.kind==='opening');
      if(!members.length)throw Error('missing opening meshes');
      if(variant==='legacyDoor'&&!members.some(m=>m.name.includes('__leafpart_')))throw Error('missing legacy attachments');
      const frames = group.children.filter(m=>m.name.includes('__frame_'));
      group.updateMatrixWorld(true);
      const initial = members.map(m=>m.matrix.clone());
      const fixed = frames.map(m=>m.matrix.toArray());
      const closed = members.map(m=>[...m.position.toArray(),...m.quaternion.toArray()]);
      const source = JSON.stringify(presentationTest.scene.document.blueprint);
      const controls = new Map(members.map(m=>[m.userData.interaction.groupId,m]));
      let maxError=0, samples=0;
      for (const target of [1,0]) {
        for (const control of controls.values()) toggleOpeningInteraction(control,s.markNeedsRender);
        for (let tick=0;tick<120;tick++) {
          await new Promise(r=>requestAnimationFrame(r)); group.updateMatrixWorld(true); samples++;
          members.forEach((mesh,i)=>{
            const interaction=mesh.userData.interaction,progress=mesh.userData.interactionProgress||0;
            const expected=initial[i].clone();
            if(mode==='swing') {
              const delta=(interaction.openRotation[1]-interaction.closedRotation[1])*progress;
              const pivot=interaction.pivot;
              const move=new THREE.Matrix4().makeTranslation(...pivot)
                .multiply(new THREE.Matrix4().makeRotationY(delta))
                .multiply(new THREE.Matrix4().makeTranslation(...pivot.map(v=>-v)));
              expected.premultiply(move);
            } else expected.premultiply(new THREE.Matrix4().makeTranslation(...interaction.openOffset.map(v=>v*progress)));
            mesh.matrix.elements.forEach((v,j)=>maxError=Math.max(maxError,Math.abs(v-expected.elements[j])));
          });
          if(members.every(m=>Math.abs((m.userData.interactionProgress||0)-target)<1e-9)) break;
          if(tick===119) throw Error('animation timeout');
        }
      }
      if(maxError>1e-7) throw Error('non-rigid leaf '+variant+'/'+mode+' '+maxError);
      frames.forEach((m,i)=>{if(JSON.stringify(m.matrix.toArray())!==JSON.stringify(fixed[i]))throw Error('frame moved')});
      members.forEach((m,i)=>[...m.position.toArray(),...m.quaternion.toArray()].forEach((v,j)=>{
        if(Math.abs(v-closed[i][j])>1e-12)throw Error('close did not restore transform');
      }));
      if(JSON.stringify(presentationTest.scene.document.blueprint)!==source)throw Error('source mutated');
      results.push({type:variant,mode,parts:members.length,maxError,samples});
    }
    return results;
  })()`)

  production = await preview({ root, logLevel: 'error', preview: { host: '127.0.0.1', port: 0 } })
  const productionOrigin = production.resolvedUrls.local[0]
  await p.send('Page.navigate', { url: productionOrigin })
  await p.wait('document.readyState === "complete"')
  const assets = await readdir(join(root, 'dist/assets'))
  const workerFile = assets.find(name => /^reconstruction\.worker-.*\.js$/.test(name))
  assert.ok(workerFile, '先运行 npm run build 生成生产 Worker')
  const solidSource = JSON.parse(await readFile(join(pack, '穹庭自然研学馆-新实体建筑示例.wild'), 'utf8'))
  report.productionWorker = await p.evaluate(`new Promise((resolve,reject)=>{
    const worker=new Worker(${JSON.stringify('assets/' + workerFile)},{type:'module'});
    const timeout=setTimeout(()=>{worker.terminate();reject(Error('worker timeout'))},20000);
    worker.onerror=event=>{clearTimeout(timeout);worker.terminate();reject(Error(event.message))};
    worker.onmessage=event=>{clearTimeout(timeout);worker.terminate();
      const {entity,error}=event.data;if(error)return reject(Error(error));
      resolve({meshes:entity.meshes.length,hidden:entity.hiddenElementIds.length,
        errors:entity.diagnostics.filter(d=>d.level==='error')});
    };
    worker.postMessage({requestId:1,blueprint:${JSON.stringify(solidSource)}});
  })`)
  assert.ok(report.productionWorker.meshes > 0)
  assert.deepEqual(report.productionWorker.errors, [])
  assert.deepEqual(p.errors, [])
  await writeFile(
    join(output, 'browser-smoke.json'),
    JSON.stringify({ ok: true, ...report, errors: p.errors }, null, 2) + '\n'
  )
  console.log(JSON.stringify({ ok: true, ...report }))
} finally {
  await browser.close()
  await server.close()
  await new Promise(resolve => (production ? production.httpServer.close(resolve) : resolve()))
}
