// 复用现有渲染脚本，增加观察相机和 Three.js 全局剖切面；不修改源 WILD 或项目渲染器。
import { readFile } from 'node:fs/promises'
import { dirname, resolve, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { createRequire } from 'node:module'

const here = dirname(fileURLToPath(import.meta.url))
const web = resolve(here, '../../../wild-web')
const require = createRequire(join(web, 'package.json'))
let source = await readFile(join(web, 'scripts/render-baseline.mjs'), 'utf8')
function replaceOnce(before, after) {
  if (source.split(before).length !== 2) throw new Error('渲染脚本入口已变化，拒绝猜测替换：' + before)
  source = source.replace(before, after)
}
replaceOnce("from 'vite'", 'from ' + JSON.stringify(pathToFileURL(require.resolve('vite')).href))
replaceOnce('const here = dirname(fileURLToPath(import.meta.url))', 'const here = ' + JSON.stringify(join(web, 'scripts')))
replaceOnce("if (import.meta.url === pathToFileURL(process.argv[1]).href) {", 'if (true) {')
const views = source.match(/const VIEWS = \[[\s\S]*?\n\]/)?.[0]
if (!views) throw new Error('未找到观察相机列表')
replaceOnce(views, `const VIEWS = [
  { name: 'section-ground', azimuthDeg: 180, polarDeg: 7, cutY: 3.42 },
  { name: 'section-upper', azimuthDeg: 180, polarDeg: 7, cutY: 6.65 },
  { name: 'courtyard', azimuthDeg: 135, polarDeg: 68, cutY: null },
]`)
replaceOnce("view.name === 'top'", 'view.polarDeg <= 18')
replaceOnce('renderer.render(scene, camera);', `renderer.clippingPlanes = view.cutY == null ? []
  : [new THREE.Plane(new THREE.Vector3(0, -1, 0), view.cutY)];
renderer.render(scene, camera);`)
replaceOnce("baselineVersion: BASELINE_VERSION,", "baselineVersion: BASELINE_VERSION + '-section/1', sectionPlanes: { ground: 3.42, upper: 6.65 },")
await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'))
