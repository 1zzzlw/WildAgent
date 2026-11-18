import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
import { launchEditorBrowser } from './editor-browser.mjs'

const output = process.argv[2] || '../.workbuddy/render-upgrade/sky-texture'
await mkdir(output, {recursive: true})
const browser = await launchEditorBrowser('http://127.0.0.1:5188/scripts/presentation-preview.html')
const p = browser.page
try {
  await p.wait('window.ready && document.querySelector(".canvas-viewport").__vueParentComponent.setupState.environmentRuntime?.photographicSkyHighResolutionReady')
  await p.evaluate(`(() => {
    const s = document.querySelector('.canvas-viewport').__vueParentComponent.setupState;
    s.finishEntrance(); s.renderPanel.requestPreset({type:'time',value:'sunset'});
    s.controls.autoRotate=false; s.controls.enableDamping=false;
    s.camera.fov=60; s.camera.updateProjectionMatrix();
    s.camera.position.set(0,5,0); s.controls.target.set(-100,20,.08); s.controls.update();
    s.presentationGround.visible=false; s.shadowGround.visible=false;
    if(s.gridHelper) s.gridHelper.visible=false; s.markNeedsRender();
  })()`)
  await p.wait('document.querySelector(".canvas-viewport").__vueParentComponent.setupState.environmentRuntime.photographicSkyHighResolutionReady')
  const seam = await p.evaluate(`(() => {
    const s=document.querySelector('.canvas-viewport').__vueParentComponent.setupState;
    s.postProcessing.render(); const gl=s.renderer.getContext();
    const w=s.renderer.domElement.width,h=s.renderer.domElement.height,data=new Uint8Array(w*h*4);
    gl.readPixels(0,0,w,h,gl.RGBA,gl.UNSIGNED_BYTE,data);
    const columns=[];
    for(let x=Math.floor(w/2)-5;x<=Math.floor(w/2)+5;x++) {
      let sum=0,count=0;
      for(let y=Math.floor(h*.3);y<h*.9;y++) for(let k=0;k<3;k++) {
        sum+=Math.abs(data[(y*w+x)*4+k]-(data[(y*w+x-2)*4+k]+data[(y*w+x+2)*4+k])/2);count++;
      }
      columns.push(sum/count);
    }
    return {maxColumnDeviation:Math.max(...columns),columns};
  })()`)
  assert.ok(seam.maxColumnDeviation < 3, '经度接缝出现异常亮/暗竖线')
  await p.screenshot(output+'/seam.png')
  const lifecycle = await p.evaluate(`(async () => {
    const {PhotographicSky}=await import('/src/renderer/photographicSky.ts');
    const {TIME_PRESETS}=await import('/src/renderer/defaultWorldLook.ts');
    const THREE=await import('/node_modules/.vite/deps/three.js');
    const atmosphere={cloud:.72,rain:0,snow:0,dust:0,fog:0,tintStrength:.16,backgroundTint:0x657281};
    const sun=new THREE.Vector3(1,1,1),oldDecoder=window.createImageBitmap;
    let created=0,closed=0;const decodes=[],events=[];
    window.createImageBitmap=(...args)=>{
      const promise=oldDecoder(...args).then(bitmap=>{
        created++;const close=bitmap.close.bind(bitmap);let released=false;
        bitmap.close=()=>{if(!released){closed++;released=true}close()};return bitmap;
      });decodes.push(promise);return promise;
    };
    let sky,discarded,captureWait,capturedName;
    try {
      await new Promise((resolve,reject)=>{
        const timer=setTimeout(()=>reject(Error('天空切换超时')),10000);
        sky=new PhotographicSky(quality=>{
          events.push({quality,name:sky.mesh.material.uniforms.panorama.value?.name});
          if(quality==='full'){clearTimeout(timer);resolve()}
          if(quality==='error'){clearTimeout(timer);reject(Error('天空切换失败'))}
        });
        sky.update(TIME_PRESETS.night,atmosphere,sun);
        captureWait=sky.waitForHighResolution().then(()=>{capturedName=sky.mesh.material.uniforms.panorama.value?.name});
        sky.update(TIME_PRESETS.dawn,atmosphere,sun);
        sky.update(TIME_PRESETS.sunset,atmosphere,sun);
      });
      await sky.waitForHighResolution();
      await captureWait;
      const texture=sky.mesh.material.uniforms.panorama.value;
      const fullSize=[texture.image.width,texture.image.height];
      const cloudHaze=sky.mesh.material.uniforms.haze.value;
      sky.setVisible(false);const hidden=!sky.mesh.visible,iblVisible=sky.environmentMesh.visible;
      sky.setVisible(true);
      let lateCallbacks=0;
      discarded=new PhotographicSky(()=>lateCallbacks++);
      discarded.update(TIME_PRESETS.day,atmosphere,sun);discarded.dispose();
      sky.dispose();await sky.waitForHighResolution();await Promise.all(decodes);await new Promise(resolve=>setTimeout(resolve,100));
      return {events,fullSize,cloudHaze,hidden,iblVisible,lateCallbacks,created,closed,capturedName,disposedReady:sky.highResolutionReady};
    } finally {sky?.dispose();discarded?.dispose();window.createImageBitmap=oldDecoder}
  })()`)
  assert.deepEqual(lifecycle.fullSize,[8192,4096])
  assert.ok(lifecycle.events.every(event=>event.name==='Sky:sunset:'+event.quality), '迟到资源覆盖当前时段')
  assert.equal(lifecycle.cloudHaze,0, '照片重复按云量雾化')
  assert.ok(lifecycle.hidden && lifecycle.iblVisible)
  assert.equal(lifecycle.lateCallbacks,0)
  assert.equal(lifecycle.closed,lifecycle.created, '解码资源未释放')
  assert.equal(lifecycle.disposedReady,false)
  assert.equal(lifecycle.capturedName,'Sky:sunset:full')
  // 使用全新页面排除页面级字节缓存，验证真实截图会等待高清资源。
  await p.send('Page.reload',{ignoreCache:true})
  await p.wait('window.ready && document.querySelector(".canvas-viewport").__vueParentComponent.setupState.environmentRuntime?.photographicSkyHighResolutionReady')
  await p.send('Network.enable')
  await p.send('Network.setCacheDisabled',{cacheDisabled:true})
  await p.send('Network.emulateNetworkConditions',{offline:false,latency:80,downloadThroughput:1000000,uploadThroughput:1000000})
  await p.evaluate(`(() => {
    const s=document.querySelector('.canvas-viewport').__vueParentComponent.setupState;
    window.skyCaptureStates=[];
    const click=HTMLAnchorElement.prototype.click;
    HTMLAnchorElement.prototype.click=function(){
      if(this.download.startsWith('wild-viewport-')) window.skyCaptureStates.push({highResolution:s.environmentRuntime.photographicSkyHighResolutionReady});
      else click.call(this);
    };
    s.renderPanel.requestPreset({type:'time',value:'sunset'});
  })()`)
  await p.wait('(()=>{const r=document.querySelector(".canvas-viewport").__vueParentComponent.setupState.environmentRuntime;return r.photographicSkyReady&&!r.photographicSkyHighResolutionReady})()')
  await p.evaluate('window.skyCapturePending=document.querySelector(".canvas-viewport").__vueParentComponent.setupState.takeScreenshot(); void 0')
  assert.equal(await p.evaluate('window.skyCaptureStates.length'),0)
  await p.evaluate('window.skyCapturePending')
  const captures=await p.evaluate('window.skyCaptureStates')
  assert.deepEqual(captures,[{highResolution:true}])
  await p.send('Network.emulateNetworkConditions',{offline:false,latency:0,downloadThroughput:-1,uploadThroughput:-1})
  await p.send('Network.setBlockedURLs',{urls:['*skies/night.webp']})
  const fallback=await p.evaluate(`(async()=>{
    const s=document.querySelector('.canvas-viewport').__vueParentComponent.setupState;
    s.renderPanel.requestPreset({type:'time',value:'night'});await new Promise(resolve=>setTimeout(resolve,0));
    await s.environmentRuntime.waitForPhotographicSky();await new Promise(resolve=>setTimeout(resolve,150));
    return {previewVisible:s.environmentRuntime.photographicSkyReady,fullReady:s.environmentRuntime.photographicSkyHighResolutionReady,environment:!!s.scene.environment};
  })()`)
  assert.deepEqual(fallback,{previewVisible:false,fullReady:false,environment:true})
  await p.send('Network.setBlockedURLs',{urls:[]})
  await p.evaluate(`(async()=>{const s=document.querySelector('.canvas-viewport').__vueParentComponent.setupState;s.renderPanel.requestPreset({type:'time',value:'day'});await new Promise(resolve=>setTimeout(resolve,0));s.renderPanel.requestPreset({type:'time',value:'night'});})()`)
  await p.wait('document.querySelector(".canvas-viewport").__vueParentComponent.setupState.environmentRuntime.photographicSkyHighResolutionReady')
  assert.deepEqual(p.errors,[])
  await writeFile(output+'/results.json',JSON.stringify({seam,lifecycle,captures,fallback,retryAfterFailure:true,shaderErrors:p.errors},null,2))
  console.log(JSON.stringify({seam,lifecycle,captures,fallback,retryAfterFailure:true,shaderErrors:p.errors}))
} finally {await browser.close()}
