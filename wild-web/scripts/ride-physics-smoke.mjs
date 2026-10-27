import assert from 'node:assert/strict'
import { readFile, writeFile } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { launchEditorBrowser } from './editor-browser.mjs'
const text=await readFile('../docs/10月27日/岚石光庭-交互材质别墅.wild','utf8'),bp=JSON.parse(text),browser=await launchEditorBrowser('http://127.0.0.1:5178/scripts/material-mechanism-preview.html')
try{
 const p=browser.page;await p.wait('window.ready');await p.evaluate(`(async()=>{const {reconstructWildEntity}=await import('/src/renderer/wildCoreAdapter.ts'),{createSceneGroupFromEntity}=await import('/src/renderer/renderEntity.ts');window.group=createSceneGroupFromEntity(await reconstructWildEntity(${JSON.stringify(bp)}));window.scene.add(window.group);return true})()`)
 const result=await p.evaluate(`(async()=>{
  const {CharacterRoamingRuntime}=await import('/src/extensions/characterRoaming/CharacterRoamingRuntime.ts');
  const {tickMechanisms,interactMechanism}=await import('/src/renderer/mechanismRuntime.ts');
  const rider=new CharacterRoamingRuntime({scene:window.scene,worldRoot:window.group,camera:window.camera,canvas:window.renderer.domElement,groundY:-.04,view:'first',interact:()=>false,onLockChange:()=>{},onViewChange:()=>{},onTargetChange:()=>{},onMessage:()=>{},requestRender:()=>{}});
  // 固定时间步验证真实人物碰撞；锁定态由测试注入，独立于鼠标锁定权限与人工操控。
  Object.defineProperty(rider,'locked',{get:()=>true});
  const place=y=>{rider.body.start.set(-6.2,y+.242,-4.45);rider.body.end.set(-6.2,y+1.51,-4.45);rider.velocity.set(0,0,0);rider.grounded=true};
  const cab=window.group.getObjectByName('courtyard_lift__cab');let drift=0;
  const step=()=>{tickMechanisms(window.group,.05);rider.tick(.05);const floor=cab.position.y+.05;drift=Math.max(drift,Math.abs(rider.body.start.y-.24-floor))};
  place(.32);interactMechanism(window.group.getObjectByName('courtyard_lift__car_button_1'),()=>{});
  for(let i=0;i<200;i++)step();const upper=rider.body.start.y-.24;
  rider.keys.add('KeyS');for(let i=0;i<20;i++){tickMechanisms(window.group,.05);rider.tick(.05)}rider.keys.clear();const exited={feet:rider.body.start.y-.24,z:rider.body.start.z};
  place(3.72);interactMechanism(window.group.getObjectByName('courtyard_lift__car_button_0'),()=>{});for(let i=0;i<250;i++)step();const lower=rider.body.start.y-.24;
  rider.dispose();return {upper,lower,exited,maxFloorDrift:drift};
 })()`)
 assert.ok(Math.abs(result.upper-3.72)<.03,JSON.stringify(result));assert.ok(Math.abs(result.lower-.32)<.03,JSON.stringify(result));assert.ok(Math.abs(result.exited.feet-3.72)<.03);assert.ok(result.exited.z>-3.1,'停靠开门后人物应能走出井道');assert.ok(result.maxFloorDrift<.04,JSON.stringify(result));assert.deepEqual(p.errors,[])
 const report={status:'PASS',inputSha256:createHash('sha256').update(text).digest('hex'),...result,scope:'Chromium 内真实 CharacterRoamingRuntime 固定时间步、真实建筑碰撞与楼板井洞；测试注入锁定态及移动键，未冒充人工键鼠游玩'}
 await writeFile('../docs/10月27日/验证/人物电梯物理验收.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2))
}finally{await browser.close()}
