import assert from 'node:assert/strict'
import { readFile, mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { launchEditorBrowser } from './editor-browser.mjs'

const output = resolve('../docs/10月30日/渲染中断修复')
await mkdir(output, { recursive: true })
const origin = process.env.EDITOR_URL || 'http://127.0.0.1:5190'
const browser = await launchEditorBrowser(`${origin}/scripts/presentation-preview.html`)
const p = browser.page
const viewport = code => p.evaluate(`(()=>{const s=document.querySelector('.canvas-viewport').__vueParentComponent.setupState;${code}})()`)
try {
  await p.wait('window.ready')
  const fixture = JSON.parse(await readFile(resolve('scripts/fixtures/presentation.json'), 'utf8'))
  delete fixture.presentation.entrance
  assert.equal(await p.evaluate(`presentationTest.scene.loadBlueprint(${JSON.stringify(fixture)})`), true)
  const before = await viewport('return {json:JSON.stringify(s.sceneStore.document.blueprint),revision:s.sceneStore.document.revision};')
  await viewport(`
    Object.defineProperty(s.worldRuntime,'tick',{value:undefined,configurable:true});
    if(s.animationFrameId!==null)cancelAnimationFrame(s.animationFrameId);s.animationFrameId=null;
    s.renderFrame();return true;
  `)
  await p.evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')
  assert.ok(await viewport('return s.renderer.info.render.calls > 0;'))
  await p.evaluate('presentationTest.remount()')
  await p.wait('document.querySelector(".canvas-viewport").__vueParentComponent.setupState.sceneGroup.children.length > 0')
  assert.deepEqual(await viewport('return {json:JSON.stringify(s.sceneStore.document.blueprint),revision:s.sceneStore.document.revision};'), before)
  await p.screenshot(output + '/重新挂载后.png')
  assert.deepEqual(p.errors, [])
  const report = { checks: { legacyRuntimeWithoutTickRenders:true, remountRebuildsStoredScene:true, documentPreserved:true, noRuntimeErrors:true }, errors:p.errors }
  await writeFile(output + '/回归结果.json', JSON.stringify(report,null,2)+'\n')
  console.log(JSON.stringify(report,null,2))
} finally { await browser.close() }
