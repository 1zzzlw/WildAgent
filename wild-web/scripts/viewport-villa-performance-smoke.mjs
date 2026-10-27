import assert from 'node:assert/strict'
import { readFile, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { launchEditorBrowser } from './editor-browser.mjs'

const output='../docs/10月27日/渲染性能光影与三种别墅',manifest=JSON.parse(await readFile(output+'/生成清单.json','utf8'))
const browser=await launchEditorBrowser('http://127.0.0.1:5178/'),p=browser.page
const viewport=code=>p.evaluate(`(()=>{const s=document.querySelector('.canvas-viewport').__vueParentComponent.setupState;${code}})()`)
try {
 await p.wait('!!document.querySelector(".enter-button")')
 await p.evaluate(`(()=>{const el=document.querySelector('input[aria-label="访客名称"]');el.value='三案与休眠验收';el.dispatchEvent(new Event('input',{bubbles:true}))})()`)
 await p.click('.enter-button');await p.wait('!!document.querySelector(".canvas-viewport canvas")')
 const imports=[]
 for(const record of manifest.records) {
  const source=JSON.parse(await readFile(output+'/'+record.directory+'/'+record.file,'utf8'))
  await p.upload('input[type=file]',resolve(output+'/'+record.directory+'/'+record.file))
  await p.wait('document.querySelector(".save-state")?.textContent.includes("已保存")',60000)
  await p.wait(`document.querySelector('.canvas-viewport').__vueParentComponent.setupState.sceneStore.document?.blueprint.meta.name===${JSON.stringify(source.meta.name)}`)
  const session=await p.evaluate(`import('/src/stores/agentStore.ts').then(m=>m.useAgentStore().currentSessionId)`)
  const stored=await p.evaluate(`fetch('/api/editor-smoke-storage').then(r=>r.json()).then(rows=>Object.entries(rows).find(([key])=>key.includes(${JSON.stringify(session)}))?.[1])`)
  assert.deepEqual(stored.geometry,source.geometry,'保存不能改变源几何/交互参数')
  assert.deepEqual(stored.materials,source.materials,'保存不能丢失完整材质配方')
  assert.deepEqual(stored.meta,{...source.meta,version:'1.0'},'遵守现有1.1导入归一到1.0的协议')
  assert.ok(Number.isInteger(stored.editor.revision))
  assert.equal(await viewport(`return s.sceneStore.loadBlueprint(${JSON.stringify(stored)})`),true)
  const stats=await viewport('return {meshes:s.sceneStore.reconstructed.meshes.length,errors:s.sceneStore.reconstructed.diagnostics.filter(d=>d.level==="error")}')
  assert.deepEqual(stats.errors,[]);imports.push({name:record.name,persisted:true,reopened:true,...stats})
 }
 await p.upload('input[type=file]',resolve('scripts/fixtures/render-upgrade.json'))
 await p.wait('document.querySelector(".canvas-viewport").__vueParentComponent.setupState.waterReflection.surfaces.length>0')
 await viewport("s.renderPanel.requestPreset({type:'quality',value:'medium'});return true")
 await p.wait('!document.querySelector(".canvas-viewport").__vueParentComponent.setupState.waterReflection.enabled')
 await viewport("s.renderPanel.requestPreset({type:'quality',value:'high'});return true")
 await p.wait('document.querySelector(".canvas-viewport").__vueParentComponent.setupState.waterReflection.enabled')
 await p.evaluate(`Promise.all([import('/src/renderer/worldEffectRuntime.ts').then(m=>m.updateWorldEffectState({clouds:false,ripples:false})),import('/src/renderer/worldEnvironmentRuntime.ts').then(m=>m.updateWorldRenderingState({weatherEnabled:false}))])`)
 await viewport(`s.renderPanel.requestPreset({type:'view',value:'presentation'});s.renderPanel.autoRotate=false;s.controls.autoRotate=false;s.controls.enableDamping=false;
  const water=s.waterReflection.surfaces[0];water.updateWorldMatrix(true,false);const box=water.geometry.boundingBox.clone().applyMatrix4(water.matrixWorld),point=box.getCenter(s.camera.position.clone());
  s.camera.position.set(point.x+5,point.y+5,point.z+8);s.controls.target.copy(point);s.controls.update();s.markNeedsRender();return true`)
 await p.wait('document.querySelector(".canvas-viewport").__vueParentComponent.setupState.waterReflection.hasVisibleSurface(document.querySelector(".canvas-viewport").__vueParentComponent.setupState.camera)')
 await p.evaluate('new Promise(r=>setTimeout(r,150))')
 const visible=await viewport('return {continuous:s.continuousFrame,queued:s.animationFrameId!==null}')
 assert.deepEqual(visible,{continuous:true,queued:true})
 await viewport(`const point=s.controls.target.clone();s.camera.position.set(point.x,point.y+4,point.z+10);s.controls.target.set(point.x,point.y+4,point.z+50);s.controls.update();s.markNeedsRender();return true`)
 await p.wait('document.querySelector(".canvas-viewport").__vueParentComponent.setupState.animationFrameId===null')
 const asleep=await viewport('return {continuous:s.continuousFrame,queued:s.animationFrameId!==null,waterVisible:s.waterReflection.hasVisibleSurface(s.camera)}')
 assert.deepEqual(asleep,{continuous:false,queued:false,waterVisible:false})
 assert.deepEqual(p.errors,[])
 const result={status:'PASS',imports,allowedNormalization:'meta.version 1.1→1.0，并写入编辑器revision；geometry/materials逐项保持',mediumReflectionOffHighOn:true,visibleWaterAnimates:visible,offscreenWaterSleeps:asleep,shaderErrors:p.errors}
 await writeFile(output+'/验证/三案编辑器与离屏休眠.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2))
}finally{await browser.close()}
