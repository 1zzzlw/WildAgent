import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import { writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { dirname, resolve, join } from 'node:path'

const exec=promisify(execFile),here=dirname(fileURLToPath(import.meta.url)),root=resolve(here,'../../..')
const cases=[
 ['Core TypeScript','wild-core',['node_modules/typescript/bin/tsc','--noEmit','-p','tsconfig.json']],
 ['Vue TypeScript','wild-web',['node_modules/vue-tsc/bin/vue-tsc.js','-b']],
 ['Vite production build','wild-web',['node_modules/vite/bin/vite.js','build']],
 ['12 historical geometries','wild-web',['scripts/geometry-regression.mjs']],
 ['Opening interaction and incremental resources','wild-web',['scripts/check-opening-interactions.mjs']],
 ['Elevator and fan','wild-web',['scripts/check-mechanisms.mjs']],
 ['Three villas Schema and Core','wild-web',['scripts/validate-three-villas.mjs']],
 ['Shadow fit and cache regression','wild-web',['scripts/render-optimization-smoke.mjs']],
 ['Materials and wall glass GPU','wild-web',['scripts/material-mechanism-smoke.mjs','../docs/10月27日/渲染性能光影与三种别墅/验证']],
]
const results=[]
for(const [name,cwd,args]of cases) {
 const startedAt=new Date().toISOString();let stdout='',stderr='',exitCode=0
 try{({stdout,stderr}=await exec(process.execPath,args,{cwd:join(root,cwd),env:{...process.env,SystemRoot:'C:/Windows',WINDIR:'C:/Windows'},maxBuffer:4*1024*1024,windowsHide:true}))}
 catch(e){stdout=e.stdout||'';stderr=e.stderr||e.message;exitCode=e.code??1}
 const result={name,cwd,command:['node',...args],startedAt,endedAt:new Date().toISOString(),exitCode,stdout,stderr};results.push(result)
 await writeFile(join(here,'验证/最终检查原始输出.json'),JSON.stringify({status:results.every(r=>r.exitCode===0)?'PASS':'FAIL',results},null,2))
 console.log(JSON.stringify({name,exitCode}))
 if(exitCode!==0){console.error(stderr||stdout);process.exitCode=1;break}
}
