import assert from 'node:assert/strict'
import { readFile, mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createHash } from 'node:crypto'
import { launchEditorBrowser } from './editor-browser.mjs'

const output = resolve('../docs/11月1日/通用建筑组装开关')
await mkdir(output, { recursive: true })
const origin = process.env.EDITOR_URL || 'http://127.0.0.1:5196'
const browser = await launchEditorBrowser(`${origin}/scripts/presentation-preview.html?controls`)
const p = browser.page
const viewport = code => p.evaluate(`(()=>{const s=document.querySelector('.canvas-viewport').__vueParentComponent.setupState;${code}})()`)
const state = () => viewport(`const r=s.worldRuntime.getInstance('editor:active-blueprint').assembly;
  return {active:r.active,progress:r.progress,enabled:s.renderPanel.entranceEnabled};`)
const source = () => viewport('return {json:JSON.stringify(s.sceneStore.document.blueprint),revision:s.sceneStore.document.revision,dirty:s.sceneStore.document.dirty};')
const load = async blueprint => {
  assert.equal(await p.evaluate(`presentationTest.scene.loadBlueprint(${JSON.stringify(blueprint)})`), true)
  await p.wait('!presentationTest.scene.isReconstructing')
}
const snapshot = () => viewport(`s.sceneGroup.updateMatrixWorld(true);
  return s.sceneGroup.children.filter(o=>o.isMesh).map(o=>({name:o.name,matrix:o.matrix.toArray(),
    instances:o.isInstancedMesh?Array.from(o.instanceMatrix.array):null,auto:o.matrixAutoUpdate,culling:o.frustumCulled}));`)

