import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { readFile, writeFile, mkdir, readdir } from 'node:fs/promises'
import { resolve, relative } from 'node:path'
import { launchEditorBrowser } from './editor-browser.mjs'
const output='../docs/10月27日/别墅渲染',text=await readFile('../docs/10月27日/岚石光庭-交互材质别墅.wild','utf8'),bp=JSON.parse(text)
await mkdir(output,{recursive:true})
const browser=await launchEditorBrowser('http://127.0.0.1:5178/scripts/material-mechanism-preview.html')
try{
 const p=browser.page;await p.resize(1280,960);await p.wait('window.ready')
 const views=[
  {name:'01-水庭日景',time:'day',camera:[18,11,21],target:[0,2,2]},
  {name:'02-西南立面',time:'day',camera:[-20,10,22],target:[-1,2,1]},
  {name:'03-北侧立面',time:'day',camera:[17,10,-22],target:[0,2,-2]},
  {name:'04-俯视全景',time:'day',camera:[14,27,22],target:[0,0,1]},
  {name:'05-水庭夜景',time:'night',camera:[17,9,21],target:[0,2,2]},
  {name:'06-起居室内',time:'day',camera:[-.8,1.95,-.8],target:[5.2,1.3,-3.8]},
  {name:'07-起居室夜景',time:'night',camera:[-.8,1.95,-.8],target:[5.2,1.3,-3.8]},
  {name:'08-二层卧室',time:'day',camera:[-3.05,5.25,6.35],target:[-5.7,4.5,3.4]},
  {name:'09-木作洞石近景',time:'day',camera:[-.1,5.1,4.1],target:[-2.5,5,.8]},
 ]
 const results=[]
 for(const view of views){const result=await p.evaluate('window.viewBlueprint('+JSON.stringify(bp)+','+JSON.stringify({...view,quality:'high'})+')');assert.deepEqual(result.diagnostics.filter(d=>d.level==='error'),[]);await p.screenshot(output+'/'+view.name+'.png');results.push({...view,...result})}
 // 电梯开放轿厢，真实层门仍然保留，不靠隐藏井壁拍摄。
 const liftView={time:'day',quality:'high',camera:[-6.2,1.9,-1.4],target:[-6.2,1.7,-4.1]}
 await p.evaluate('window.viewBlueprint('+JSON.stringify(bp)+','+JSON.stringify(liftView)+')')
 const hall=await p.evaluate("window.controlPoint('courtyard_lift__hall_0')")
 await p.send('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...hall});await p.send('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...hall})
 await p.evaluate('window.advance(1)');assert.equal(await p.evaluate("window.group.getObjectByName('courtyard_lift__cab_door_1').userData.elevatorDoorProgress"),1)
 await p.screenshot(output+'/10-电梯开门与按钮.png')
 const button=await p.evaluate("window.controlPoint('courtyard_lift__car_button_1')")
 await p.send('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...button});await p.send('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...button})
 await p.evaluate('window.advance(8)');assert.equal(await p.evaluate("window.group.getObjectByName('courtyard_lift__cab').userData.elevatorFloor"),1)
 assert.deepEqual(p.errors,[])
 const hash=createHash('sha256');async function walk(dir){for(const e of (await readdir(dir,{withFileTypes:true})).sort((a,b)=>a.name.localeCompare(b.name))){const path=resolve(dir,e.name);if(e.isDirectory())await walk(path);else if(/\.(ts|json)$/.test(path)){hash.update(relative('..',path));hash.update(await readFile(path))}}}
 await walk('../wild-core/src');await walk('src/renderer');await walk('src/extensions/characterRoaming');hash.update(await readFile('../wild-core/schema.json'));hash.update(await readFile('../wild-core/material-presets.json'));hash.update(await readFile('scripts/material-mechanism-preview.html'))
 const result={status:'PASS',inputSha256:createHash('sha256').update(text).digest('hex'),rendererSourceSha256:hash.digest('hex'),resolution:[1280,960],quality:'high',views:results,interaction:{hallButtonRealClick:true,carFloorButtonRealClick:true,arrivedAtFloor:1},hiddenObjects:[],shaderErrors:p.errors,visual_review:{complete:false,reason:'已生成真实渲染，待逐张检查；用户审图尚未进行'}}
 await writeFile(output+'/render_manifest.json',JSON.stringify(result,null,2));console.log(JSON.stringify({status:result.status,inputSha256:result.inputSha256,views:results.length+1,interaction:result.interaction,shaderErrors:p.errors},null,2))
}finally{await browser.close()}
