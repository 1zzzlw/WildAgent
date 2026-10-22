import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { launchEditorBrowser } from './editor-browser.mjs'

const url = process.env.EDITOR_URL || 'http://127.0.0.1:5178'
const output = join(tmpdir(), 'wild-render-details')
const fixture = JSON.parse(await readFile(new URL('./fixtures/render-details.json', import.meta.url), 'utf8'))
let browser = await launchEditorBrowser(url + '/scripts/render-details-preview.html')
try {
  const p = browser.page
  await p.wait('window.ready')
  await p.wait(`(()=>{let ready=true;group.traverse(o=>{if(o.name==='TextLabel'&&!o.material.map?.image?.complete)ready=false});return ready})()`)
  assert.deepEqual(await p.evaluate('entity.diagnostics.filter(d=>d.level==="error")'), [])
  assert.equal(await p.evaluate('lamps.length'), 3)
  const positions = await p.evaluate(`lamps.map(o=>({id:o.userData.elementId,source:o.children.find(c=>c.userData.fixtureLight).getWorldPosition(o.position.clone()).toArray()}))`)
  for (const [prefix, expected] of [['lamp', [0,1.35,0.7]], ['strip', [2.4,1.2,0]], ['body_lamp', [-2,1.2,0]]]) {
    const source = positions.find(row=>row.id.startsWith(prefix)).source
    source.forEach((value, axis)=>assert.ok(Math.abs(value-expected[axis])<1e-5, JSON.stringify(positions)))
  }
  assert.equal(await p.evaluate(`(()=>{const roundTrip=parse(JSON.stringify(blueprint));return roundTrip.geometry.elements.find(e=>e.id==='sign').label.text})()`), '栖光别墅')
  await p.evaluate('window.day(true)')
  await p.screenshot(join(output,'01-中文招牌-白天.png'))
  await p.evaluate(`(()=>{let label;group.traverse(o=>{if(o.name==='TextLabel')label=o});const c=document.createElement('canvas');c.width=label.material.map.image.width;c.height=label.material.map.image.height;const ctx=c.getContext('2d');ctx.drawImage(label.material.map.image,0,0);window.labelImage=ctx.getImageData(0,0,c.width,c.height).data;})()`)
  assert.ok(await p.evaluate('Array.from(labelImage).filter((v,i)=>i%4===3&&v>0).length>1000'), '中文招牌必须包含实际印字像素')
  await p.evaluate('window.day(false);window.toggleAll()')
  await p.wait('lamps.every(o=>o.userData.lightLevel===2)')
  await p.evaluate(`(()=>{window.frame();window.litPixels=window.readPixels();const point=scene.position.clone().set(0,0.01,1.8).project(camera);window.floorSample={x:Math.round((point.x+1)*renderer.domElement.width/2),y:Math.round((1-point.y)*renderer.domElement.height/2)}})()`)
  await p.screenshot(join(output,'02-自制灯具-夜景照明.png'))
  await p.evaluate('window.toggleAll()')
  await p.wait('lamps.every(o=>o.userData.lightLevel===0)')
  const illumination = await p.evaluate(`(()=>{window.frame();const dark=readPixels();const width=renderer.domElement.width;let on=0,off=0,n=0;for(let y=floorSample.y-15;y<floorSample.y+15;y++)for(let x=floorSample.x-15;x<floorSample.x+15;x++){const i=(y*width+x)*4;on+=litPixels[i]+litPixels[i+1]+litPixels[i+2];off+=dark[i]+dark[i+1]+dark[i+2];n+=3}return {on:on/n,off:off/n}})()`)
  assert.ok(illumination.on > illumination.off + 20, '灯具必须照亮远离灯罩的地面：'+JSON.stringify(illumination))

  // 覆盖旧文件默认水参数与显式不透射参数，不能用默认 0 覆盖“未填写”。
  const water = await p.evaluate(`(async()=>{const bp={meta:{version:'1.1',type:'asset',name:'水材质'},geometry:{elements:[{type:'primitive',id:'w',shape:'box',dimensions:[1,.1,1],material:'water'}]},materials:{water:{baseColor:[.2,.5,.4],roughness:.06,metallic:0,albedo:1,lightingCondition:'D65_noon'}}};const first=(await reconstruct(bp)).materialParams[0];bp.materials.water.transmission=0;const second=(await reconstruct(bp)).materialParams[0];return {transmission:first.transmission,ior:first.ior,explicit:second.transmission}})()`)
  assert.ok(water.transmission > 0.9);assert.equal(water.ior,1.333);assert.equal(water.explicit,0)
  const invalid = await p.evaluate(`(async()=>{const bp=structuredClone(blueprint);bp.geometry.elements.find(e=>e.id==='lamp').lightSource.intensity=-1;return (await reconstruct(bp)).diagnostics.some(d=>d.level==='error')})()`)
  assert.equal(invalid,true,'非法光源应产生诊断')
  assert.deepEqual(p.errors,[])
  console.log('PASS literal Chinese signage, round-trip, custom/body/sweep lights and real floor illumination',illumination)
} finally { await browser.close() }

