import assert from 'node:assert/strict'
import { readFile, mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createHash } from 'node:crypto'
import { launchEditorBrowser } from './editor-browser.mjs'

const output = resolve('../docs/10月29日/语言设计优化/浏览器验证')
await mkdir(output, { recursive: true })
const origin = process.env.EDITOR_URL || 'http://127.0.0.1:5178'
const browser = await launchEditorBrowser(`${origin}/scripts/presentation-preview.html`)
const p = browser.page
const viewport = code => p.evaluate(`(()=>{const s=document.querySelector('.canvas-viewport').__vueParentComponent.setupState;${code}})()`)
const environment = () => p.evaluate(`import('/src/renderer/worldEnvironmentRuntime.ts').then(m=>({environment:{...m.getWorldEnvironmentState()},style:m.getWorldRenderingState().style}))`)
const documentState = () => viewport('return {json:JSON.stringify(s.sceneStore.document.blueprint),revision:s.sceneStore.document.revision,dirty:s.sceneStore.document.dirty};')
const load = blueprint => p.evaluate(`presentationTest.scene.loadBlueprint(${JSON.stringify(blueprint)})`)
try {
  await p.wait('window.ready && !!document.querySelector(".canvas-viewport canvas")')
  const baseline = await environment()
  const raw = await readFile(resolve('../docs/10月29日/语言设计优化/雨宿便利店-原生展示.wild'), 'utf8')
  const blueprint = JSON.parse(raw)
  assert.equal(await load(blueprint), true)
  await p.wait('document.querySelector(".canvas-viewport").__vueParentComponent.setupState.worldRuntime.getInstance("editor:active-blueprint").presentation.active')
  const saved = await documentState()
  await viewport(`
    s.renderLoopActive=false;
    if(s.animationFrameId!==null)cancelAnimationFrame(s.animationFrameId);
    s.animationFrameId=null;
    const entrance=s.worldRuntime.getInstance('editor:active-blueprint').presentation;
    entrance.start(s.sceneStore.document.blueprint.presentation.entrance);entrance.tick(4);
    s.markShadowsDirty();s.fixtureLighting.update(s.camera,'medium');
    s.waterReflection.invalidate();s.waterReflection.update(s.camera,true);s.composer.render();return entrance.progress;
  `)
  await p.screenshot(output + '/01-原生组装中.png')
  await viewport('s.startRenderLoop();return true;')
  await p.wait('!document.querySelector(".canvas-viewport").__vueParentComponent.setupState.worldRuntime.getInstance("editor:active-blueprint").presentation.active', 40000)
  const native = await viewport(`let outlines=0;s.sceneGroup.traverse(o=>{if(o.name==='PresentationOutline')outlines++});
    return {outlines,meshes:s.sceneStore.reconstructed.meshes.length,camera:s.camera.position.toArray(),target:s.controls.target.toArray(),
      errors:s.sceneStore.reconstructed.diagnostics.filter(d=>d.level==='error'),view:s.viewMode,
      stageGround:s.presentationGround.visible,stageShadow:s.shadowGround.visible,stageSky:s.sky.visible,
      weatherScale:s.scene.getObjectByName('WorldWeatherVisuals').scale.toArray()};`)
  assert.equal(native.meshes, 612)
  assert.ok(native.outlines > 0)
  assert.deepEqual(native.errors, [])
  assert.equal(native.view, 'presentation')
  assert.equal(native.stageGround, false)
  assert.equal(native.stageShadow, false)
  assert.equal(native.stageSky, false)
  assert.equal(native.weatherScale[0], 12)
  assert.equal(native.weatherScale[2], 12)
  assert.ok(native.camera.every((v,i)=>Math.abs(v-blueprint.presentation.camera.position[i])<1e-5))
  assert.deepEqual(await documentState(), saved, '播放不能改变源文档或 revision/dirty')
  assert.equal((await environment()).style, 'toon')
  assert.equal((await environment()).environment.rain, .65)
  await p.screenshot(output + '/02-原生雨夜三渲二.png')
  await viewport("s.worldRuntime.getInstance('editor:active-blueprint').presentation.start({type:'assemble',duration:3});s.markNeedsRender();return true;")
  await p.wait('document.querySelector(".canvas-viewport").__vueParentComponent.setupState.worldRuntime.getInstance("editor:active-blueprint").presentation.active')
  await p.send('Input.dispatchMouseEvent', { type:'mousePressed',button:'left',buttons:1,x:700,y:500,clickCount:1 })
  await p.send('Input.dispatchMouseEvent', { type:'mouseReleased',button:'left',buttons:0,x:700,y:500,clickCount:1 })
  assert.equal(await viewport("return s.worldRuntime.getInstance('editor:active-blueprint').presentation.active;"), false)
  assert.deepEqual(await documentState(), saved)

  const fixture = JSON.parse(await readFile(resolve('scripts/fixtures/presentation.json'), 'utf8'))
  const shifted = structuredClone(fixture)
  for (const element of shifted.geometry.elements) for (const key of ['position','from','to']) {
    if (element[key]) { element[key][0] += 10; element[key][2] -= 7 }
  }
  for (const instance of shifted.geometry.instances) { instance.position[0] += 10; instance.position[2] -= 7 }
  for (const key of ['position','target']) { shifted.presentation.camera[key][0] += 10; shifted.presentation.camera[key][2] -= 7 }
  delete shifted.presentation.entrance
  assert.equal(await load(shifted), true)
  const offsetCamera = await viewport('return {camera:s.camera.position.toArray(),target:s.controls.target.toArray(),root:s.sceneGroup.position.toArray()};')
  assert.ok(offsetCamera.camera.every((v,i)=>Math.abs(v-fixture.presentation.camera.position[i])<1e-5))
  assert.ok(offsetCamera.target.every((v,i)=>Math.abs(v-fixture.presentation.camera.target[i])<1e-5))
  const revised = await documentState()
  await viewport(`s.worldRuntime.getInstance('editor:active-blueprint').presentation.start({type:'assemble',duration:3});s.markNeedsRender();return true;`)
  assert.equal(await viewport(`return s.sceneStore.applyPatch({type:'scene_patch',patch_id:'presentation-edit',base_revision:s.sceneStore.document.revision,source:'user',mode:'apply',requires_confirmation:false,operations:[{op:'update_element',id:'base',changes:{dimensions:[6.2,.4,6]}}]});`), true)
  await p.wait('!document.querySelector(".canvas-viewport").__vueParentComponent.setupState.worldRuntime.getInstance("editor:active-blueprint").presentation.active')
  assert.equal((await documentState()).revision, revised.revision + 1)
  const glb = await p.evaluate(`(async()=>{
    const s=document.querySelector('.canvas-viewport').__vueParentComponent.setupState;
    const before=JSON.stringify(s.sceneStore.document.blueprint);
    s.finishEntrance();
    const {exportBuildingGlb}=await import('/src/renderer/glbExport.ts');
    const {GLTFLoader}=await import('/node_modules/three/examples/jsm/loaders/GLTFLoader.js');
    const result=await exportBuildingGlb(s.sceneGroup,'原生展示导出',s.renderer);
    const parsed=await new GLTFLoader().parseAsync(result.data,'');let meshes=0;
    parsed.scene.traverse(o=>{if(o.isMesh)meshes++});
    return {bytes:result.data.byteLength,meshes,unchanged:before===JSON.stringify(s.sceneStore.document.blueprint),warnings:result.warnings};
  })()`)
  assert.ok(glb.bytes > 100 && glb.meshes > 0)
  assert.equal(glb.unchanged, true)
  const legacy = structuredClone(fixture)
  delete legacy.presentation
  assert.equal(await load(legacy), true)
  assert.deepEqual(await environment(), baseline, '新文件不能继承上一份蓝图的雨夜或 toon')
  assert.equal(await viewport("return s.worldRuntime.getInstance('editor:active-blueprint').presentation.active;"), false)
  assert.equal(await viewport("let n=0;s.sceneGroup.traverse(o=>{if(o.name==='PresentationOutline')n++});return n;"), 0)
  await viewport(`s.renderLoopActive=false;if(s.animationFrameId!==null)cancelAnimationFrame(s.animationFrameId);s.animationFrameId=null;
    s.worldRuntime.getInstance('editor:active-blueprint').presentation.start({type:'assemble',duration:2});s.needsRender=false;return true;`)
  await p.send('Input.dispatchMouseEvent', { type:'mousePressed',button:'left',buttons:1,x:700,y:500,clickCount:1 })
  await p.send('Input.dispatchMouseEvent', { type:'mouseReleased',button:'left',buttons:0,x:700,y:500,clickCount:1 })
  assert.equal(await viewport('return s.needsRender;'), true, '静态场景取消后也必须请求最终帧')
  await viewport('s.startRenderLoop();return true;')

  const bad = { ...fixture, presentation: { camera: { position:[0,0,0], target:[0,0,0] } } }
  await load(bad)
  assert.ok(await viewport("return s.sceneStore.validationIssues.some(i=>i.path==='presentation'&&i.level==='error');"))
  assert.ok((await viewport('return s.camera.position.toArray();')).every(Number.isFinite))
  await load(blueprint)
  await viewport('s.finishEntrance();s.markNeedsRender();return true;')
  await p.resize(1440, 1080)
  await p.evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')
  await p.screenshot(output + '/03-原生最终视角.png')
  assert.deepEqual(p.errors, [])
  const sourceSha256 = {}
  for (const file of ['../wild-core/schema.json', 'src/components/viewport/CanvasViewport.vue',
    'src/renderer/blueprintPresentationRuntime.ts', 'src/renderer/worldEnvironmentRuntime.ts',
    'src/renderer/worldWeatherRuntime.ts', 'src/renderer/materialFeatures/toonMaterial.ts']) {
    sourceSha256[file] = createHash('sha256').update(await readFile(resolve(file))).digest('hex')
  }
  const report = { inputSha256:createHash('sha256').update(raw).digest('hex'), sourceSha256,
    checks:{nativeViewport:true,dioramaBounds:true,weather:true,toonAndOutlines:true,assemblyFinished:true,inputCancelsAssembly:true,staticCancelRequestsFrame:true,editingCancelsWithoutReplay:true,glbRoundTrip:true,
      noDocumentMutation:true,centeredCameraCoordinates:true,legacyRestoresDefaults:true,invalidCameraReported:true,noShaderOrRuntimeErrors:true},
    native, offsetCamera, baseline, glb, errors:p.errors }
  await writeFile(output + '/验证结果.json', JSON.stringify(report,null,2)+'\n')
  console.log(JSON.stringify(report,null,2))
} catch (error) {
  await p.screenshot(output + '/failure.png')
  throw error
} finally { await browser.close() }
