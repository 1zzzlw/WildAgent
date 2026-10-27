import assert from 'node:assert/strict'
import { resolve } from 'node:path'
import { readFile, writeFile } from 'node:fs/promises'
import { launchEditorBrowser } from './editor-browser.mjs'

const output='../docs/10月27日/验证',browser=await launchEditorBrowser('http://127.0.0.1:5178/')
const p=browser.page
const viewport=code=>p.evaluate(`(()=>{const s=document.querySelector('.canvas-viewport').__vueParentComponent.setupState;${code}})()`)
try{
 await p.wait('!!document.querySelector(".enter-button")')
 await p.evaluate(`(()=>{const el=document.querySelector('input[aria-label="访客名称"]');el.value='材质与设备验收';el.dispatchEvent(new Event('input',{bubbles:true}))})()`)
 await p.click('.enter-button');await p.wait('!!document.querySelector(".canvas-viewport canvas")')
 const source=JSON.parse(await readFile('../docs/10月27日/岚石光庭-交互材质别墅.wild','utf8'))
 await p.upload('input[type=file]',resolve('../docs/10月27日/岚石光庭-交互材质别墅.wild'))
 await p.wait('document.querySelector(".save-state")?.textContent.includes("已保存")',60000)
 await p.wait('document.querySelector(".canvas-viewport").__vueParentComponent.setupState.sceneStore.reconstructed?.meshes.length>500')
 const sessionId=await p.evaluate(`import('/src/stores/agentStore.ts').then(m=>m.useAgentStore().currentSessionId)`)
 const stored=await p.evaluate(`fetch('/api/editor-smoke-storage').then(r=>r.json()).then(rows=>Object.entries(rows).find(([key])=>key.includes(${JSON.stringify(sessionId)}))?.[1])`)
 assert.deepEqual(stored.materials,source.materials,'库配方保存后不能变成只有颜色')
 assert.deepEqual(stored.geometry.components,source.geometry.components)
 assert.equal(await viewport(`return s.sceneStore.loadBlueprint(${JSON.stringify(stored)})`),true)
 await p.wait('document.querySelector(".canvas-viewport").__vueParentComponent.setupState.sceneStore.reconstructed?.meshes.length>500')
 assert.equal(await viewport('return s.sceneStore.reconstructed.diagnostics.filter(d=>d.level==="error").length'),0)
 const asset={meta:{version:'1.1',type:'asset',name:'设备按钮编辑器验收'},geometry:{elements:[],components:[
  {type:'elevator',id:'lift',position:[-1.8,0,0],dimensions:{width:1.8,depth:1.8,height:2.5},floorHeight:3.2,floorCount:3},
  {type:'fan',id:'fan',position:[2,2.6,0],controlPosition:[2,1.1,1],radius:.65}
 ]},materials:{}}
 assert.equal(await viewport(`return s.sceneStore.loadBlueprint(${JSON.stringify(asset)})`),true)
 await p.wait('!!document.querySelector(".canvas-viewport").__vueParentComponent.setupState.sceneGroup?.getObjectByName("lift__cab")')
 await viewport("s.renderPanel.requestPreset({type:'view',value:'presentation'});s.renderPanel.requestPreset({type:'quality',value:'high'});s.controls.autoRotate=false;s.controls.enableDamping=false;s.camera.position.set(-1.8,1.55,4.8);s.controls.target.set(-1.8,1.3,0);s.controls.update();s.markShadowsDirty();return true")
 const original=await viewport('return {revision:s.sceneStore.document.revision,blueprint:JSON.stringify(s.sceneStore.document.blueprint)}')
 const point=async id=>viewport(`const mesh=s.sceneGroup.getObjectByName(${JSON.stringify(id)}),point=mesh.getWorldPosition(mesh.position.clone()).project(s.camera),r=s.renderer.domElement.getBoundingClientRect();return {x:r.x+(point.x*.5+.5)*r.width,y:r.y+(-point.y*.5+.5)*r.height}`)
 const click=async id=>{
  let position=await point(id),stable=0
  for(let i=0;i<30&&stable<3;i++){
   await new Promise(resolve=>setTimeout(resolve,80));const next=await point(id)
   stable=Math.hypot(next.x-position.x,next.y-position.y)<.5?stable+1:0;position=next
  }
  assert.equal(stable,3,'点击前投影位置应稳定')
  await p.send('Input.dispatchMouseEvent',{type:'mouseMoved',...position})
  await p.send('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...position})
  await p.send('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...position})
 }
 await click('lift__hall_0')
 await p.wait('document.querySelector(".canvas-viewport").__vueParentComponent.setupState.sceneGroup.getObjectByName("lift__cab_door_1").userData.elevatorDoorProgress===1')
 await p.screenshot(resolve(output+'/编辑器-电梯按钮与开门.png'))
 await click('lift__car_button_2')
 await p.wait('document.querySelector(".canvas-viewport").__vueParentComponent.setupState.sceneGroup.getObjectByName("lift__cab").userData.elevatorPhase==="moving"')
 await p.wait('document.querySelector(".canvas-viewport").__vueParentComponent.setupState.sceneGroup.getObjectByName("lift__cab").userData.elevatorFloor===2',45000)
 await p.wait('document.querySelector(".canvas-viewport").__vueParentComponent.setupState.sceneGroup.getObjectByName("lift__cab_door_1").userData.elevatorDoorProgress===1')
 await click('lift__hall_0')
 await p.wait('document.querySelector(".canvas-viewport").__vueParentComponent.setupState.sceneGroup.getObjectByName("lift__cab").userData.elevatorFloor===0',45000)
 await viewport('s.camera.position.set(2,1.6,4.5);s.controls.target.set(2,1.5,0);s.controls.update();s.markNeedsRender();return true')
 await click('fan__control')
 await p.wait('document.querySelector(".canvas-viewport").__vueParentComponent.setupState.sceneGroup.getObjectByName("fan__hub").userData.rotorSpeed>1')
 const first=await viewport('return s.sceneGroup.getObjectByName("fan__blade_0").position.toArray()')
 await p.wait('document.querySelector(".canvas-viewport").__vueParentComponent.setupState.sceneGroup.getObjectByName("fan__hub").userData.rotorSpeed>5')
 assert.notDeepEqual(await viewport('return s.sceneGroup.getObjectByName("fan__blade_0").position.toArray()'),first)
 await click('fan__control');assert.equal(await viewport('return s.sceneGroup.getObjectByName("fan__hub").userData.rotorLevel'),2)
 await click('fan__control')
 await p.wait('document.querySelector(".canvas-viewport").__vueParentComponent.setupState.sceneGroup.getObjectByName("fan__hub").userData.rotorSpeed===0')
 await p.wait('document.querySelector(".canvas-viewport").__vueParentComponent.setupState.animationFrameId===null')
 const current=await viewport('return {revision:s.sceneStore.document.revision,blueprint:JSON.stringify(s.sceneStore.document.blueprint)}')
 assert.deepEqual(current,original,'运行设备不能改写 WILD 或增加撤销历史')
 await viewport("s.selectionStore.select('fan');s.uiStore.openPanel('properties');return true")
 await p.wait('document.querySelector(".property-panel")?.textContent.includes("吊扇参数")')
 await p.evaluate(`(()=>{const row=[...document.querySelectorAll('.property-row')].find(r=>r.querySelector('label')?.textContent==='扇叶半径'),input=row.querySelector('input');input.value='0.75';input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}));input.dispatchEvent(new FocusEvent('blur',{bubbles:true}));return true})()`)
 await p.wait('document.querySelector(".canvas-viewport").__vueParentComponent.setupState.sceneStore.document.blueprint.geometry.components.find(c=>c.id==="fan").radius===0.75')
 await p.screenshot(resolve(output+'/编辑器-风扇参数面板.png'))
 assert.deepEqual(p.errors,[])
 const result={status:'PASS',villaImportedAndPersisted:true,allMaterialRecipesPreserved:true,realEditorLeftClicks:true,elevatorRoundTrip:[0,2,0],fanLowHighOff:true,idleRenderSleeps:true,blueprintAndRevisionUnchanged:true,fanParameterEditedThroughUi:true,errors:p.errors}
 await writeFile(output+'/完整编辑器验收.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2))
}catch(error){await p.screenshot(resolve(output+'/编辑器-失败诊断.png'));console.log(await viewport('return {camera:s.camera.position.toArray(),target:s.controls.target.toArray(),fan:s.sceneGroup.getObjectByName("fan__control")?.userData.rotorLevel,view:s.viewMode}'));throw error}finally{await browser.close()}
