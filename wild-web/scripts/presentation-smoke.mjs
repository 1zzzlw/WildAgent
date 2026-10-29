import assert from 'node:assert/strict'
import { mkdtemp, readFile, rm } from 'node:fs/promises'
import { dirname, join, resolve } from 'node:path'
import { tmpdir } from 'node:os'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { build } from 'vite'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const directory = await mkdtemp(join(tmpdir(), 'wild-presentation-test-'))
try {
  await build({ root, configFile: false, logLevel: 'silent', plugins: [{
    name: 'presentation-test-entry',
    resolveId: id => id === 'virtual:presentation-test' ? '\0presentation-test' : null,
    load: id => id === '\0presentation-test' ? `
      export * as THREE from 'three';
      export { parseBlueprint, reconstructEntity } from 'wild-core/primitive';
      export { compileBlueprintComponents } from 'wild-core/compiler';
      export { createSceneGroupFromEntity, clearSceneObjectResources } from '/src/renderer/renderEntity.ts';
      export * from '/src/renderer/blueprintPresentationRuntime.ts';
      export * from '/src/renderer/worldEnvironmentRuntime.ts';
    ` : null,
  }], build: { outDir: directory, emptyOutDir: false, minify: false,
    rollupOptions: { input: 'virtual:presentation-test', preserveEntrySignatures: 'exports-only',
      output: { format: 'es', entryFileNames: 'test.mjs' } } } })
  const m = await import(pathToFileURL(join(directory, 'test.mjs')).href)
  const fixture = JSON.parse(await readFile(join(root, 'scripts/fixtures/presentation.json'), 'utf8'))
  const original = JSON.stringify(fixture)
  const blueprint = m.parseBlueprint(original)
  assert.deepEqual(blueprint.presentation, fixture.presentation)
  for (const presentation of [
    { style: 'unknown' }, { stage: 'unknown' }, { environment: { rain: 1.01 } }, { environment: { timeOfDay: -1 } },
    { environment: { wind: 'fast' } }, { camera: { position: [0,0,0], target: [0,0,0] } },
    { entrance: { type: 'assemble', duration: 0 } }, { entrance: { type: 'assemble', duration: -2 } },
    { entrance: { type: 'assemble', duration: 1, script: 'alert(1)' } }, { shader: 'arbitrary' },
  ]) assert.throws(() => m.parseBlueprint(JSON.stringify({ ...fixture, presentation })), /schema validation/)
  const compiled = m.compileBlueprintComponents(blueprint)
  assert.equal(compiled.diagnostics.length, 0)
  const entity = await m.reconstructEntity(compiled.blueprint)
  assert.equal(entity.diagnostics.filter(d => d.level === 'error').length, 0)
  const legacy = structuredClone(fixture)
  delete legacy.presentation
  const legacyEntity = await m.reconstructEntity(m.compileBlueprintComponents(m.parseBlueprint(JSON.stringify(legacy))).blueprint)
  assert.deepEqual(entity.meshes.map(v => [...v.geometry]), legacyEntity.meshes.map(v => [...v.geometry]))
  assert.deepEqual(entity.boundingBox, legacyEntity.boundingBox)
  assert.equal(JSON.stringify(fixture), original, '编译不能改写源蓝图')

  m.updateWorldEnvironmentState({ timeOfDay: 12, rain: .1, wetness: .2 })
  const baseline = { ...m.getWorldEnvironmentState() }
  const defaults = new m.BlueprintPresentationDefaults()
  defaults.apply(blueprint.presentation)
  assert.equal(m.getWorldRenderingState().style, 'toon')
  assert.equal(m.getWorldRenderingUniforms().toonEnabled.value, 1)
  assert.equal(m.getWorldEnvironmentState().rain, .3)
  defaults.apply()
  assert.deepEqual(m.getWorldEnvironmentState(), baseline, '打开旧稿必须恢复查看器环境')
  assert.equal(m.getWorldRenderingState().style, 'pbr')
  assert.equal(m.getWorldRenderingUniforms().toonEnabled.value, 0)

  const group = m.createSceneGroupFromEntity(entity)
  const runtime = new m.BlueprintPresentationRuntime(group)
  const instances = group.children.filter(v => v instanceof m.THREE.InstancedMesh)
  assert.ok(instances.length > 0, '必须覆盖真实 renderer 实例批处理')
  const snapshot = () => group.children.map(v => ({
    matrix: [...v.matrix.elements], auto: v.matrixAutoUpdate, culling: v.frustumCulled,
    instances: v.isInstancedMesh ? [...v.instanceMatrix.array] : null,
    vertices: v.isMesh ? [...v.geometry.attributes.position.array] : null,
  }))
  group.updateMatrixWorld(true)
  const before = snapshot()
  runtime.setStyle('toon')
  assert.ok(group.children.some(v => v.children.some(c => c.name === 'PresentationOutline')))
  runtime.start(blueprint.presentation.entrance)
  assert.equal(runtime.active, true)
  runtime.tick(.7)
  assert.notDeepEqual(snapshot().map(v => v.instances), before.map(v => v.instances))
  runtime.finish()
  assert.deepEqual(snapshot(), before, '取消动画必须精确恢复实例矩阵和显示状态')
  runtime.start(blueprint.presentation.entrance)
  runtime.tick(2)
  assert.equal(runtime.active, false)
  assert.equal(runtime.progress, 1)
  assert.deepEqual(snapshot(), before, '自然完成必须恢复最终静态场景')
  runtime.start(blueprint.presentation.entrance)
  runtime.reset()
  assert.deepEqual(snapshot(), before)
  assert.ok(group.children.every(v => !v.children.some(c => c.name === 'PresentationOutline')))
  m.clearSceneObjectResources(group)
  console.log('PASS: 原始契约拒错、旧稿几何一致、环境回退、真实实例批处理、完成/取消/释放均恢复原状')
} finally {
  if (dirname(directory) !== tmpdir() || !directory.split(/[\\/]/).pop().startsWith('wild-presentation-test-')) throw new Error('临时目录边界不匹配')
  await rm(directory, { recursive: true, force: true })
}
