import assert from 'node:assert/strict'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'
import { launchEditorBrowser } from './editor-browser.mjs'

// 复用现有独立视口，不依赖登录服务；验证 Worker、资源复用和画质保持。
const server = await createServer({
  root: fileURLToPath(new URL('..', import.meta.url)),
  server: { host: '127.0.0.1', port: 5186, strictPort: true },
})
let browser
try {
  await server.listen()
  browser = await launchEditorBrowser('http://127.0.0.1:5186/scripts/presentation-preview.html')
  const p = browser.page
  await p.wait('window.ready')
  const result = await p.evaluate(`(async()=>{
    const {isReactive,nextTick}=await import('/node_modules/.vite/deps/vue.js')
    const {reconstructScene}=await import('/src/renderer/reconstructionClient.ts')
    const {reconstructWildEntity}=await import('/src/renderer/wildCoreAdapter.ts')
    const {meshSignature}=await import('/src/renderer/meshSignature.ts')
    const {MaterialCache}=await import('/src/renderer/materialAdapter.ts')
    const {updateWorldEffectState}=await import('/src/renderer/worldEffectRuntime.ts')
    const {updateWorldRenderingState}=await import('/src/renderer/worldEnvironmentRuntime.ts')
    updateWorldEffectState({clouds:false,ripples:false})
    updateWorldRenderingState({weatherEnabled:false})
    window.presentationTest.render.entranceEnabled=false
    const store=window.presentationTest.scene
    const assert=(ok,message)=>{if(!ok)throw Error(message)}
    const source=await fetch('/scripts/fixtures/render-upgrade.json').then(r=>r.json())
    const snapshot=JSON.stringify(source)
    const worker=await reconstructScene(source),direct=await reconstructWildEntity(source)
    assert(worker.meshes.length===direct.meshes.length,'Worker 网格数量改变')
    for(let i=0;i<worker.meshes.length;i++) {
      const a=worker.meshes[i],b=direct.meshes[i]
      assert(a.renderSignature===meshSignature(b),'Worker 复用键不一致')
      assert(JSON.stringify(a.transform)===JSON.stringify(b.transform),'Worker 变换改变')
      for(const field of ['geometry','indices','normals','uvs','vertexColors']) {
        assert(!!a[field]===!!b[field],'Worker 属性缺失: '+field)
        if(!a[field])continue
        assert(a[field].length===b[field].length,'Worker 属性长度改变: '+field)
        assert(a[field].every((value,j)=>Object.is(value,b[field][j])),'Worker 几何属性改变: '+field)
      }
    }
    assert(JSON.stringify(worker.materialParams)===JSON.stringify(direct.materialParams),'Worker 材质改变')
    assert(JSON.stringify(worker.boundingBox)===JSON.stringify(direct.boundingBox),'Worker 包围盒改变')
    assert(JSON.stringify(source)===snapshot,'Worker 修改了源蓝图')
    // Vue Proxy 必须仍能越过 Worker 边界；结果保持普通对象。
    assert(await store.loadBlueprint(source),'视口导入失败')
    await nextTick()
    assert(!isReactive(store.reconstructed)&&!isReactive(store.reconstructed.meshes[0]),'重建结果进入了深层响应式')
    const s=document.querySelector('.canvas-viewport').__vueParentComponent.setupState
    s.environmentPresetId='meadow';s.rebuildBuiltInEnvironment()
    let children=[...s.builtInEnvironment.children]
    const originalMeshes=[...s.sceneGroup.children]
    s.updateScene()
    assert(children.every((child,i)=>child===s.builtInEnvironment.children[i]),'相同环境被重复创建')
    assert(originalMeshes.every((mesh,i)=>mesh===s.sceneGroup.children[i]),'未变化网格没有复用')
    const readPixels=()=>{
      s.waterReflection.update(s.camera,true);s.composer.render()
      const gl=s.renderer.getContext(),pixels=new Uint8Array(gl.drawingBufferWidth*gl.drawingBufferHeight*4)
      gl.readPixels(0,0,gl.drawingBufferWidth,gl.drawingBufferHeight,gl.RGBA,gl.UNSIGNED_BYTE,pixels)
      return pixels
    }
    const reusedPixels=readPixels()
    s.clearBuiltInEnvironment();s.rebuildBuiltInEnvironment()
    const recreatedPixels=readPixels()
    assert(reusedPixels.every((value,i)=>value===recreatedPixels[i]),'复用环境与重新创建的像素不一致')
    children=[...s.builtInEnvironment.children]
    const originalY=s.environmentGroundY
    s.environmentGroundY+=1;s.rebuildBuiltInEnvironment()
    assert(s.builtInEnvironment.position.y===originalY+1,'复用环境没有更新位置')
    assert(children.every((child,i)=>child===s.builtInEnvironment.children[i]),'平移环境重建了几何')
    s.environmentGroundY=originalY;s.rebuildBuiltInEnvironment()
    const originalExtent=s.lightingExtent
    s.lightingExtent+=1;s.rebuildBuiltInEnvironment()
    assert(s.builtInEnvironment.children[0]!==children[0],'尺度变化未重建环境')
    s.lightingExtent=originalExtent;s.rebuildBuiltInEnvironment()
    s.environmentPresetId='minimal';s.rebuildBuiltInEnvironment()
    assert(s.builtInEnvironment.children.length===0&&!s.builtInEnvironment.visible,'切换极简未释放环境')
    s.environmentPresetId='meadow';s.rebuildBuiltInEnvironment()
    s.qualityLevel='high';s.timeOfDay='night';s.applyTimePreset();s.applyQualityPreset()
    const quality=()=>({ratio:s.renderer.getPixelRatio(),ao:s.postProcessing.composer.passes.some(p=>p.constructor.name==='GTAOPass'&&p.enabled),bloom:s.bloomPass.enabled,reflection:s.waterReflection.enabled,samples:s.postProcessing.composer.renderTarget1.samples,shadow:s.directionalLight.shadow.mapSize.x})
    const before=quality(),savedUpdate=s.controls.update,savedDelta=s.weatherClock.getDelta
    try {
      s.controls.update=()=>true;s.weatherClock.getDelta=()=>.05
      for(let i=0;i<50;i++) {
        if(s.animationFrameId!==null)cancelAnimationFrame(s.animationFrameId)
        s.animationFrameId=null;s.continuousFrame=true;s.fpsSmoothed=10;s.renderFrame()
      }
      assert(JSON.stringify(quality())===JSON.stringify(before),'低帧率交互降低画质')
    } finally {
      s.controls.update=savedUpdate;s.weatherClock.getDelta=savedDelta
    }
    // 缓存只覆盖一次更新；下一次更新必须识别原对象上的材质修改。
    const cache=new MaterialCache('render-loading-smoke'),params={baseColor:[.5,.4,.3],roughness:.7,metallic:0,albedo:1}
    cache.beginUpdate();const first=cache.getOrCreate('test',params,false)
    assert(first===cache.getOrCreate('test',params,false),'同次更新材质未复用');cache.endUpdate()
    params.roughness=.2;cache.beginUpdate();const changed=cache.getOrCreate('test',params,false);cache.endUpdate()
    assert(changed!==first&&changed.roughness===.2,'材质缓存跨更新失效失败');cache.clear()
    const large=structuredClone(source)
    large.geometry.elements.push(...Array.from({length:1200},(_,i)=>({id:'stress-'+i,type:'primitive',shape:'box',position:[i%40,1,Math.floor(i/40)],dimensions:[.2+(i%11)*.01,.4,.2],material:'stone'})))
    assert(await store.loadBlueprint(large),'大场景重建失败');await nextTick()
    assert(store.reconstructed.meshes.length===1205,'大场景丢失网格')
    const largeMeshes=[...s.sceneGroup.children],originalGeometry=s.sceneStore.reconstructed.meshes[5].geometry
    await store.reconstruct();await nextTick()
    assert(largeMeshes.every((mesh,i)=>mesh===s.sceneGroup.children[i]),'大场景重建未复用网格')
    assert(s.sceneStore.reconstructed.meshes[5].geometry!==originalGeometry,'未实际运行第二次 Worker 重建')
    assert(s.sceneStore.reconstructed.meshes.every(mesh=>typeof mesh.renderSignature==='string'),'大场景复用键未在 Worker 计算')
    const result={meshes:worker.meshes.length,stressMeshes:store.reconstructed.meshes.length,workerGeometryExact:true,workerMaterialExact:true,rawReconstruction:true,environmentReused:true,environmentPixelsExact:true,environmentInvalidation:true,unchangedMeshesReused:true,quality:quality(),materialChangesPreserved:true}
    window.presentationTest.app.unmount()
    return result
  })()`)
  assert.deepEqual(p.errors, [])
  console.log(JSON.stringify({ status: 'PASS', ...result, browserErrors: p.errors }, null, 2))
} finally {
  await browser?.close()
  await server.close()
}
