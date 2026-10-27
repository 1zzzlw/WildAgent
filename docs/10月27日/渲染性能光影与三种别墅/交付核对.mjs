import assert from 'node:assert/strict'
import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import { readFile, writeFile, readdir } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { fileURLToPath } from 'node:url'
import { dirname, resolve, relative, join } from 'node:path'

const exec=promisify(execFile),here=dirname(fileURLToPath(import.meta.url)),root=resolve(here,'../../..')
const sha=bytes=>createHash('sha256').update(bytes).digest('hex')
const json=async name=>JSON.parse(await readFile(join(here,name),'utf8'))
const records=(await json('生成清单.json')).records
const replay=await exec(process.execPath,[join(here,'生成三种别墅.mjs')],{cwd:root,windowsHide:true})
for(const record of records)assert.equal(sha(await readFile(join(here,record.directory,record.file))),record.sha256,'作者重放必须逐字节一致')

const hash=createHash('sha256')
async function sourceWalk(dir) {
 for(const e of (await readdir(dir,{withFileTypes:true})).sort((a,b)=>a.name.localeCompare(b.name))) {
  const p=join(dir,e.name)
  if(e.isDirectory())await sourceWalk(p)
  else if(/\.(ts|json)$/.test(p)){hash.update(relative(root,p).replaceAll('\\','/'));hash.update(await readFile(p))}
 }
}
await sourceWalk(join(root,'wild-core/src'));await sourceWalk(join(root,'wild-web/src/renderer'))
for(const p of ['wild-core/schema.json','wild-core/material-presets.json','wild-web/scripts/material-mechanism-preview.html'])hash.update(await readFile(join(root,p)))
const rendererSourceSha256=hash.digest('hex')
let images=0
for(const r of records) {
 const report=await json(r.directory+'/静态与Core验收.json'),render=await json(r.directory+'/效果图/render_manifest.json')
 assert.equal(report.sha256,r.sha256);assert.equal(report.status,'PASS');assert.equal(render.inputSha256,r.sha256);assert.equal(render.rendererSourceSha256,rendererSourceSha256)
 assert.equal(render.visual_review.assistant_review,'completed');assert.equal(render.visual_review.complete,false)
 for(const name of render.visual_review.reviewedFiles){const bytes=await readFile(join(here,r.directory,'效果图',name));assert.equal(bytes.readUInt32BE(16),1280);assert.equal(bytes.readUInt32BE(20),960);images++}
}
assert.equal(images,25)
const tests=await json('验证/最终检查原始输出.json');assert.equal(tests.status,'PASS');assert.ok(tests.results.every(r=>r.exitCode===0))
for(const p of ['验证/完整编辑器验收.json','验证/三案编辑器与离屏休眠.json','验证/资料包最终核对.json','验证/独立资料包运行.json'])assert.equal((await json(p)).status,'PASS',p)
const packageCheck=await json('验证/资料包最终核对.json')
for(const r of packageCheck.archives)assert.equal(sha(await readFile(join(root,r.file))),r.sha256)

const diff=await exec('git',['diff','--check'],{cwd:root,windowsHide:true,maxBuffer:1024*1024})
const productionFiles=[]
for(const p of ['wild-web/src/components/viewport/CanvasViewport.vue','wild-web/src/renderer/fixtureLightingRuntime.ts','wild-web/src/renderer/waterReflectionRuntime.ts','wild-web/src/renderer/lightingRuntime.ts','wild-web/src/renderer/mechanismRuntime.ts'])productionFiles.push({file:p,sha256:sha(await readFile(join(root,p)))})
const files=[]
async function walk(dir) {
 for(const e of await readdir(dir,{withFileTypes:true})) {
  if(e.name==='__pycache__')continue
  const p=join(dir,e.name)
  if(e.isDirectory())await walk(p)
  else if(p!==join(here,'交付清单.json')) {
   const bytes=await readFile(p)
   if(p.endsWith('.json'))JSON.parse(bytes.toString('utf8'))
   files.push({path:relative(here,p).replaceAll('\\','/'),bytes:bytes.length,sha256:sha(bytes)})
  }
 }
}
await walk(here)
const result={status:'PASS',date:'2026-10-27',rendererSourceSha256,productionFiles,authorReplay:{exitCode:0,identical:true,stdout:replay.stdout},checks:{finalChecks:tests.results.length,realEditorImports:3,mainRealWebGLImages:images,independentKitRealWebGLImages:4,gitDiffCheck:0,packageLinks:packageCheck.links,sourceSnapshots:packageCheck.sourceSnapshots},limitations:['CPU提交耗时未证明稳定改善，不声称整体FPS提高40%','用户审图、工程审查、新三案全空间人物行走及完整Agent生成链未验收'],gitWarnings:diff.stderr.split(/\r?\n/).filter(Boolean).length,archives:packageCheck.archives,files:files.sort((a,b)=>a.path.localeCompare(b.path))}
await writeFile(join(here,'交付清单.json'),JSON.stringify(result,null,2)+'\n')
console.log(JSON.stringify({status:result.status,files:files.length,checks:result.checks,rendererSourceSha256}))
