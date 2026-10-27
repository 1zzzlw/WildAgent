import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { readFile, writeFile, mkdir, readdir } from 'node:fs/promises'
import { resolve, relative } from 'node:path'
import { launchEditorBrowser } from './editor-browser.mjs'

const root = '../docs/10月27日/渲染性能光影与三种别墅'
const manifest = JSON.parse(await readFile(root + '/生成清单.json', 'utf8'))
const hash = createHash('sha256')
async function walk(dir) {
  for (const e of (await readdir(dir, { withFileTypes: true })).sort((a,b) => a.name.localeCompare(b.name))) {
    const file=resolve(dir,e.name)
    if(e.isDirectory())await walk(file)
    else if(/\.(ts|json)$/.test(file)){hash.update(relative('..',file).replaceAll('\\','/'));hash.update(await readFile(file))}
  }
}
await walk('../wild-core/src');await walk('src/renderer')
for(const f of ['../wild-core/schema.json','../wild-core/material-presets.json','scripts/material-mechanism-preview.html'])hash.update(await readFile(f))
const rendererSourceSha256=hash.digest('hex')
const configs = [
 {front:[21,13,25],target:[0,2,0],inside:[6.3,1.95,2.7],insideTarget:[2.5,1.2,-1.5],detail:[8.4,5.5,5.35],detailTarget:[5.8,4.5,4.1]},
 {front:[23,15,26],target:[0,1.6,-1],inside:[2.7,1.9,-4.9],insideTarget:[-.5,1.1,-7.2],detail:[2.8,1.25,5.7],detailTarget:[-.3,.5,.6]},
 {front:[23,15,26],target:[0,2,0],inside:[2.8,1.9,-.2],insideTarget:[-2,1.05,-2.7],detail:[4.6,1.7,5.2],detailTarget:[1.35,2.2,2.65]},
]
const browser=await launchEditorBrowser('http://127.0.0.1:5178/scripts/material-mechanism-preview.html')
try {
 const p=browser.page;await p.resize(1280,960);await p.wait('window.ready')
 for(let i=0;i<manifest.records.length;i++) {
  const record=manifest.records[i],text=await readFile(root+'/'+record.directory+'/'+record.file,'utf8'),bp=JSON.parse(text),c=configs[i]
  if(process.argv[2]&&!record.directory.startsWith(process.argv[2]))continue
  assert.equal(createHash('sha256').update(text).digest('hex'),record.sha256)
  const output=root+'/'+record.directory+'/效果图';await mkdir(output,{recursive:true})
  const views=[
   {name:'01-日景主视',time:'day',camera:c.front,target:c.target},
   {name:'02-西南立面',time:'day',camera:[-23,13,22],target:c.target},
   {name:'03-东北立面',time:'day',camera:[21,14,-25],target:c.target},
   {name:'04-俯视全景',time:'day',camera:[1,37,17],target:[0,0,-1]},
   {name:'05-黄昏',time:'sunset',camera:c.front,target:c.target},
   {name:'06-夜景',time:'night',camera:[19,10,23],target:c.target},
   {name:'07-室内材质',time:'day',camera:c.inside,target:c.insideTarget},
   {name:'08-近景构造',time:'day',camera:c.detail,target:c.detailTarget},
  ],results=[]
  for(const view of views) {
   const settings={...view,quality:'high'}
   const result=await p.evaluate('window.viewBlueprint('+JSON.stringify(bp)+','+JSON.stringify(settings)+')')
   assert.deepEqual(result.diagnostics.filter(d=>d.level==='error'),[])
   await p.evaluate('document.fonts.ready.then(()=>{window.draw();return true})')
   await p.screenshot(output+'/'+view.name+'.png')
   const stats=await p.evaluate('({drawCalls:window.renderer.info.render.calls,triangles:window.renderer.info.render.triangles,reflection:window.renderHarness.reflection.active})')
   results.push({...view,...result,...stats})
  }
  if(i===0) {
   const liftSettings={quality:'high',fov:50,camera:[-4.9,1.85,-1.1],target:[-6.8,1.5,-2.3]}
   await p.evaluate('window.viewBlueprint('+JSON.stringify(bp)+','+JSON.stringify(liftSettings)+')')
   const point=await p.evaluate("window.controlPoint('courtyard_lift__hall_0')")
   assert.ok(point.x>0&&point.x<1280&&point.y>0&&point.y<960,'呼梯按钮须在画面内: '+JSON.stringify(point))
   for(const type of ['mousePressed','mouseReleased'])await p.send('Input.dispatchMouseEvent',{type,button:'left',clickCount:1,...point})
   await p.evaluate('window.advance(1)')
   assert.equal(await p.evaluate("window.group.getObjectByName('courtyard_lift__cab_door_1').userData.elevatorDoorProgress"),1)
   await p.screenshot(output+'/09-电梯开门.png')
   results.push({name:'09-电梯开门',...liftSettings,hallButtonRealClick:true,doorProgress:1})
  }
  assert.deepEqual(p.errors,[])
  const result={status:'PASS',inputSha256:record.sha256,rendererSourceSha256,resolution:[1280,960],quality:'high',views:results,hiddenObjects:[],shaderErrors:p.errors,visual_review:{complete:false,assistant_review:'pending',user_review:'pending',reason:'真实WebGL实图已生成，待逐张查看；用户审图独立进行'}}
  await writeFile(output+'/render_manifest.json',JSON.stringify(result,null,2))
  console.log(JSON.stringify({name:record.name,views:results.length,inputSha256:record.sha256,rendererSourceSha256}))
 }
}finally{await browser.close()}
