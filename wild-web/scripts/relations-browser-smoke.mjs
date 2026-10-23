import assert from 'node:assert/strict'
import { resolve } from 'node:path'
import { mkdir, writeFile } from 'node:fs/promises'
import { launchEditorBrowser } from './editor-browser.mjs'

const output = resolve('../deliveries/component-relations')
await mkdir(output, { recursive: true })
const browser = await launchEditorBrowser(process.env.EDITOR_URL || 'http://127.0.0.1:5178/')
const p = browser.page
const viewport = code => p.evaluate(`(async()=>{const s=document.querySelector('.canvas-viewport').__vueParentComponent.setupState;${code}})()`)
const fixture = { meta: {version:'1.1',type:'building',name:'源构件身份与宿主依附'}, geometry: {
  elements: [
    {id:'wall',type:'wall',from:[-4,0,0],to:[4,3,0],thickness:.2,material:'stone'},
    {id:'floor',type:'floor',from:[-5,-.2,-1],to:[5,-.2,5],thickness:.2,material:'stone'},
  ], components: [
    {id:'window',type:'window',parentWall:'wall',from:[2,1,0],width:2,height:1.2,frameMaterial:'frame',glassMaterial:'glass'},
    {id:'rail',type:'railing',parentFloor:'floor',path:[[1,0,3],[4,0,3]],height:1,material:'frame'},
  ],
}, materials: {
  stone:{baseColor:[.7,.65,.55],roughness:.8,metallic:0,albedo:1},
  frame:{baseColor:[.15,.2,.2],roughness:.4,metallic:.4,albedo:1},
  glass:{baseColor:[.8,.9,.92],roughness:.08,metallic:0,albedo:1,materialClass:'glass',transmission:.9},
} }
try {
  await p.wait('!!document.querySelector(".enter-button")')
  await p.evaluate(`(()=>{const input=document.querySelector('input[aria-label="访客名称"]');input.value='宿主与源身份回归';input.dispatchEvent(new Event('input',{bubbles:true}))})()`)
  await p.click('.enter-button')
  await p.wait('!!document.querySelector(".canvas-viewport canvas")')
  await p.wait('!!document.querySelector(".canvas-viewport").__vueParentComponent.setupState.sceneStore.reconstructed && !document.querySelector(".canvas-viewport").__vueParentComponent.setupState.sceneStore.isReconstructing')
  const loaded = await viewport(`return s.sceneStore.loadBlueprint(${JSON.stringify(fixture)});`)
  assert.equal(loaded, true, JSON.stringify({state:await viewport('return JSON.parse(JSON.stringify({issues:s.sceneStore.validationIssues,diagnostics:s.sceneStore.reconstructed?.diagnostics}));'),errors:p.errors}))
  await p.wait('!document.querySelector(".canvas-viewport").__vueParentComponent.setupState.sceneStore.isReconstructing')
  await p.evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
  const point = await viewport(`
    const mapping=s.sceneStore.reconstructed.componentMapping;let glass;
    s.sceneGroup.traverse(object=>{if(object.isMesh&&mapping.componentIdByGeneratedElementId[object.userData.elementId]==='window'&&object.material?.transmission>0)glass=object});
    if(!glass)throw Error('没有窗玻璃网格');glass.geometry.computeBoundingBox();
    const point=glass.geometry.boundingBox.getCenter(s.sceneBoundsCenter.clone()).applyMatrix4(glass.matrixWorld).project(s.camera);
    const rect=s.renderer.domElement.getBoundingClientRect();return {x:rect.x+(point.x+1)*rect.width/2,y:rect.y+(1-point.y)*rect.height/2};`)
  await p.send('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...point})
  await p.send('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...point})
  await p.wait('document.querySelector(".canvas-viewport").__vueParentComponent.setupState.selectionStore.selectedIds[0]==="window"')
  assert.deepEqual(await viewport('return [...s.selectionStore.selectedIds];'),['window'])
  if (!await p.evaluate('document.querySelector(".property-panel")?.getBoundingClientRect().width>100 && document.querySelector(".dock-panel")?.getBoundingClientRect().width>100')) await p.click('button[aria-label="属性"]')
  await p.wait('document.querySelector(".property-panel")?.getBoundingClientRect().width>100 && document.querySelector(".dock-panel")?.getBoundingClientRect().width>100')
  assert.ok(await p.evaluate('document.querySelector(".property-panel").textContent.includes("沿墙距离")'))
  const originalGenerated = await viewport('return [...s.sceneStore.reconstructed.componentMapping.generatedElementIdsByComponentId.window];')
  await p.evaluate(`(()=>{const row=[...document.querySelectorAll('.property-row')].find(row=>row.querySelector('label')?.textContent==='宽度');const input=row.querySelector('input');input.value='2.4';input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}));})()`)
  await p.wait('document.querySelector(".canvas-viewport").__vueParentComponent.setupState.sceneStore.document.blueprint.geometry.components.find(c=>c.id==="window").width===2.4')
  await p.wait('!document.querySelector(".canvas-viewport").__vueParentComponent.setupState.sceneStore.isReconstructing')
  assert.deepEqual(await viewport('return [...s.selectionStore.selectedIds];'),['window'])
  assert.deepEqual(await viewport('return [...s.sceneStore.reconstructed.componentMapping.generatedElementIdsByComponentId.window];'),originalGenerated)
  await p.click('button[aria-label="撤销"]')
  await p.wait('document.querySelector(".canvas-viewport").__vueParentComponent.setupState.sceneStore.document.blueprint.geometry.components.find(c=>c.id==="window").width===2')
  assert.deepEqual(await viewport('return [...s.selectionStore.selectedIds];'),['window'])
  await p.screenshot(output+'/01-玻璃选择与源参数编辑.png')
  await p.click('button[aria-label="场景树"]')
  await p.wait('!!document.querySelector("[data-source-id=window]")')
  const indents = await p.evaluate(`['wall','window','floor','rail'].map(id=>({id,padding:parseInt(document.querySelector('[data-source-id="'+id+'"]').style.paddingLeft)}))`)
  assert.ok(indents[1].padding>indents[0].padding&&indents[3].padding>indents[2].padding)
  await p.click('button[aria-label="收起 wall 的依附构件"]')
  assert.equal(await p.evaluate('!!document.querySelector("[data-source-id=window]")'),false)
  await p.click('button[aria-label="展开 wall 的依附构件"]')
  await p.screenshot(output+'/02-宿主依附场景树.png')
  const result=await viewport(`
    const {createGeometryTranslationOperations}=await import('/src/wild/componentDrag.ts');
    const {createPatch}=await import('/src/wild/scenePatch.ts');
    s.selectionStore.setSelection(['floor','rail']);const original=s.sceneStore.document.blueprint.geometry.components.find(c=>c.id==='rail').path.map(p=>[...p]);
    const operations=createGeometryTranslationOperations(s.sceneStore.document.blueprint,['floor','rail'],[1,.5,0]);
    await s.sceneStore.applyPatch(createPatch(s.sceneStore.document.revision,operations,'user',false,'移动楼板与栏杆'));
    return JSON.parse(JSON.stringify({original,path:s.sceneStore.document.blueprint.geometry.components.find(c=>c.id==='rail').path,operations:operations.map(op=>op.id),selected:[...s.selectionStore.selectedIds]}));`)
  assert.deepEqual(result.path,result.original)
  assert.deepEqual(result.operations,['floor'])
  await p.click('button[aria-label="撤销"]')
  await p.wait('document.querySelector(".canvas-viewport").__vueParentComponent.setupState.sceneStore.document.blueprint.geometry.elements.find(e=>e.id==="floor").from[0]===-5')
  await viewport(`const {createPatch}=await import('/src/wild/scenePatch.ts');s.selectionStore.setSelection(['rail']);await s.sceneStore.applyPatch(createPatch(s.sceneStore.document.revision,[{op:'remove_element',id:'floor'}],'user',false,'删除楼板'));return true;`)
  assert.deepEqual(await viewport('return [...s.selectionStore.selectedIds];'),[])
  assert.equal(await viewport('return s.sceneStore.document.blueprint.geometry.components.some(c=>c.id==="rail");'),false)
  await p.click('button[aria-label="撤销"]')
  await p.wait('document.querySelector(".canvas-viewport").__vueParentComponent.setupState.sceneStore.document.blueprint.geometry.components.some(c=>c.id==="rail")')
  assert.deepEqual(p.errors,[])
  const report={status:'PASS',glassSelectsSource:true,widthEditPreservesSourceId:true,oneUndoRestoresWidth:true,hostTreeCollapsible:true,floorAndChildMoveOnce:true,cascadeDeletionAndUndo:true,staleSelectionRemoved:true,errors:p.errors}
  await writeFile(output+'/浏览器验证.json',JSON.stringify(report,null,2))
  console.log(JSON.stringify(report,null,2))
} finally { await browser.close() }
