/** 本次参考文档的有限Core语义核对；不是通用几何/视觉验收工具。 */
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const coreRoot = resolve(process.argv[2] || join(here, '../核心资料/wild-core'))
const viteModule = resolve(process.argv[3] || join(here, '../核心资料/wild-web/node_modules/vite/dist/node/index.js'))
const output = resolve(process.argv[4] || join(here, 'v2语义核对结果.json'))
const { build } = await import(pathToFileURL(viteModule).href)
const temporary = await mkdtemp(join(tmpdir(), 'wild-v2-semantics-'))
const sha = bytes => createHash('sha256').update(bytes).digest('hex')
try {
  const exports = {
    buildFloor: 'primitive/geometry/floor.ts',
    buildStair: 'primitive/geometry/stair.ts',
    buildColumn: 'primitive/geometry/column.ts',
    buildPrimitive: 'primitive/geometry/primitive.ts',
    resolveSpatialRelations: 'primitive/resolver.ts',
    boxWithHoles: 'primitive/geometry/box-with-holes.ts',
  }
  const entry = join(temporary, 'entry.ts')
  await writeFile(entry, Object.entries(exports).map(([name, source]) =>
    `export { ${name} } from ${JSON.stringify(join(coreRoot, 'src', source).replaceAll('\\', '/'))};`
  ).join('\n'), 'utf8')
  await build({
    configFile: false, root: coreRoot, logLevel: 'silent',
    build: { outDir: join(temporary, 'build'), emptyOutDir: false, minify: false,
      lib: { entry, formats: ['es'], fileName: () => 'probe.mjs' } },
  })
  const core = await import(pathToFileURL(join(temporary, 'build/probe.mjs')).href)
  const tests = []
  const check = (name, actual, passed) => tests.push({ name, actual, passed })
  const floor = core.buildFloor({type:'floor', id:'f', from:[0,2,0], to:[2,2,2], thickness:.2})[0]
  const ys = Array.from(floor.geometry).filter((_, i) => i % 3 === 1).map(y => y + floor.transform.position[1])
  const floorRange = [Math.min(...ys), Math.max(...ys)]
  check('floor_Y为板底并向上加厚', floorRange, Math.abs(floorRange[0]-2)<1e-6 && Math.abs(floorRange[1]-2.2)<1e-6)
  const stairs = core.buildStair({type:'stair',id:'s',from:[0,0,0],to:[0,1,2],width:1,stepCount:5,stepHeight:.2,stepDepth:.4})
  const last = stairs.at(-1)
  const stairEnd = {farEdgeZ:last.transform.position[2]+.2,topY:last.transform.position[1]+.1}
  check('楼梯末级远边到to而非少半步', stairEnd, Math.abs(stairEnd.farEdgeZ-2)<1e-6 && Math.abs(stairEnd.topY-1)<1e-6)
  const columns = core.buildColumn({type:'column',id:'c',base:[0,0,0],height:3,bottomRadius:.15,topRadius:.13,style:'modern'})
  const columnFinite = columns.every(m => [...m.geometry,...m.transform.position].every(Number.isFinite))
  check('合法column可生成有限网格', {meshCount:columns.length,finite:columnFinite}, columns.length>0 && columnFinite)
  const walls = [
    {type:'wall',id:'front',from:[0,0,0],to:[4,3,0],thickness:.24},
    {type:'wall',id:'right',from:[4,0,0],to:[4,3,4],thickness:.24},
    {type:'wall',id:'back',from:[4,0,4],to:[0,3,4],thickness:.24},
    {type:'wall',id:'left',from:[0,0,4],to:[0,3,0],thickness:.24},
    {type:'opening',id:'o',parentWall:'front',from:[1,0,0],width:1,height:2,style:'arched'},
  ]
  core.resolveSpatialRelations(walls)
  check('转角延伸不要求作者补半墙厚', {openingWorld:walls[4]._worldPos,extensions:walls[0]._jointExtensions},
    walls[4]._worldPos[0]===1.5 && walls[0]._jointExtensions.start===.12 && walls[0]._jointExtensions.end===.12)
  const sweep = core.buildPrimitive({type:'primitive',id:'p',shape:'profile_sweep',
    profile:[[-.1,-.1],[.1,-.1],[.1,.1],[-.1,.1]],path:[[0,0,0],[0,0,1]],closedProfile:true})[0]
  check('闭合四边截面扫掠只有8侧三角无端盖', {triangles:sweep.geometry.length/9}, sweep.geometry.length/9===8)
  const hole = {localX:2,localY:0,localW:1,localH:2}
  const rect = core.boxWithHoles(4,3,.24,[{...hole,style:'rectangular'}])
  const arch = core.boxWithHoles(4,3,.24,[{...hole,style:'arched'}])
  check('拱形洞实际进入墙体几何', {rectVertices:rect.geometry.length/3,archedVertices:arch.geometry.length/3},
    arch.geometry.length!==rect.geometry.length && [...arch.geometry].every(Number.isFinite))
  const sources = []
  for (const source of Object.values(exports)) {
    const bytes = await readFile(join(coreRoot,'src',source))
    sources.push({source:'wild-core/src/'+source,sha256:sha(bytes)})
  }
  const result = {review_date:'2026-10-23',ok:tests.every(t=>t.passed),tests,sources,
    boundary:'直接执行当前Core的有限语义核对；未跑完整后端、真实渲染、全模型碰撞或审美验收'}
  await writeFile(output, JSON.stringify(result,null,2)+'\n','utf8')
  console.log(JSON.stringify(result,null,2))
  if (!result.ok) process.exitCode = 1
} finally {
  // 只删除本次mkdtemp返回的独立目录，不清理项目或资料包。
  const expectedParent = resolve(tmpdir())
  if (dirname(resolve(temporary)) !== expectedParent) throw new Error('临时目录边界异常')
  await rm(temporary,{recursive:true,force:true})
}
