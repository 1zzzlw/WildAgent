import { mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const out = dirname(fileURLToPath(import.meta.url))
const root = resolve(out, '../../..')
const require = createRequire(join(root, 'wild-web/package.json'))
const { build } = await import(pathToFileURL(require.resolve('vite')))
const cacheRoot = join(root, 'wild-web/node_modules/.tmp')
await mkdir(cacheRoot, { recursive: true })
const cache = await mkdtemp(join(cacheRoot, 'kb-core-'))
await build({
  logLevel: 'silent',
  build: {
    lib: { entry: join(root, 'wild-core/src/index.ts'), formats: ['es'], fileName: () => 'core.mjs' },
    outDir: cache, emptyOutDir: false, minify: false,
  },
})
const core = await import(pathToFileURL(join(cache, 'core.mjs')))
const rows = JSON.parse(await readFile(join(out, 'catalog.json'), 'utf8'))
const results = []
for (const row of rows) {
  try {
    const parsed = core.parseBlueprint(JSON.stringify(row.blueprint))
    const compiled = core.compileBlueprintComponents(parsed)
    const rebuilt = await core.reconstructEntity(compiled.blueprint)
    const errors = [...compiled.diagnostics, ...rebuilt.diagnostics].filter(d => d.level === 'error')
    const finiteMeshes = rebuilt.meshes.every(m => [
      ...m.geometry, ...m.transform.position, ...m.transform.rotation, ...m.transform.scale,
    ].every(Number.isFinite))
    const finiteBounds = Object.values(rebuilt.boundingBox).flat().every(Number.isFinite)
    results.push({ slug: row.slug, mesh_count: rebuilt.meshes.length,
      finite_meshes: finiteMeshes, finite_bounds: finiteBounds, errors,
      passed: !errors.length && finiteMeshes && finiteBounds && rebuilt.meshes.length > 0 })
  } catch (error) {
    results.push({ slug: row.slug, passed: false, error: error.message })
  }
}
await writeFile(join(out, 'core-validation.json'), JSON.stringify({
  method: 'Current wild-core parseBlueprint, compileBlueprintComponents and reconstructEntity; no browser rendering',
  results,
}, null, 2))
console.log('CORE', results.filter(r => r.passed).length, '/', results.length)
for (const failed of results.filter(r => !r.passed)) console.log(failed)
if (results.some(r => !r.passed)) process.exitCode = 1
