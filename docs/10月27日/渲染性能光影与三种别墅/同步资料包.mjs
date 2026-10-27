import { readFile, writeFile, readdir, mkdir, copyFile, cp, stat } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { fileURLToPath } from 'node:url'
import { dirname, resolve, relative, join } from 'node:path'

const here=dirname(fileURLToPath(import.meta.url)),root=resolve(here,'../../..'),pack=join(root,'docs/蓝图文档'),skill=join(root,'docs/蓝图技能/wild-blueprint-authoring')
const digest=bytes=>createHash('sha256').update(bytes).digest('hex')
const slash=p=>p.replaceAll('\\','/')
const files=async dir=>{const result=[];for(const e of await readdir(dir,{withFileTypes:true})){if(['node_modules','__pycache__','.git'].includes(e.name))continue;const p=join(dir,e.name);if(e.isDirectory())result.push(...await files(p));else if(!/\.zip(?:\.sha256)?$/.test(e.name))result.push(p)}return result.sort()}
const sources=new Set((await files(join(root,'wild-core/src'))).filter(p=>p.endsWith('.ts')))
for(const name of ['types.ts','schema.json','material-presets.json','package.json','package-lock.json','tsconfig.json'])sources.add(join(root,'wild-core',name))
const pending=['renderEntity.ts','materialAdapter.ts','worldRenderSettings.ts','environmentRuntime.ts','postProcessingRuntime.ts','fixtureLightingRuntime.ts','waterReflectionRuntime.ts'].map(n=>join(root,'wild-web/src/renderer',n))
while(pending.length){const source=resolve(pending.pop());if(sources.has(source))continue;sources.add(source)
 const text=await readFile(source,'utf8')
 for(const match of text.matchAll(/(?:from\s*|import\s*)['"](\.[^'"]+)['"]/g)) {
  const base=resolve(dirname(source),match[1]),candidates=[base,base+'.ts',join(base,'index.ts')]
  let target
  for(const p of candidates)if(await stat(p).then(s=>s.isFile(),()=>false)){target=p;break}
  if(!target)throw Error('未解析导入: '+source+' '+match[1]);pending.push(target)
 }
}
for(const name of ['validate-generated.mjs','render-baseline.mjs'])sources.add(join(root,'wild-web/scripts',name))
for(const name of ['contracts.py','compilation.py'])sources.add(join(root,'wild-server/app/design',name))
const rows=[]
for(const source of [...sources].sort()) {
 const sourcePath=slash(relative(root,source)),target=join(pack,'核心资料',sourcePath),bytes=await readFile(source)
 await mkdir(dirname(target),{recursive:true});await writeFile(target,bytes)
 rows.push({source:sourcePath,packed:slash(relative(pack,target)),bytes:bytes.length,sha256:digest(bytes)})
}
await writeFile(join(pack,'验证与来源/核心源码来源.json'),JSON.stringify({snapshot_date:'2026-10-27',policy:'当前工作树原样快照；包含完整Core和渲染相对依赖闭包；不包含依赖缓存、密钥或完整后端',files:rows},null,2)+'\n')
const manifest=JSON.parse(await readFile(join(here,'生成清单.json'),'utf8')),caseRoot=join(pack,'案例/16-三种原创别墅-2026-10-27')
await mkdir(caseRoot,{recursive:true})
for(const r of manifest.records)await cp(join(here,r.directory),join(caseRoot,r.directory),{recursive:true,filter:p=>!['__pycache__','node_modules'].includes(p.split(/[\\/]/).at(-1))})
for(const name of ['生成清单.json','设计事实.json'])await copyFile(join(here,name),join(caseRoot,name))
await copyFile(join(here,'生成三种别墅.mjs'),join(caseRoot,'作者源码.mjs.txt'))
await writeFile(join(caseRoot,'README.md'),'# 三种原创别墅 · 2026-10-27\n\n'+manifest.records.map(r=>'- ['+r.name+']('+r.directory+'/'+r.file+')：'+r.bytes+'字节；[设计事实]('+r.directory+'/设计事实.md)、[Core检查]('+r.directory+'/静态与Core验收.json)、[日景]('+r.directory+'/效果图/01-日景主视.png)、[夜景]('+r.directory+'/效果图/06-夜景.png)、[渲染清单]('+r.directory+'/效果图/render_manifest.json)。').join('\n')+'\n\n各案包含完整正式WILD、设计事实、静态/Core检查与实图。25张1280×960 WebGL图绑定源hash；用户审图仍待完成。作者为本轮Codex，未调用远程模型或项目Agent生成链。\n\n[作者源码](作者源码.mjs.txt)作为原项目过程证据，其输入材质目录和执行位置以原项目 docs/10月27日/渲染性能光影与三种别墅 为准；它不是随包通用生成器。包内正式WILD不依赖该脚本，可直接导入；重新检查/出图使用[包内工具](../../工具/README.md)。\n\n三案在楼层、交通、屋面、围合和景观上实质不同。借鉴局部构造与验证方法，不默认复用布局。实心坡顶不表示可用阁楼；概念几何和审图不证明工程合规。\n')
const entries=[]
for(const p of await files(pack))if(slash(relative(pack,p))!=='验证与来源/文件清单.json') {const bytes=await readFile(p);entries.push({path:slash(relative(pack,p)),bytes:bytes.length,sha256:digest(bytes)})}
await writeFile(join(pack,'验证与来源/文件清单.json'),JSON.stringify({date:'2026-10-27',excludes:['自身','zip及其sha256','node_modules','__pycache__'],files:entries},null,2)+'\n')
await cp(pack,join(skill,'references/blueprint-kit'),{recursive:true,filter:p=>!['node_modules','__pycache__','.git'].includes(p.split(/[\\/]/).at(-1))&&!/\.zip(?:\.sha256)?$/.test(p)})
const mapped=[]
for(const p of await files(pack))mapped.push({source:slash(relative(pack,p)),packed:'references/blueprint-kit/'+slash(relative(pack,p)),sha256:digest(await readFile(p))})
await writeFile(join(root,'docs/蓝图技能/资料整合来源.json'),JSON.stringify({source:'docs/蓝图文档',date:'2026-10-27',policy:'当前材质/动态构件/渲染能力、源码与三案证据同步；历史报告保留原日期与边界',files:mapped},null,2)+'\n')
await writeFile(join(here,'验证/资料同步.json'),JSON.stringify({status:'PASS',sourceSnapshots:rows.length,documentFiles:mapped.length,caseFiles:manifest.records.map(r=>({file:r.file,sha256:r.sha256})),targetDirectories:['docs/蓝图文档','docs/蓝图技能/wild-blueprint-authoring'],globalSkillInstalled:false},null,2)+'\n')
console.log(JSON.stringify({sourceSnapshots:rows.length,documentFiles:mapped.length,cases:manifest.records.length}))
