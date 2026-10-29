import assert from 'node:assert/strict'
import { readFile, mkdir, writeFile } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { resolve } from 'node:path'
import { launchEditorBrowser } from './editor-browser.mjs'

const before = process.argv.includes('--record-before')
const output = resolve('../docs/10月30日/微缩背景修复')
await mkdir(output, { recursive:true })
const raw = await readFile(resolve('../docs/10月30日/双场景创作与引擎优化/汐见电车站/汐见电车站-海边暮色.wild'), 'utf8')
const blueprint = JSON.parse(raw)
const browser = await launchEditorBrowser(`${process.env.EDITOR_URL || 'http://127.0.0.1:5196'}/scripts/presentation-preview.html`)
const p = browser.page
const view = code => p.evaluate(`(()=>{const s=document.querySelector('.canvas-viewport').__vueParentComponent.setupState;${code}})()`)
const load = async b => {
  assert.equal(await p.evaluate(`presentationTest.scene.loadBlueprint(${JSON.stringify(b)})`), true)
  await view('s.finishEntrance();s.markNeedsRender();return true;')
}
const sample = async hour => {
  await p.evaluate(`import('/src/renderer/worldEnvironmentRuntime.ts').then(m=>m.updateWorldEnvironmentState({timeOfDay:${hour}}))`)
  await p.evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')
  return view(`s.composer.render();const gl=s.renderer.getContext(),w=s.renderer.domElement.width,h=s.renderer.domElement.height;
    const pixels=[[8,8],[w-9,8],[8,h-9]].map(([x,y])=>{const v=new Uint8Array(4);gl.readPixels(x,y,1,1,gl.RGBA,gl.UNSIGNED_BYTE,v);return Array.from(v)});
    const all=new Uint8Array(w*h*4);gl.readPixels(0,0,w,h,gl.RGBA,gl.UNSIGNED_BYTE,all);let opaquePixels=0;for(let i=3;i<all.length;i+=4)if(all[i]===255)opaquePixels++;
    return {background:s.scene.background?.getHexString()??null,pixels,opaquePixels,clearAlpha:s.renderer.getClearAlpha(),contextAlpha:gl.getContextAttributes().alpha,exposure:s.renderer.toneMappingExposure,
      light:s.directionalLight.color.getHexString(),direction:s.keyLightDirection.toArray(),skyVisible:s.sky.visible,environment:s.scene.environment?.uuid};`)
}
try {
  await p.wait('window.ready');await p.resize(1280,960);await load(blueprint)
  await p.send('Emulation.setDefaultBackgroundColorOverride',{color:{r:0,g:0,b:0,a:0}})
  const saved = await view('return JSON.stringify(s.sceneStore.document);')
  const diorama = []
  for (const hour of [10,18.7,22]) {
    diorama.push({hour,...await sample(hour)})
    await p.screenshot(`${output}/${before?'修复前':'修复后'}-${hour}.png`)
  }
  assert.equal(await view('return JSON.stringify(s.sceneStore.document);'),saved)
  assert.equal(new Set(diorama.map(v=>v.light)).size,3,'灯光必须继续随时段改变')
  assert.ok(new Set(diorama.map(v=>v.exposure)).size>1,'模型曝光仍按时段变化')
  if (!before) {
    for(const row of diorama) {
      assert.equal(row.background,null);assert.equal(row.clearAlpha,0);assert.equal(row.contextAlpha,true)
      assert.deepEqual(row.pixels,[[0,0,0,0],[0,0,0,0],[0,0,0,0]],'后期处理之后的背景必须透明')
      assert.ok(row.opaquePixels>10000,'模型仍然可见')
    }
  }
  const world = structuredClone(blueprint);world.presentation.stage='world'
  await load(world)
  const worldSamples = []
  for(const hour of [10,18.7,22]) worldSamples.push({hour,...await sample(hour)})
  assert.equal(new Set(worldSamples.map(v=>v.background)).size,3,'普通世界的背景继续跟随环境')
  assert.deepEqual(worldSamples.map(v=>v.skyVisible),[true,true,false])
  for(const row of worldSamples)assert.ok(row.pixels.every(v=>v[3]===255),'普通世界保持不透明天空')
  await load(blueprint)
  const returned = await sample(18.7)
  if(!before) assert.equal(returned.background,diorama[0].background,'切回微缩舞台恢复固定背景')
  const qualitySamples=[]
  if(!before) for(const quality of ['low','high']) {
    await p.evaluate(`presentationTest.render.requestPreset({type:'quality',value:'${quality}'})`)
    const row={quality,...await sample(22)}
    assert.ok(row.pixels.every(v=>v[3]===0),'不同画质的夜间后期均保留透明背景')
    assert.ok(row.opaquePixels>10000)
    qualitySamples.push(row)
  }
  assert.deepEqual(p.errors,[])
  const report = {phase:before?'before':'after',inputSha256:createHash('sha256').update(raw).digest('hex'),
    diorama,world:worldSamples,returned,qualitySamples,documentUnchanged:true,errors:p.errors}
  await writeFile(`${output}/${before?'修复前':'修复后'}-验证结果.json`,JSON.stringify(report,null,2)+'\n')
  console.log(JSON.stringify(report,null,2))
} finally { await browser.close() }