try {
  await p.wait('window.ready')
  const legacy = JSON.parse(await readFile(resolve('scripts/fixtures/presentation.json'), 'utf8'))
  await load(legacy)
  const saved = await source()
  assert.equal((await state()).active, true, '普通蓝图由前端开关控制组装')
  await viewport('s.finishEntrance();return true;')
  const complete = await snapshot()
  assert.ok(complete.some(mesh => mesh.instances), '覆盖实际 InstancedMesh')

  // 从真实工具栏打开设置，再通过真实鼠标事件操作开关。
  await p.click('[aria-label="渲染面板"]')
  await p.click('[aria-label="渲染信息"]')
  assert.equal(await p.evaluate(`(()=>{const el=document.querySelector('.render-details');return el.scrollWidth<=el.clientWidth})()`), true, '设置面板没有横向溢出')
  const toggle = '.rc-toggle[title^="载入建筑"]'
  await p.click(toggle)
  assert.equal((await state()).enabled, false)
  assert.equal(await p.evaluate('document.querySelector(".rc-actions button").disabled'), true)
  await p.screenshot(output + '/01-关闭组装显示完整建筑.png')

  // 模拟按需渲染休眠超过默认动画时长，再打开，第一帧不能直接结束。
  await viewport('s.weatherClock.oldTime=performance.now()-20000;return true;')
  await p.click(toggle)
  assert.equal((await state()).active, true)
  assert.ok((await state()).progress < .3, '休眠时间不能跳过新播放的动画')
  await viewport("s.worldRuntime.getInstance('editor:active-blueprint').assembly.tick(3);s.markNeedsRender();return true;")
  const middle = await snapshot()
  assert.notDeepEqual(middle.filter(m=>!m.instances), complete.filter(m=>!m.instances), '普通网格确实发生变换')
  assert.notDeepEqual(middle.filter(m=>m.instances), complete.filter(m=>m.instances), '实例网格确实发生变换')
  await p.screenshot(output + '/02-通用组装播放中.png')
  await p.click(toggle)
  assert.equal((await state()).active, false)
  assert.deepEqual(await snapshot(), complete, '关闭立即精确恢复完整矩阵和状态')
  assert.deepEqual(await source(), saved)

  // 前端关闭状态跨文件保留。
  const secondBlueprint = JSON.parse(await readFile(resolve('scripts/fixtures/presentation.json'), 'utf8'))
  await load(secondBlueprint)
  assert.equal((await state()).active, false)
  const secondSource = await source()
  const secondComplete = await snapshot()
  await p.click(toggle)
  await viewport("s.worldRuntime.getInstance('editor:active-blueprint').assembly.tick(10);s.markNeedsRender();return true;")
  assert.equal((await state()).active, false, '使用前端固定的 10 秒时长')
  assert.deepEqual(await snapshot(), secondComplete)
  await p.click('.rc-actions button')
  assert.equal((await state()).active, true, '原生按钮能重新播放')
  await p.send('Input.dispatchMouseEvent', { type:'mousePressed',button:'left',buttons:1,x:1100,y:900,clickCount:1 })
  await p.send('Input.dispatchMouseEvent', { type:'mouseReleased',button:'left',buttons:0,x:1100,y:900,clickCount:1 })
  assert.equal((await state()).active, false, '开始操作画布时恢复完整场景')
  assert.deepEqual(await snapshot(), secondComplete)
  assert.deepEqual(await source(), secondSource)

  // 切换建筑时结束旧动画；常规编辑不能再次触发入场。
  await p.evaluate('presentationTest.render.requestReplayEntrance()')
  assert.equal((await state()).active, true)
  await load(legacy)
  assert.equal((await state()).active, true)
  await viewport(`return s.sceneStore.applyPatch({type:'scene_patch',patch_id:'assembly-edit',
    base_revision:s.sceneStore.document.revision,source:'user',mode:'apply',requires_confirmation:false,
    operations:[{op:'update_element',id:'base',changes:{dimensions:[6.2,.4,6]}}]});`)
  assert.equal((await state()).active, false, '编辑重建后不重复入场')

  // 关闭状态在视口重新挂载后仍有效。
  await p.evaluate('presentationTest.render.entranceEnabled=false')
  const beforeRemount = await source()
  await p.evaluate('presentationTest.remount()')
  await p.wait('document.querySelector(".canvas-viewport").__vueParentComponent.setupState.sceneGroup.children.length>0')
  assert.equal((await state()).active, false)
  assert.deepEqual(await source(), beforeRemount)

  // 一份实际建筑：没有入场配置的站房同样能播放并恢复，环境不随开关改变。
  const building = JSON.parse(await readFile(resolve('../docs/10月30日/双场景创作与引擎优化/汐见电车站/汐见电车站-海边暮色.wild'), 'utf8'))
  await load(building)
  const buildingSource = await source()
  const buildingComplete = await snapshot()
  const environment = () => p.evaluate(`import('/src/renderer/worldEnvironmentRuntime.ts').then(m=>JSON.stringify(m.getWorldEnvironmentState()))`)
  const environmentBefore = await environment()
  await p.evaluate('presentationTest.render.entranceEnabled=true')
  await viewport("s.worldRuntime.getInstance('editor:active-blueprint').assembly.tick(4);s.markNeedsRender();return true;")
  assert.equal((await state()).active, true)
  await p.screenshot(output + '/03-海边站房通用组装.png')
  await p.evaluate('presentationTest.render.entranceEnabled=false')
  assert.deepEqual(await snapshot(), buildingComplete)
  assert.deepEqual(await source(), buildingSource)
  assert.equal(await environment(), environmentBefore)
  await p.screenshot(output + '/04-海边站房关闭后.png')
  assert.deepEqual(p.errors, [])
  const sourceSha256 = {}
  for (const file of ['src/stores/renderPanelStore.ts','src/components/viewport/CanvasViewport.vue','src/components/viewport/RenderControlPanel.vue']) {
    sourceSha256[file] = createHash('sha256').update(await readFile(resolve(file))).digest('hex')
  }
  const report = {checks:{legacyBlueprint:true,instancedMeshes:true,nativeControls:true,disabledAcrossDocuments:true,
    idleReplay:true,exactRestore:true,frontendDuration:true,replay:true,inputCancels:true,switchBlueprint:true,
    editDoesNotReplay:true,remountPreservesDisabled:true,realBuilding:true,noDocumentMutation:true,
    environmentUnchanged:true,noRuntimeOrShaderErrors:true},sourceSha256,errors:p.errors}
  await writeFile(output + '/验证结果.json', JSON.stringify(report,null,2)+'\n')
  console.log(JSON.stringify(report,null,2))
} catch (error) {
  await p.screenshot(output + '/failure.png')
  throw error
} finally { await browser.close() }
