import assert from 'node:assert/strict'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { resolve } from 'node:path'
import { launchEditorBrowser } from './editor-browser.mjs'

const output=resolve('../docs/10月30日/微缩背景修复'), assets=resolve('public/business-plan')
await mkdir(output,{recursive:true});await mkdir(assets,{recursive:true})
const browser=await launchEditorBrowser(`${process.env.EDITOR_URL||'http://127.0.0.1:5196'}/scripts/presentation-preview.html`)
const p=browser.page,view=code=>p.evaluate(`(()=>{const s=document.querySelector('.canvas-viewport').__vueParentComponent.setupState;${code}})()`)
const cases=[
  ['yukiakari','../docs/10月30日/雪灯面包店/雪灯面包店-雪夜街角.wild',[[10,8.2,14],[-10,8,14]],[0,1.7,0]],
  ['tomokoji','../docs/10月30日/双场景创作与引擎优化/灯巷拉面屋/灯巷拉面屋-雨夜街角.wild',[[10,7.6,14],[-10,7.6,14]],[0,2,0]],
  ['shiomi','../docs/10月30日/双场景创作与引擎优化/汐见电车站/汐见电车站-海边暮色.wild',[[12,9,16],[-12,8.5,16]],[0,1.5,0]],
]
try{
  await p.wait('window.ready');await p.resize(1440,1080)
  await p.send('Emulation.setDefaultBackgroundColorOverride',{color:{r:0,g:0,b:0,a:0}})
  const manifest=[]
  for(const [id,file,cameras,target] of cases){
    const raw=await readFile(resolve(file),'utf8'),bp=JSON.parse(raw)
    assert.equal(await p.evaluate(`presentationTest.scene.loadBlueprint(${JSON.stringify(bp)})`),true)
    await p.evaluate("presentationTest.render.requestPreset({type:'quality',value:'high'})")
    await view('s.finishEntrance();s.startRenderLoop();s.markNeedsRender();return true;')
    await p.evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')
    const source=await view('return JSON.stringify(s.sceneStore.document);')
    for(let i=0;i<cameras.length;i++){
      const state=await view(`s.renderLoopActive=false;if(s.animationFrameId!==null)cancelAnimationFrame(s.animationFrameId);s.animationFrameId=null;
        s.camera.position.set(${cameras[i]});s.controls.target.set(${target});s.controls.update();
        s.markShadowsDirty();s.fixtureLighting.update(s.camera,'high');s.waterReflection.invalidate();s.waterReflection.update(s.camera,true);s.composer.render();
        const v=new Uint8Array(4);s.renderer.getContext().readPixels(8,8,1,1,s.renderer.getContext().RGBA,s.renderer.getContext().UNSIGNED_BYTE,v);
        return {background:s.scene.background,corner:Array.from(v),camera:s.camera.position.toArray(),target:s.controls.target.toArray()};`)
      assert.equal(state.background,null);assert.equal(state.corner[3],0)
      const name=`${id}-0${i+1}.png`;await p.screenshot(resolve(assets,name))
      manifest.push({id,file:resolve(file),inputSha256:createHash('sha256').update(raw).digest('hex'),image:name,
        imageSha256:createHash('sha256').update(await readFile(resolve(assets,name))).digest('hex'),size:[1440,1080],...state})
    }
    assert.equal(await view('return JSON.stringify(s.sceneStore.document);'),source)
  }
  assert.deepEqual(p.errors,[])
  await writeFile(resolve(output,'商业页面截图来源.json'),JSON.stringify({renderer:'原生 CanvasViewport',quality:'high',transparent:true,manifest,errors:p.errors},null,2)+'\n')
  console.log(JSON.stringify({images:manifest.length,transparent:true,errors:p.errors}))
}finally{await browser.close()}
