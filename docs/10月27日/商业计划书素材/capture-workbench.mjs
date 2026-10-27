import assert from 'node:assert/strict'
import { writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { launchEditorBrowser } from '../../../wild-web/scripts/editor-browser.mjs'

const directory=fileURLToPath(new URL('./',import.meta.url))
const browser=await launchEditorBrowser((process.env.BUSINESS_PREVIEW_URL || 'http://127.0.0.1:5178')+'/')
try {
  const p=browser.page
  await p.resize(1680,1050)
  await p.wait('!!document.querySelector(".enter-button")',60000)
  await p.evaluate(`(()=>{const el=document.querySelector('input[aria-label="访客名称"]');el.value='商业计划书演示';el.dispatchEvent(new Event('input',{bubbles:true}));return true})()`)
  await p.click('.enter-button')
  await p.wait('!!document.querySelector(".canvas-viewport canvas")')
  await p.upload('input[type=file]',fileURLToPath(new URL('../岚石光庭-交互材质别墅.wild',import.meta.url)))
  await p.wait('document.querySelector(".save-state")?.textContent.includes("已保存")',60000)
  await p.wait('document.querySelector(".canvas-viewport").__vueParentComponent.setupState.sceneStore.reconstructed?.meshes.length>500')
  const viewport=code=>p.evaluate(`(()=>{const s=document.querySelector('.canvas-viewport').__vueParentComponent.setupState;${code}})()`)
  const result=await viewport(`s.renderPanel.requestPreset({type:'view',value:'presentation'});s.renderPanel.requestPreset({type:'quality',value:'high'});s.renderPanel.autoRotate=false;s.controls.autoRotate=false;s.controls.enableDamping=false;s.camera.position.set(23,14,27);s.controls.target.set(0,2,1);s.controls.update();s.markShadowsDirty();s.markNeedsRender();return {name:s.sceneStore.document.blueprint.meta.name,meshes:s.sceneStore.reconstructed.meshes.length,errors:s.sceneStore.reconstructed.diagnostics.filter(d=>d.level==='error')}`)
  assert.deepEqual(result.errors,[])
  await p.evaluate('new Promise(resolve=>setTimeout(resolve,600))')
  await p.evaluate('document.fonts.ready.then(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))))')
  async function shot(file) { const r=await p.send('Page.captureScreenshot',{format:'jpeg',quality:94});await writeFile(directory+file,Buffer.from(r.data,'base64')) }
  await shot('workbench-01.jpg')
  const material=await p.evaluate(`(()=>{const button=Array.from(document.querySelectorAll('button')).find(el=>el.textContent.trim()==='材质'||el.title==='材质');if(!button)return false;button.setAttribute('data-business-material','true');return true})()`)
  if(material){await p.click('[data-business-material="true"]');await p.evaluate('new Promise(resolve=>setTimeout(resolve,600))');await shot('workbench-02.jpg')}
  assert.deepEqual(p.errors,[])
  await writeFile(directory+'workbench-manifest.json',JSON.stringify({createdAt:new Date().toISOString(),source:'../岚石光庭-交互材质别墅.wild',resolution:[1680,1050],...result,materialPanel:material,files:material?['workbench-01.jpg','workbench-02.jpg']:['workbench-01.jpg'],scope:'完整 Vue 编辑器真实导入与截图；使用独立临时浏览器和现有本地 smoke 服务，未调用模型。'},null,2))
  console.log(JSON.stringify({status:'captured',...result,materialPanel:material}))
} finally { await browser.close() }
