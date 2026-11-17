import assert from 'node:assert/strict'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { launchEditorBrowser } from './editor-browser.mjs'

const output = process.argv[2] || '../.workbuddy/render-upgrade/sky'
await mkdir(output,{recursive:true})
const blueprint = JSON.parse(await readFile('../docs/11月17日/无垠之环-四方归一纪念建筑.wild','utf8'))
const browser=await launchEditorBrowser('http://127.0.0.1:5188/scripts/presentation-preview.html?controls')
const p=browser.page
const viewport=code=>p.evaluate(`(async()=>{const s=document.querySelector('.canvas-viewport').__vueParentComponent.setupState;${code}})()`)
try {
  await p.wait('window.ready && document.querySelector(".canvas-viewport")?.__vueParentComponent.setupState.renderer')
  await p.evaluate('window.presentationTest.scene.loadBlueprint('+JSON.stringify(blueprint)+')')
  await p.wait('!!document.querySelector(".canvas-viewport").__vueParentComponent.setupState.sceneGroup?.children.length')
  await viewport(`s.finishEntrance();s.renderPanel.requestPreset({type:'quality',value:'high'});s.renderPanel.autoRotate=false;s.controls.autoRotate=false;s.controls.enableDamping=false;return true`)
  const states=[]
  for(const time of ['dawn','day','sunset','night']) {
    await viewport(`s.renderPanel.requestPreset({type:'time',value:'${time}'});return true`)
    await p.wait(`document.querySelector('.canvas-viewport').__vueParentComponent.setupState.environmentRuntime?.photographicSkyReady`)
    await viewport(`s.finishEntrance();s.camera.fov=45;s.camera.updateProjectionMatrix();s.camera.position.set(82,32,-94);s.controls.target.set(0,13,0);s.controls.update();s.markNeedsRender();return true`)
    await p.evaluate('new Promise(resolve=>setTimeout(resolve,350))')
    states.push(await viewport(`const photo=s.scene.getObjectByName('PhotographicSky');return {time:s.timeOfDay,photo:s.environmentRuntime.photographicSkyReady,procedural:s.sky.visible,skyVisible:photo.visible,quality:s.qualityLevel,texture:[photo.material.uniforms.panorama.value.image.width,photo.material.uniforms.panorama.value.image.height],ground:s.presentationGround.geometry.type,fxaa:s.postProcessing.fxaa.enabled,pixels:[s.renderer.domElement.width,s.renderer.domElement.height],occlusion:{...s.postProcessing.visibility.stats},environment:!!s.scene.environment}`))
    await p.screenshot(output+'/'+time+'.png')
  }
  await viewport('s.renderPanel.showEdges=true;return true')
  await p.wait('!document.querySelector(".canvas-viewport").__vueParentComponent.setupState.scene.getObjectByName("PhotographicSky").visible')
  await viewport('s.renderPanel.showEdges=false;return true')
  await p.wait('document.querySelector(".canvas-viewport").__vueParentComponent.setupState.scene.getObjectByName("PhotographicSky").visible')
  await viewport(`const effects=await import('/src/renderer/worldEffectRuntime.ts');const env=await import('/src/renderer/worldEnvironmentRuntime.ts');s.renderPanel.requestPreset({type:'time',value:'sunset'});env.updateWorldEnvironmentState({cloudCoverage:.75});effects.updateWorldEffectState({clouds:true});s.camera.position.set(0,3,90);s.controls.target.set(0,38,0);s.controls.update();s.markNeedsRender();return true`)
  await p.evaluate('new Promise(resolve=>setTimeout(resolve,350))')
  await p.screenshot(output+'/dynamic-clouds.png')
  const dynamic=await viewport(`return {visible:s.scene.getObjectByName('WorldCloudLayer').visible,continuous:s.continuousFrame}`)
  assert.equal(dynamic.visible,true)
  assert.equal(dynamic.continuous,true)
  await viewport(`const effects=await import('/src/renderer/worldEffectRuntime.ts');effects.updateWorldEffectState({clouds:false});return true`)
  await p.evaluate(`fetch('/scripts/fixtures/render-upgrade.json').then(r=>r.json()).then(bp=>window.presentationTest.scene.loadBlueprint(bp))`)
  await p.wait('document.querySelector(".canvas-viewport").__vueParentComponent.setupState.sceneGroup.children.length < 30 && document.querySelector(".canvas-viewport").__vueParentComponent.setupState.sceneBoundsSize.x < 30')
  await viewport(`const env=await import('/src/renderer/worldEnvironmentRuntime.ts');env.updateWorldEnvironmentState({timeOfDay:12,cloudCoverage:.08,fog:0});s.finishEntrance();s.renderPanel.requestPreset({type:'environment',value:'meadow'});return true`)
  await viewport(`s.renderPanel.requestPreset({type:'view',value:'editor'});s.camera.position.set(110,150,110);s.controls.target.set(0,0,0);s.controls.update();s.markNeedsRender();return true`)
  await p.evaluate('new Promise(resolve=>setTimeout(resolve,300))')
  await p.screenshot(output+'/circular-world.png')
  await p.send('Network.enable')
  await p.send('Network.setBlockedURLs',{urls:['*skies/*.webp']})
  await p.evaluate('window.presentationTest.remount()')
  await p.wait('document.querySelector(".canvas-viewport").__vueParentComponent.setupState.sky?.visible && !document.querySelector(".canvas-viewport").__vueParentComponent.setupState.environmentRuntime?.photographicSkyReady')
  assert.deepEqual(p.errors,[])
  assert.ok(states.every(state=>state.photo&&!state.procedural&&state.environment&&state.skyVisible))
  assert.ok(states.every(state=>state.texture[0]===8192&&state.ground==='CircleGeometry'&&!state.fxaa))
  await p.send('Emulation.setDeviceMetricsOverride',{width:1000,height:700,deviceScaleFactor:2,mobile:false})
  const retina=await viewport(`s.qualityLevel='high';s.applyQualityPreset();return {width:s.renderer.domElement.width,height:s.renderer.domElement.height,texel:s.postProcessing.output.material.uniforms.worldTexel.value.toArray()}`)
  assert.deepEqual(retina,{width:2000,height:1400,texel:[1/2000,1/1400]})
  await writeFile(output+'/viewport.json',JSON.stringify({states,dynamic,retina,photoFailureFallback:true,shaderErrors:p.errors,edgeMode:true},null,2))
  console.log(JSON.stringify({states,dynamic,photoFailureFallback:true,shaderErrors:p.errors,edgeMode:true}))
}finally{await browser.close()}
