import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import { readFile, writeFile, cp, mkdtemp, stat } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { fileURLToPath } from 'node:url'
import { dirname, resolve, join } from 'node:path'
import { createHash } from 'node:crypto'

const exec=promisify(execFile),here=dirname(fileURLToPath(import.meta.url)),root=resolve(here,'../../..')
const workspace=await mkdtemp(join(tmpdir(),'wild-render-kit-')),skill=join(workspace,'wild-blueprint-authoring')
await cp(join(root,'docs/蓝图技能/wild-blueprint-authoring'),skill,{recursive:true,filter:p=>!['node_modules','__pycache__','.git'].includes(p.split(/[\\/]/).at(-1))&&!/\.zip(?:\.sha256)?$/.test(p)})
const kit=join(skill,'references/blueprint-kit'),records=JSON.parse(await readFile(join(here,'生成清单.json'),'utf8')).records
const results=[],env={...process.env,SystemRoot:'C:/Windows',WINDIR:'C:/Windows'}
async function run(name,executable,args,cwd=workspace) {
 const startedAt=new Date().toISOString();let stdout='',stderr='',exitCode=0
 try{({stdout,stderr}=await exec(executable,args,{cwd,env,maxBuffer:4*1024*1024,windowsHide:true}))}catch(e){stdout=e.stdout||'';stderr=e.stderr||e.message;exitCode=e.code??1}
 results.push({name,command:[executable,...args],cwd,startedAt,endedAt:new Date().toISOString(),exitCode,stdout,stderr})
 await writeFile(join(here,'验证/独立资料包运行.json'),JSON.stringify({status:results.every(r=>r.exitCode===0)?'PASS':'FAIL',workspace,results},null,2))
 console.log(JSON.stringify({name,exitCode}));if(exitCode)throw Error(name+': '+stderr.slice(-2000))
}
const npmCli=join(dirname(process.execPath),'node_modules/npm/bin/npm-cli.js')
for(const name of ['wild-core','wild-web'])await run('npm ci '+name,process.execPath,[npmCli,'ci','--ignore-scripts','--no-audit','--no-fund'],join(kit,'核心资料',name))
for(const r of records) {
 const file=join(kit,'案例/16-三种原创别墅-2026-10-27',r.directory,r.file)
 await run('portable Core '+r.file,process.execPath,[join(skill,'scripts/validate_core.mjs'),file])
}
const first=records[0],input=join(kit,'案例/16-三种原创别墅-2026-10-27',first.directory,first.file),output=join(here,'验证/独立资料包四视图')
await run('portable WebGL presentation',process.execPath,[join(skill,'scripts/render_preview.mjs'),input,output,'--quality=high','--time=day'])
const manifest=JSON.parse(await readFile(join(output,'render_manifest.json'),'utf8'))
const inputSha256=createHash('sha256').update(await readFile(input)).digest('hex')
if(manifest.inputSha256!==inputSha256)throw Error('独立实图输入指纹不一致')
for(const name of ['front','side','top','perspective'])if((await stat(join(output,name+'.png'))).size<1000)throw Error('缺失独立实图: '+name)
await writeFile(join(here,'验证/独立资料包运行.json'),JSON.stringify({status:'PASS',workspace,results,inputSha256,realWebGLImages:4,manifest:'独立资料包四视图/render_manifest.json',boundary:'临时目录依赖安装、三案Core与一案展示四视图；不是独立Agent创作、其他系统或全UI验收'},null,2))
