import assert from 'node:assert/strict'
import { readFile, writeFile } from 'node:fs/promises'
import { launchEditorBrowser } from './editor-browser.mjs'

// 运行真实视口；注入锁定态和输入以隔离绘制开销，不代替人工锁鼠体验验收。
const blueprintPath = process.env.ROAMING_BLUEPRINT || 'scripts/fixtures/presentation.json'
const blueprint = JSON.parse(await readFile(blueprintPath, 'utf8'))
const browser = await launchEditorBrowser('http://127.0.0.1:5178/scripts/presentation-preview.html')
try {
  const p = browser.page
  await p.wait('window.ready')
  await p.evaluate(`presentationTest.scene.loadBlueprint(${JSON.stringify(blueprint)})`)
  await p.wait('document.querySelector(".canvas-viewport").__vueParentComponent.setupState.sceneGroup.children.length > 0')
  await p.evaluate(`(async () => {
    const s = document.querySelector('.canvas-viewport').__vueParentComponent.setupState;
    await import('/src/renderer/worldEffectRuntime.ts').then(m => m.updateWorldEffectState({clouds:false, ripples:false}));
    await import('/src/renderer/worldEnvironmentRuntime.ts').then(m => m.updateWorldRenderingState({weatherEnabled:false}));
    s.finishEntrance();
    s.roaming.view = 'first';
    s.roaming.start();
    s.characterRoaming.capturePointer = () => {};
    Object.defineProperty(s.characterRoaming, 'locked', {get: () => true, configurable:true});
    s.markNeedsRender();
  })()`)
  const result = await p.evaluate(`(async () => {
    const s = document.querySelector('.canvas-viewport').__vueParentComponent.setupState;
    const frame = () => new Promise(requestAnimationFrame);
    const mean = values => values.reduce((a,b) => a+b) / values.length;
    const samples = [];
    for (const view of ['first', 'third']) {
      s.characterRoaming.setView(view);
      for (let i=0; i<10; i++) await frame();
      const times=[], frames=[], calls=[];
      const initialYaw=s.characterRoaming.yaw;
      let shadows=0, last=performance.now();
      const original=s.renderer.shadowMap.render;
      s.renderer.shadowMap.render=function(...args) {
        if (this.needsUpdate && s.directionalLight.shadow.needsUpdate) shadows++;
        return original.apply(this,args);
      };
      try {
        for (let i=0; i<60; i++) {
          document.dispatchEvent(new MouseEvent('mousemove', {movementX:3, movementY:0}));
          await frame();
          const now=performance.now();
          frames.push(now-last); last=now;
          times.push(s.renderSubmitMs);
          calls.push(s.renderer.info.render.calls);
        }
      } finally { s.renderer.shadowMap.render=original; }
      frames.sort((a,b) => a-b); times.sort((a,b) => a-b);
      samples.push({view, headingDelta:s.characterRoaming.yaw-initialYaw, frames:frames.length, frameMean:mean(frames), frameP95:frames[57],
        submitMean:mean(times), submitP95:times[57], shadows, callsMean:mean(calls)});
    }
    const switches=[];
    for (let i=0; i<12; i++) {
      const view=s.roaming.view==='first' ? 'third' : 'first', start=performance.now();
      s.renderer.domElement.dispatchEvent(new KeyboardEvent('keydown', {code:'F5', bubbles:true, cancelable:true}));
      await frame();
      switches.push({view, actual:s.roaming.view, ms:performance.now()-start, visible:s.characterRoaming.avatar.visible});
    }
    // 镜头贴墙后人物自动隐藏时，也要刷新最后一帧投影，避免留下人物残影。
    s.characterRoaming.setView('third');
    await frame();
    const world=s.characterRoaming.world, rayDistance=world.rayDistance, shadowRender=s.renderer.shadowMap.render;
    let hiddenShadows=0;
    let hiddenAvatar;
    try {
      world.rayDistance=() => .1;
      s.renderer.shadowMap.render=function(...args) {
        if (this.needsUpdate && s.directionalLight.shadow.needsUpdate) hiddenShadows++;
        return shadowRender.apply(this,args);
      };
      await frame(); await frame();
      hiddenAvatar=!s.characterRoaming.avatar.visible;
    } finally {
      world.rayDistance=rayDistance;
      s.renderer.shadowMap.render=shadowRender;
    }
    const gl=s.renderer.getContext(), ext=gl.getExtension('WEBGL_debug_renderer_info');
    const gpu=gl.getParameter(ext ? ext.UNMASKED_RENDERER_WEBGL : gl.RENDERER);
    const settings={quality:s.qualityLevel, msaa:s.composer.renderTarget1.samples};
    Object.defineProperty(s.characterRoaming, 'locked', {get: () => false});
    s.roaming.stop();
    await frame();
    return {gpu, samples, switches, hiddenAvatar, hiddenShadows, ...settings};
  })()`)
  assert.deepEqual(p.errors, [])
  assert.equal(result.samples[0].shadows, 0, '第一视角转头不应刷新静态主光阴影')
  assert.ok(result.samples[1].shadows > 0, '可见人物的动态投影必须继续刷新')
  assert.ok(result.samples.every(sample => Math.abs(sample.headingDelta) > .4), '鼠标输入应确实改变观察方向')
  for (const change of result.switches) {
    assert.equal(change.actual, change.view, 'F5 应正常切换视角')
    assert.equal(change.visible, change.view === 'third', '切换后人物可见性应正确')
  }
  assert.ok(result.hiddenAvatar && result.hiddenShadows > 0, '镜头贴墙隐藏人物时应清理旧投影')
  assert.equal(result.quality, 'medium', '漫游不应自动降低画质')
  assert.equal(result.msaa, 4, '保留原抗锯齿采样数')
  const report = {blueprintPath, ...result, errors:p.errors}
  if (process.env.ROAMING_REPORT) await writeFile(process.env.ROAMING_REPORT, JSON.stringify(report, null, 2))
  console.log(JSON.stringify(report, null, 2))
} finally {
  await browser.close()
}
