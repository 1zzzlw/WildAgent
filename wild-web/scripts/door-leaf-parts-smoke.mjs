import assert from 'node:assert/strict'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { launchEditorBrowser } from './editor-browser.mjs'

const out=resolve('../docs/10月30日/双场景创作与引擎优化/面包店交互修复')
await mkdir(out,{recursive:true})
const browser=await launchEditorBrowser(`${process.env.EDITOR_URL||'http://127.0.0.1:5194'}/scripts/presentation-preview.html`)
const p=browser.page
const view=code=>p.evaluate(`(()=>{const s=document.querySelector('.canvas-viewport').__vueParentComponent.setupState;${code}})()`)
const frame=()=>p.evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')
const load=async bp=>{assert.equal(await p.evaluate(`presentationTest.scene.loadBlueprint(${JSON.stringify(bp)})`),true);await view('s.finishEntrance();s.markNeedsRender();return true;');await frame()}
const camera=()=>view(`s.camera.position.copy(s.sceneGroup.localToWorld(s.camera.position.set(1.5,2.1,6)));s.controls.target.copy(s.sceneGroup.localToWorld(s.controls.target.set(-.15,1.3,1.75)));s.controls.update();s.markNeedsRender();return true;`)
const trigger=name=>p.evaluate(`import('/src/renderer/renderEntity.ts').then(m=>{const s=document.querySelector('.canvas-viewport').__vueParentComponent.setupState;return m.toggleOpeningInteraction(s.sceneGroup.getObjectByName(${JSON.stringify(name)}),()=>{s.markShadowsDirty();s.markNeedsRender()})})`)
const waitProgress=(name,value)=>p.wait(`document.querySelector('.canvas-viewport').__vueParentComponent.setupState.sceneGroup.getObjectByName(${JSON.stringify(name)}).userData.interactionProgress===${value}`)
try {
  await p.wait('window.ready');await p.resize(1280,960)
  const old=JSON.parse(await readFile(out+'/修复前/雪灯面包店-雪夜街角.wild','utf8'))
  old.geometry.components.find(e=>e.id==='entrance').interaction={mode:'swing',openAngle:100}
  await load(old);await camera();await frame();await p.screenshot(out+'/01-修复前关闭.png')
  const oldBefore=await view("return {leaf:s.sceneGroup.getObjectByName('entrance__opening').position.toArray(),handle:s.sceneGroup.getObjectByName('door_handle').position.toArray()};")
  await trigger('entrance__opening');await waitProgress('entrance__opening',1);await frame()
  const oldAfter=await view("return {leaf:s.sceneGroup.getObjectByName('entrance__opening').position.toArray(),handle:s.sceneGroup.getObjectByName('door_handle').position.toArray()};")
  assert.deepEqual(oldBefore.handle,oldAfter.handle);assert.notDeepEqual(oldBefore.leaf,oldAfter.leaf)
  await p.screenshot(out+'/02-修复前把手留在原地.png')

  const raw=await readFile(resolve('../docs/10月30日/雪灯面包店/雪灯面包店-雪夜街角.wild'),'utf8')
  const fixed=JSON.parse(raw);await load(fixed);await camera();await frame()
  const document=await view('return JSON.stringify(s.sceneStore.document);')
  const snapshot=()=>view(`const leaf=s.sceneGroup.getObjectByName('entrance__opening');s.sceneGroup.updateMatrixWorld(true);
    const parts=s.sceneGroup.getObjectsByProperty('type','Mesh').filter(m=>m.name.startsWith('entrance__leafpart_'));
    const inverse=leaf.matrixWorld.clone().invert();return {leaf:leaf.matrix.toArray(),frame:s.sceneGroup.getObjectByName('entrance__frame_1').matrix.toArray(),
      parts:parts.map(m=>({id:m.name,relative:inverse.clone().multiply(m.matrixWorld).toArray()}))};`)
  const closed=await snapshot();assert.equal(closed.parts.length,4)
  await p.screenshot(out+'/03-修复后关闭.png')
  // 用原生右键入口命中把手，覆盖拾取与组合构件的开合派发。
  const point=await view(`const h=s.sceneGroup.getObjectByName('entrance__leafpart_handle');const v=h.position.clone();h.parent.localToWorld(v);v.project(s.camera);return {x:(v.x*.5+.5)*1280,y:(-.5*v.y+.5)*960};`)
  await p.send('Input.dispatchMouseEvent',{type:'mousePressed',button:'right',buttons:2,clickCount:1,...point})
  await p.send('Input.dispatchMouseEvent',{type:'mouseReleased',button:'right',buttons:0,clickCount:1,...point})
  await waitProgress('entrance__opening',1)
  const opened=await snapshot();assert.notDeepEqual(closed.leaf,opened.leaf);assert.deepEqual(closed.frame,opened.frame)
  for(let i=0;i<closed.parts.length;i++) for(let j=0;j<16;j++)assert.ok(Math.abs(closed.parts[i].relative[j]-opened.parts[i].relative[j])<1e-7)
  await p.screenshot(out+'/04-修复后把手护板随门打开.png')
  await trigger('entrance__leafpart_handle');await waitProgress('entrance__opening',0)
  const returned=await snapshot();assert.deepEqual(closed,returned)
  assert.equal(await view('return JSON.stringify(s.sceneStore.document);'),document)

  const variants=await p.evaluate(`(async()=>{
    const {compileBlueprintComponents}=await import('/@fs/E:/AgentProject/WildAgent/wild-core/src/compiler/index.ts');
    const {reconstructEntity,parseBlueprint}=await import('/@fs/E:/AgentProject/WildAgent/wild-core/src/primitive/index.ts');
    const {createSceneGroupFromEntity,clearSceneObjectResources,toggleOpeningInteraction}=await import('/src/renderer/renderEntity.ts');
    const result=[];
    for(const [mode,double,angle,initiallyOpen] of [['swing',false,0,false],['swing',false,Math.PI/2,false],['swing',true,.55,false],['slide',false,.4,false],['lift',false,0,false],['swing',false,0,true]]){
      const parts=[{id:'handle',position:[.25,1,.04],dimensions:[.03,.25,.04],material:'metal'}];
      if(double)parts.push({id:'second',leaf:1,position:[-.25,1,.04],dimensions:[.03,.25,.04],material:'metal'});
      const bp={meta:{version:'1.1',type:'asset',name:'门扇附件回归'},geometry:{elements:[{type:'wall',id:'wall',from:[0,0,0],to:[6*Math.cos(angle),5,6*Math.sin(angle)],thickness:.2,material:'wood'}],components:[{type:'door',id:'door',parentWall:'wall',from:[1,0,0],width:double?2.4:1.4,height:2.6,frameWidth:.06,frameMaterial:'wood',leafMaterial:'wood',doorStyle:double?'double':'single',leafParts:parts,interaction:{mode,initiallyOpen,openAngle:95,openDistance:1.1}}]},materials:{wood:{baseColor:[.5,.3,.2],roughness:.7,metallic:0,albedo:1,lightingCondition:'D65_noon'},metal:{baseColor:[.5,.5,.5],roughness:.3,metallic:.8,albedo:1,lightingCondition:'D65_noon'}}};
      parseBlueprint(JSON.stringify(bp));const original=JSON.stringify(bp),comp=compileBlueprintComponents(bp);if(comp.diagnostics.length)throw Error(JSON.stringify(comp.diagnostics));
      const entity=await reconstructEntity(comp.blueprint),root=createSceneGroupFromEntity(entity);
      const leaves=root.children.filter(m=>m.name==='door__opening'),attachments=root.children.filter(m=>m.name.startsWith('door__leafpart_'));
      const snap=()=>{root.updateMatrixWorld(true);return attachments.map((m,i)=>leaves[i].matrixWorld.clone().invert().multiply(m.matrixWorld).toArray())};
      const start=snap();toggleOpeningInteraction(attachments[0],()=>{});
      await new Promise(resolve=>{const poll=()=>attachments.every(m=>m.userData.interactionProgress===(initiallyOpen?0:1))?resolve():requestAnimationFrame(poll);poll()});
      const end=snap();let error=0;start.forEach((m,i)=>m.forEach((v,j)=>error=Math.max(error,Math.abs(v-end[i][j]))));
      if(error>1e-7)throw Error('附件脱离门扇 '+error);if(JSON.stringify(bp)!==original)throw Error('源蓝图变化');
      result.push({mode,double,angle,initiallyOpen,maxRelativeError:error});clearSceneObjectResources(root);
      const bad=structuredClone(bp);bad.geometry.components[0].leafParts[0].leaf=double?2:1;
      if(!compileBlueprintComponents(bad).diagnostics.some(d=>d.level==='error'))throw Error('越界门扇未拒绝');
      const invalid=structuredClone(bp);invalid.geometry.components[0].leafParts[0].dimensions[0]=-1;
      let rejected=false;try{parseBlueprint(JSON.stringify(invalid))}catch{rejected=true}if(!rejected)throw Error('非法尺寸未拒绝');
    }
    return result;
  })()`)
  assert.deepEqual(p.errors,[])
  const result={oldStandaloneHandleStays:true,nativeRightClickHandleOpensDoor:true,allFourPartsStayRigid:true,frameStaysFixed:true,closeRestoresExactTransform:true,documentUnchanged:true,variants,errors:p.errors}
  await writeFile(out+'/门扇附件回归.json',JSON.stringify(result,null,2)+'\n')
  console.log(JSON.stringify(result,null,2))
} catch(error){await p.screenshot(out+'/检查失败.png');throw error}
finally{await browser.close()}