browser = await launchEditorBrowser(url)
try {
  const p = browser.page
  await p.wait('!!document.querySelector(".enter-button")')
  await p.evaluate(`(()=>{const el=document.querySelector('input[aria-label="访客名称"]');el.value='渲染细节回归';el.dispatchEvent(new Event('input',{bubbles:true}))})()`)
  await p.click('.enter-button')
  await p.wait('!!document.querySelector(".canvas-viewport canvas")')
  const viewport = code=>p.evaluate(`(()=>{const s=document.querySelector('.canvas-viewport').__vueParentComponent.setupState;${code}})()`)
  const nextFrame = ()=>p.evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')
  // 新建独立草稿，阻止启动时的服务器会话恢复覆盖本回归场景。
  await p.evaluate(`document.querySelector('.wild-editor').__vueParentComponent.setupState.workspace.newScene()`)
  const loaded = await viewport(`return s.sceneStore.loadBlueprint(${JSON.stringify(fixture)});`)
  if (!loaded) console.log('LOAD_DIAGNOSTICS',await viewport('return JSON.stringify({name:s.sceneStore.document?.name,reconstructing:s.sceneStore.isReconstructing,issues:s.sceneStore.validationIssues,diagnostics:s.sceneStore.reconstructed?.diagnostics});'),p.errors)
  assert.equal(loaded,true)
  await p.click('button[aria-label="渲染面板"]');await p.click('button[aria-label="渲染信息"]')
  await p.wait('!!document.querySelector("[aria-label=场景占地尺寸]")')
  assert.equal(await p.evaluate('document.querySelector("[aria-label=场景占地尺寸]").textContent'),'16×16 m')
  assert.equal(await p.evaluate('document.querySelector("[aria-label=地面网格尺寸]").textContent'),'32×32 m · 1 m/格')
  await p.evaluate(`(()=>{const e=document.querySelector('input[aria-label="水面透明度"]');e.value='0.45';e.dispatchEvent(new Event('input',{bubbles:true}))})()`)
  await p.wait('JSON.parse(localStorage.getItem("wild_water_appearance_v1")).transparency===0.45')
  await p.evaluate(`(()=>{const e=document.querySelector('input[aria-label="波纹强度"]');e.value='0.3';e.dispatchEvent(new Event('input',{bubbles:true}))})()`)
  await p.wait('JSON.parse(localStorage.getItem("wild_water_appearance_v1")).waveStrength===0.3')
  await p.screenshot(join(output,'03-渲染信息与水面设置.png'))
  for (const [size,grid,step] of [[32,64,1],[129,256,2]]) {
    const bp=structuredClone(fixture);bp.geometry.elements[0].from=[0,-.2,0];bp.geometry.elements[0].to=[size,-.2,size]
    // 使用只包含地板的场景，避免其它构件影响占地范围。
    bp.geometry.elements=bp.geometry.elements.slice(0,1);bp.geometry.components=[]
    await viewport(`return s.sceneStore.loadBlueprint(${JSON.stringify(bp)});`);await nextFrame()
    assert.deepEqual(await viewport('return {...s.renderPanel.sceneDimensions};'),{width:size,depth:size,gridSize:grid,gridStep:step})
    assert.equal(await viewport('s.gridHelper.geometry.computeBoundingBox();return s.gridHelper.geometry.boundingBox.max.x-s.gridHelper.geometry.boundingBox.min.x;'),grid)
  }
  await viewport('return s.sceneStore.loadBlueprint(s.sceneStore.createEmptyDocument().blueprint);');await nextFrame()
  assert.equal(await p.evaluate('document.querySelector("[aria-label=场景占地尺寸]").textContent'),'—')
  assert.equal(await p.evaluate('document.querySelector("[aria-label=地面网格尺寸]").textContent'),'16×16 m · 1 m/格')

  await viewport(`return s.sceneStore.loadBlueprint(${JSON.stringify(fixture)});`);await nextFrame()
  await viewport(`s.selectionStore.setSelection(['sign']);s.uiStore.openPanel('properties');`)
  await p.wait('!!document.querySelector("input[aria-label=招牌文字]")')
  await p.evaluate(`(()=>{const e=document.querySelector('input[aria-label="招牌文字"]');e.value='听雨山房';e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}))})()`)
  await p.wait('document.querySelector(".save-state")?.textContent.includes("未保存")')
  await nextFrame()
  assert.equal(await viewport(`return JSON.parse(JSON.stringify(s.sceneStore.document.blueprint)).geometry.elements.find(e=>e.id==='sign').label.text;`),'听雨山房')
  await p.click('button[aria-label="撤销"]');await nextFrame()
  assert.equal(await viewport(`return s.sceneStore.document.blueprint.geometry.elements.find(e=>e.id==='sign').label.text;`),'栖光别墅')
  await viewport(`s.selectionStore.setSelection(['lamp']);`);await nextFrame()
  await p.click('.property-panel .el-switch');await nextFrame()
  await p.wait(`!document.querySelector('.canvas-viewport').__vueParentComponent.setupState.sceneStore.isReconstructing`)
  assert.equal(await viewport(`return !!s.sceneStore.document.blueprint.geometry.elements.find(e=>e.id==='lamp').lightSource;`),false)
  await p.click('.property-panel .el-switch');await nextFrame()
  assert.equal(await viewport(`return s.sceneStore.document.blueprint.geometry.elements.find(e=>e.id==='lamp').lightSource.initiallyOn;`),true)
  assert.deepEqual(p.errors,[])
  console.log('PASS grid bounds/cell size/reset, live water settings, signage edit/undo, custom light switch; images:',output)
} finally { await browser.close() }
