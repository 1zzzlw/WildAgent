import assert from 'node:assert/strict'
import { resolve } from 'node:path'
import { readFile } from 'node:fs/promises'
import { launchEditorBrowser } from './editor-browser.mjs'

const browser = await launchEditorBrowser(process.env.EDITOR_URL || 'http://127.0.0.1:5178/')
const p = browser.page
const viewport = code => p.evaluate(`(()=>{const s=document.querySelector('.canvas-viewport').__vueParentComponent.setupState;${code}})()`)
try {
  await p.wait('!!document.querySelector(".enter-button")')
  await p.evaluate(`(()=>{const input=document.querySelector('input[aria-label="访客名称"]');input.value='渲染回归';input.dispatchEvent(new Event('input',{bubbles:true}))})()`)
  await p.click('.enter-button')
  await p.wait('!!document.querySelector(".canvas-viewport canvas")')
  await p.upload('input[type=file]', resolve('scripts/fixtures/render-upgrade.json'))
  await p.wait('document.querySelector(".save-state")?.textContent.includes("已保存")', 60000)
  await p.wait('document.querySelector(".canvas-viewport").__vueParentComponent.setupState.sceneStore.reconstructed?.meshes.length > 0')
  assert.equal(await viewport('return s.sceneStore.reconstructed.diagnostics.filter(d=>d.level==="error").length;'), 0)
  const stored = await p.evaluate(`fetch('/api/editor-smoke-storage').then(r=>r.json()).then(rows=>Object.values(rows).find(bp=>bp.meta.name==='渲染与几何扩展回归'))`)
  assert.ok(stored.geometry.elements.find(e => e.id === 'slab').holes.length === 1, '原始JSON保存必须保留polygon/holes')
  assert.equal(stored.geometry.elements.find(e => e.id === 'capped-rail').caps, true)
  await p.click('button[aria-label="视口"]')
  await p.click('button[aria-label="渲染质量"]')
  await p.click('button[aria-label="渲染质量：精细"]')
  await p.wait('document.querySelector(".canvas-viewport").__vueParentComponent.setupState.waterReflection.active')
  assert.equal(await viewport('return s.postProcessing.ssao.enabled;'), false)
  assert.equal(await viewport('return s.postProcessing.composer.passes.some(p=>p.constructor.name==="GTAOPass"&&p.enabled);'), true)
  await viewport("s.renderPanel.requestPreset({type:'quality',value:'low'});return true;")
  await p.wait('!document.querySelector(".canvas-viewport").__vueParentComponent.setupState.waterReflection.active')
  await viewport("s.renderPanel.requestPreset({type:'quality',value:'high'});return true;")
  await p.wait('document.querySelector(".canvas-viewport").__vueParentComponent.setupState.waterReflection.active')
  await p.click('button[aria-label="渲染面板"]')
  await p.click('button[aria-label="渲染信息"]')
  await p.wait('!!document.querySelector(".rc-panel")')
  await viewport('s.markNeedsRender();return true;')
  const stats = await viewport('s.lastStatsPublishAt=0;s.publishRenderStats();return {...s.renderPanel.stats};')
  assert.ok(stats.activeLights === 1 && stats.shadowLights === 1 && stats.drawCalls > 1 && stats.renderSubmitMs > 0)
  assert.equal(stats.waterReflection, true)
  const degraded = await viewport(`
    window.savedControlsUpdate=s.controls.update;window.savedClockDelta=s.weatherClock.getDelta;
    if(s.animationFrameId!==null)cancelAnimationFrame(s.animationFrameId);
    s.controls.update=()=>true;s.weatherClock.getDelta=()=>.05;
    s.continuousFrame=true;s.fpsSmoothed=10;s.slowFrameSeconds=2.1;s.renderFrame();
    const result={fallback:s.adaptiveQualityApplied,ao:s.postProcessing.composer.passes.some(p=>p.constructor.name==='GTAOPass'&&p.enabled)};
    if(s.animationFrameId!==null)cancelAnimationFrame(s.animationFrameId);
    s.controls.update=()=>false;s.weatherClock.getDelta=()=>.016;s.renderFrame();
    s.controls.update=window.savedControlsUpdate;s.weatherClock.getDelta=window.savedClockDelta;
    return result;
  `)
  assert.deepEqual(degraded,{fallback:true,ao:false},'交互低帧率应暂时关闭 AO')
  await p.wait('!document.querySelector(".canvas-viewport").__vueParentComponent.setupState.adaptiveQualityApplied')
  assert.equal(await viewport('return s.postProcessing.composer.passes.some(p=>p.constructor.name==="GTAOPass"&&p.enabled);'),true,'停止交互后应恢复精细档 GTAO')
  assert.equal(await viewport('return s.waterReflection.enabled;'),true,'停止交互后应恢复水面反射')
  await p.screenshot(resolve('../deliveries/render-upgrade/regression/03-编辑器渲染面板.png'))
  const villa=JSON.parse(await readFile(resolve('../docs/蓝图文档/案例/00-汀院质量参考/汀院别墅-Codex.wild'),'utf8'))
  assert.equal(await viewport(`return s.sceneStore.loadBlueprint(${JSON.stringify(villa)});`),true)
  await p.click('button[aria-label="渲染面板"]')
  await viewport("s.renderPanel.requestPreset({type:'view',value:'presentation'});s.markNeedsRender();return true;")
  await p.wait('document.querySelector(".canvas-viewport").__vueParentComponent.setupState.sceneStore.reconstructed?.meshes.length===752')
  await p.evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
  const output=resolve('../docs/渲染引擎优化/2026-10-27验证/表面诊断')
  await p.screenshot(output+'/01-表面与GTAO.png')
  await viewport("s.postProcessing.setAmbientOcclusion('off');s.markNeedsRender();return true;")
  await p.evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
  await p.screenshot(output+'/02-仅表面.png')
  await p.evaluate("import('/src/renderer/worldEnvironmentRuntime.ts').then(m=>m.updateWorldRenderingState({surfaceEnabled:false}))")
  await p.evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
  await p.screenshot(output+'/03-关闭表面.png')
  await p.evaluate("import('/src/renderer/worldEnvironmentRuntime.ts').then(m=>m.updateWorldRenderingState({surfaceEnabled:true}))")
  await viewport('s.applyQualityPreset();return true;')
  assert.deepEqual(p.errors, [])
  console.log(JSON.stringify({ status: 'PASS', importedAndPersistedExtensionFields: true, highQualityGtao: true, qualityControlsReflection: true, adaptiveQualityRestored: true, stats, errors: p.errors }, null, 2))
} finally { await browser.close() }
