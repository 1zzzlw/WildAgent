import { mkdtemp, readFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { build } from 'vite'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const outputDirectory = await mkdtemp(join(tmpdir(), 'wild-component-compiler-'))
const compilerPath = join(root, 'src/wild-compiler/index.ts').replaceAll('\\', '/')
const adapterPath = join(root, 'src/renderer/wildCoreAdapter.ts').replaceAll('\\', '/')
const scenePatchPath = join(root, 'src/wild/scenePatch.ts').replaceAll('\\', '/')
const componentSelectionPath = join(root, 'src/wild/componentSelection.ts').replaceAll('\\', '/')
const sceneStorePath = join(root, 'src/stores/sceneStore.ts').replaceAll('\\', '/')
const historyStorePath = join(root, 'src/stores/historyStore.ts').replaceAll('\\', '/')
const reconstructionClientPath = join(root, 'src/renderer/reconstructionClient.ts').replaceAll('\\', '/')
const renderEntityPath = join(root, 'src/renderer/renderEntity.ts').replaceAll('\\', '/')
const componentDragPath = join(root, 'src/wild/componentDrag.ts').replaceAll('\\', '/')
const agentBridgePath = join(root, 'src/agent/agentBridge.ts').replaceAll('\\', '/')
const agentStorePath = join(root, 'src/stores/agentStore.ts').replaceAll('\\', '/')
const presenceStorePath = join(root, 'src/extensions/presence/store.ts').replaceAll('\\', '/')
const materialAdapterPath = join(root, 'src/renderer/materialAdapter.ts').replaceAll('\\', '/')
const geometryEvaluationCases = JSON.parse(await readFile(
  join(root, 'scripts/fixtures/component-geometry-eval-cases.json'),
  'utf8',
))
const virtualEntry = `
export * from 'wildsrc:compiler';
export { parseWildBlueprint, reconstructWildEntity } from 'wildsrc:adapter';
export { applyPatchToBlueprint } from 'wildsrc:scene-patch';
export { resolveSelectableId, getRenderedElementIds } from 'wildsrc:component-selection';
export { useSceneStore } from 'wildsrc:scene-store';
export { useHistoryStore } from 'wildsrc:history-store';
export { reconstructScene } from 'wildsrc:reconstruction-client';
export { createSceneGroupFromEntity, toggleOpeningInteraction, toggleRuntimeInteraction } from 'wildsrc:render-entity';
export { createComponentTranslationChanges } from 'wildsrc:component-drag';
export { AgentBridge, agentBridge } from 'wildsrc:agent-bridge';
export { useAgentStore } from 'wildsrc:agent-store';
export { usePresenceStore } from 'wildsrc:presence-store';
export { createMaterialFromParams } from 'wildsrc:material-adapter';
export { BoxGeometry, Mesh, MeshBasicMaterial, PointLight, SpotLight, Texture, TextureLoader } from 'three';
export { createPinia, setActivePinia } from 'pinia';
export { reactive } from 'vue';
`

try {
  await build({
    root,
    logLevel: 'silent',
    plugins: [{
      name: 'wild-component-compiler-entry',
      resolveId(id) {
        if (id === 'virtual:wild-component-compiler') return '\0virtual:wild-component-compiler'
        if (id === 'wildsrc:compiler') return compilerPath
        if (id === 'wildsrc:adapter') return adapterPath
        if (id === 'wildsrc:scene-patch') return scenePatchPath
        if (id === 'wildsrc:component-selection') return componentSelectionPath
        if (id === 'wildsrc:scene-store') return sceneStorePath
        if (id === 'wildsrc:history-store') return historyStorePath
        if (id === 'wildsrc:reconstruction-client') return reconstructionClientPath
        if (id === 'wildsrc:render-entity') return renderEntityPath
        if (id === 'wildsrc:component-drag') return componentDragPath
        if (id === 'wildsrc:agent-bridge') return agentBridgePath
        if (id === 'wildsrc:agent-store') return agentStorePath
        if (id === 'wildsrc:presence-store') return presenceStorePath
        if (id === 'wildsrc:material-adapter') return materialAdapterPath
      },
      load(id) {
        if (id === '\0virtual:wild-component-compiler') return virtualEntry
      },
    }],
    build: {
      outDir: outputDirectory,
      emptyOutDir: false,
      minify: false,
      rollupOptions: {
        input: 'virtual:wild-component-compiler',
        preserveEntrySignatures: 'exports-only',
        output: {
          format: 'es',
          entryFileNames: 'component-compiler.mjs',
        },
      },
    },
  })

  const compiler = await import(
    `${pathToFileURL(join(outputDirectory, 'component-compiler.mjs')).href}?t=${Date.now()}`
  )
  assertCapabilities(compiler)
  assertGeometryEvaluationCases(compiler)
  assertRepresentativeComponents(compiler)
  await assertDoorWindowDepthAlignment(compiler)
  await assertInteractiveWindowSashes(compiler)
  await assertInteractiveLight(compiler)
  await assertSecondBatchComponents(compiler)
  assertCorniceAvoidsWallAttachments(compiler)
  assertArchitecturalRampAndCornice(compiler)
  assertCurvedWallAttachment(compiler)
  assertCompilationCache(compiler)
  assertComponentMapping(compiler)
  assertReadableCompileFailure(compiler)
  await assertRenderIntegration(compiler)
  await assertReconstructionDiagnostics(compiler)
  assertInvalidComponentSchemaIsRejected(compiler)
  assertScenePatchIntegration(compiler)
  assertMaterialTuningPatch(compiler)
  await assertPbrAssetIntegration(compiler)
  await assertComponentEditingHistory(compiler)
  await assertReactiveBlueprintWorkerTransfer(compiler)
  assertOpeningAnimationFrames(compiler)
  assertComponentTranslation(compiler)
  await assertGeneratedBlueprintLoadsFreshFile(compiler)
  assertPresenceUpdate(compiler)
  await assertExplicitServerSave(compiler)
  await inspectExternalBlueprint(compiler)
  console.log('Component compiler check passed: 10 component types, attachments, cache and interaction.')
} finally {
  await rm(outputDirectory, { recursive: true, force: true })
}

async function inspectExternalBlueprint(compiler) {
  const fixturePath = process.env.WILD_BLUEPRINT_CHECK
  if (!fixturePath) return
  // 外部问题样本可能本身包含与当前 Schema 无关的历史字段错误；此入口只诊断
  // 组件展开和空间占用，不替代正式 parseWildBlueprint 校验。
  const source = JSON.parse(await readFile(fixturePath, 'utf8'))
  const result = compiler.compileBlueprintComponents(source)
  const errors = result.diagnostics.filter(item => item.level === 'error')
  if (errors.length > 0) {
    throw new Error(`外部 Blueprint 组件编译失败: ${JSON.stringify(errors)}`)
  }
  const balconySlabs = result.blueprint.geometry.elements
    .filter(element => element.id.endsWith('__slab') && element.id.includes('balcony'))
    .map(element => ({ id: element.id, position: element.position, dimensions: element.dimensions }))
  const corniceSweeps = result.blueprint.geometry.elements
    .filter(element => element.id.includes('cornice') && element.id.includes('__sweep'))
    .map(element => ({ id: element.id, path: element.path }))
  console.log('External Blueprint overlap inspection:', JSON.stringify({
    balconySlabs,
    corniceSweeps,
  }))
}

function assertMaterialTuningPatch(compiler) {
  const source = createBlueprint()
  source.materials = {
    stone_shared: {
      baseColor: [1, 1, 1], roughness: 0.55, metallic: 0, albedo: 1,
      lightingCondition: 'D65_noon', textureSet: 'pbr_0123456789abcdef01234567',
      normalScale: 1, uvScale: [1, 1],
    },
  }
  source.geometry.elements[0].material = 'stone_shared'
  source.geometry.elements[1].material = 'stone_shared'
  const result = compiler.applyPatchToBlueprint(source, {
    type: 'scene_patch', patch_id: 'material-tuning-eval', base_revision: 1,
    source: 'agent', mode: 'proposal', requires_confirmation: true,
    operations: [{
      op: 'tune_material', id: 'front_wall', material_field: 'material',
      new_name: 'stone_front_tuned',
      changes: { roughness: 0.82, normalScale: 1.35, uvScale: [2, 2] },
      rationale: '增强石材表面层次',
    }],
  })
  assertEqual(result.geometry.elements[0].material, 'stone_front_tuned', '选中墙没有绑定调优材质')
  assertEqual(result.geometry.elements[1].material, 'stone_shared', '调优意外影响了共享材质的其他墙')
  assertEqual(result.materials.stone_shared.roughness, 0.55, '原共享材质被修改')
  assertEqual(result.materials.stone_front_tuned.textureSet, 'pbr_0123456789abcdef01234567', '调优丢失纹理资产引用')
  assertEqual(result.materials.stone_front_tuned.roughness, 0.82, '调优参数未应用')
}

async function assertPbrAssetIntegration(compiler) {
  const source = createBlueprint()
  const assetId = 'pbr_0123456789abcdef01234567'
  const image = {
    encoding: 'url',
    uri: `/api/assets/${assetId}/files/baseColor.png`,
    mimeType: 'image/png',
    sha256: 'a'.repeat(64),
    byteSize: 128,
    colorSpace: 'srgb',
  }
  const asset = {
    schemaVersion: '1.0', assetId, kind: 'pbr_texture_set', name: 'Stone',
    contentHash: `sha256:${'b'.repeat(64)}`,
    source: { type: 'local_upload' }, license: 'CC0',
    maps: { baseColor: image }, createdAt: '2026-08-10T00:00:00Z',
  }
  const patched = compiler.applyPatchToBlueprint(source, {
    type: 'scene_patch', patch_id: 'pbr-eval', base_revision: 1,
    source: 'user', mode: 'apply', requires_confirmation: false,
    operations: [
      { op: 'upsert_asset', asset_id: assetId, asset },
      {
        op: 'upsert_material', name: 'stone_pbr',
        material: {
          baseColor: [1, 1, 1], roughness: 0.75, metallic: 0, albedo: 1,
          lightingCondition: 'D65_noon', textureSet: assetId, uvScale: [2, 2],
        },
      },
      { op: 'update_element', id: 'front_wall', changes: { material: 'stone_pbr' } },
    ],
  })
  if (patched.assets?.[assetId]?.maps.baseColor.uri !== image.uri) {
    throw new Error('ScenePatch 没有写入 PBR 资产清单')
  }

  const entity = await compiler.reconstructWildEntity(patched)
  const meshIndex = entity.meshes.findIndex(mesh => mesh.elementId === 'front_wall')
  const resolved = entity.materialParams[meshIndex]?.textures?.baseColor
  if (resolved?.encoding !== 'url' || resolved.uri !== image.uri) {
    throw new Error(`wild-core 没有解析 textureSet: ${JSON.stringify(resolved)}`)
  }

  const loadedUrls = []
  const originalLoad = compiler.TextureLoader.prototype.load
  compiler.TextureLoader.prototype.load = function (url, onLoad) {
    loadedUrls.push(url)
    const texture = new compiler.Texture()
    onLoad?.(texture)
    return texture
  }
  try {
    const material = compiler.createMaterialFromParams(entity.materialParams[meshIndex])
    if (material.map === null || !loadedUrls.includes(image.uri)) {
      throw new Error(`Three.js 没有通过 URL 加载 PBR 纹理: ${JSON.stringify(loadedUrls)}`)
    }
    material.dispose()
  } finally {
    compiler.TextureLoader.prototype.load = originalLoad
  }
}

function assertCapabilities(compiler) {
  const types = compiler.getComponentCapabilities().map(item => item.type)
  assertEqual(types, [
    'balcony',
    'bay_window',
    'canopy',
    'chimney',
    'cornice',
    'door',
    'light',
    'railing',
    'ramp',
    'window',
  ], '组合构件能力列表不正确')
}

async function assertSecondBatchComponents(compiler) {
  const source = createBlueprint()
  source.geometry.components = [
    {
      type: 'canopy', id: 'test_canopy', parentWall: 'front_wall',
      from: [0.5, 2.5, 0], width: 2, depth: 1, thickness: 0.12, supportCount: 2,
    },
    {
      type: 'balcony', id: 'test_balcony', parentWall: 'front_wall',
      from: [3, 1.2, 0], width: 2.4, depth: 1.2, slabThickness: 0.18,
    },
    {
      type: 'ramp', id: 'test_ramp', from: [0, 0, 5], to: [3, 0.45, 5],
      width: 1.2, thickness: 0.18, railingSides: 'both',
    },
    {
      type: 'bay_window', id: 'test_bay', parentWall: 'side_wall',
      from: [1.2, 0.9, 0], width: 1.8, height: 1.2, projectionDepth: 0.45,
    },
    {
      type: 'cornice', id: 'test_cornice', path: [[0, 3, 0], [4, 3, 0]],
      profile: [[-0.08, -0.08], [0.08, -0.08], [0.08, 0.08], [-0.08, 0.08]],
    },
    {
      type: 'chimney', id: 'test_chimney', position: [6, 0, 4],
      width: 0.7, depth: 0.7, height: 2,
    },
  ]
  const parsed = compiler.parseWildBlueprint(JSON.stringify(source))
  const result = compiler.compileBlueprintComponents(parsed)
  assertEqual(result.diagnostics, [], '第二批组合构件不应产生诊断')
  for (const component of source.geometry.components) {
    const generated = result.mapping.generatedElementIdsByComponentId[component.id]
    if (!generated?.length) throw new Error(`${component.type} 没有生成基础元素`)
  }
  const balconyIds = new Set(result.mapping.generatedElementIdsByComponentId.test_balcony)
  const balconyElements = result.blueprint.geometry.elements.filter(element => balconyIds.has(element.id))
  const balconySlab = balconyElements.find(element => element.id === 'test_balcony__slab')
  if (!balconySlab || Math.abs(balconySlab.position[2] + 0.72) > 1e-9) {
    throw new Error(`正立面阳台没有向建筑外侧悬挑: ${JSON.stringify(balconySlab)}`)
  }
  const balconyZCoordinates = balconyElements.flatMap(element => {
    if (element.type === 'primitive' && Array.isArray(element.position)) return [element.position[2]]
    if (element.type === 'beam') return [element.from[2], element.to[2]]
    return []
  })
  if (Math.max(...balconyZCoordinates) > -0.12 + 1e-9) {
    throw new Error(`阳台或内嵌栏杆进入了建筑内部: ${JSON.stringify(balconyZCoordinates)}`)
  }
  const corniceElements = result.blueprint.geometry.elements.filter(
    element => element.id.startsWith('test_cornice__sweep'),
  )
  if (corniceElements.length !== 1 || corniceElements[0].id !== 'test_cornice__sweep') {
    throw new Error('不同标高的檐口被阳台错误裁剪')
  }
  const entity = await compiler.reconstructWildEntity(parsed)
  const errors = entity.diagnostics.filter(item => item.level === 'error')
  if (errors.length > 0) {
    throw new Error(`第二批组合构件渲染失败: ${JSON.stringify(errors)}`)
  }
}

function assertCorniceAvoidsWallAttachments(compiler) {
  const source = createBlueprint()
  source.geometry.components = [
    {
      type: 'balcony', id: 'overlap_balcony', parentWall: 'front_wall',
      from: [2.5, 3, 0], width: 2.5, depth: 1.2, slabThickness: 0.15,
    },
    {
      type: 'cornice', id: 'layer_cornice', path: [[0, 3, -0.42], [8, 3, -0.42]],
      profile: [[-0.15, -0.05], [0.15, -0.05], [0.15, 0.05], [-0.15, 0.05]],
      closedProfile: true,
    },
  ]
  const result = compiler.compileBlueprintComponents(source)
  const sweeps = result.blueprint.geometry.elements.filter(
    element => element.id.startsWith('layer_cornice__sweep'),
  )
  if (sweeps.length !== 2) throw new Error(`檐口没有避让阳台占用区间: ${JSON.stringify(sweeps)}`)
  const intervals = sweeps.map(element => [element.path[0][0], element.path[1][0]])
  assertVec3ArrayClose(intervals, [[0, 2.35], [5.15, 8]], '檐口裁剪区间错误')
}

function assertArchitecturalRampAndCornice(compiler) {
  const rampSource = createBlueprint()
  rampSource.geometry.components = [{
    type: 'ramp', id: 'architectural_ramp', from: [0, 0, 5], to: [5.4, 0.45, 5],
    width: 1.5, thickness: 0.18, railingSides: 'both', railingHeight: 1.1,
  }]
  const rampResult = compiler.compileBlueprintComponents(rampSource)
  const surface = rampResult.blueprint.geometry.elements.find(
    element => element.id === 'architectural_ramp__surface',
  )
  if (surface?.type !== 'primitive' || surface.shape !== 'profile_sweep') {
    throw new Error(`坡道主体不是连续斜面: ${JSON.stringify(surface)}`)
  }
  for (const expectedId of ['architectural_ramp__curb_left', 'architectural_ramp__curb_right']) {
    if (!rampResult.blueprint.geometry.elements.some(element => element.id === expectedId)) {
      throw new Error(`坡道缺少侧缘挡台: ${expectedId}`)
    }
  }

  const corniceSource = createBlueprint()
  corniceSource.geometry.elements = [
    { type: 'wall', id: 'wall_n', from: [0, 0, 0], to: [8, 3, 0], thickness: 0.24 },
    { type: 'wall', id: 'wall_e', from: [8, 0, 0], to: [8, 3, 6], thickness: 0.24 },
    { type: 'wall', id: 'wall_s', from: [8, 0, 6], to: [0, 3, 6], thickness: 0.24 },
    { type: 'wall', id: 'wall_w', from: [0, 0, 6], to: [0, 3, 0], thickness: 0.24 },
    { type: 'roof', id: 'roof_main', roofType: 'gable', span: 8, depth: 6, height: 2, thickness: 0.18 },
  ]
  corniceSource.geometry.components = [{
    type: 'cornice', id: 'roof_cornice', parentRoof: 'roof_main',
    path: [[-4, 0, -3], [-4, 0, 3]],
    profile: [[-0.16, -0.14], [0.16, -0.14], [0.1, 0], [-0.16, 0.08]],
  }]
  const corniceResult = compiler.compileBlueprintComponents(corniceSource)
  const sweep = corniceResult.blueprint.geometry.elements.find(
    element => element.id === 'roof_cornice__sweep',
  )
  assertEqual(
    sweep?.path,
    [[0, 3, 0], [0, 3, 6]],
    '未显式设置 position 的屋顶无法正确定位檐口',
  )

  const steppedCorniceSource = createBlueprint()
  steppedCorniceSource.geometry.elements = [
    { type: 'wall', id: 'base_n', from: [0, 0, 0], to: [18, 3.2, 0], thickness: 0.24 },
    { type: 'wall', id: 'base_e', from: [18, 0, 0], to: [18, 3.2, 12], thickness: 0.24 },
    { type: 'wall', id: 'base_s', from: [18, 0, 12], to: [0, 3.2, 12], thickness: 0.24 },
    { type: 'wall', id: 'base_w', from: [0, 0, 12], to: [0, 3.2, 0], thickness: 0.24 },
    { type: 'wall', id: 'upper_n', from: [3, 3.2, 0.8], to: [15, 6.4, 0.8], thickness: 0.24 },
    { type: 'wall', id: 'upper_e', from: [15, 3.2, 0.8], to: [15, 6.4, 10.8], thickness: 0.24 },
    { type: 'wall', id: 'upper_s', from: [15, 3.2, 10.8], to: [3, 6.4, 10.8], thickness: 0.24 },
    { type: 'wall', id: 'upper_w', from: [3, 3.2, 10.8], to: [3, 6.4, 0.8], thickness: 0.24 },
    { type: 'roof', id: 'stepped_roof', roofType: 'flat', span: 13, depth: 11, height: 0.3, thickness: 0.3 },
  ]
  steppedCorniceSource.geometry.components = [{
    type: 'cornice', id: 'stepped_cornice', parentRoof: 'stepped_roof',
    path: [[-6.5, 0, -5.5], [-6.5, 0, 5.5]],
    profile: [[-0.1, -0.1], [0.1, -0.1], [0.1, 0.1], [-0.1, 0.1]],
  }]
  const steppedCorniceResult = compiler.compileBlueprintComponents(steppedCorniceSource)
  const steppedSweep = steppedCorniceResult.blueprint.geometry.elements.find(
    element => element.id === 'stepped_cornice__sweep',
  )
  assertVec3ArrayClose(
    steppedSweep?.path,
    [[2.5, 6.7, 0.3], [2.5, 6.7, 11.3]],
    '退台屋顶檐口仍错误使用首层总包围盒定位',
  )

  compiler.clearComponentCompilationCache()
  compiler.compileBlueprintComponents(corniceSource)
  corniceSource.geometry.elements[0].to[0] = 10
  const movedResult = compiler.compileBlueprintComponents(corniceSource)
  const movedSweep = movedResult.blueprint.geometry.elements.find(
    element => element.id === 'roof_cornice__sweep',
  )
  assertEqual(movedSweep?.path?.[0]?.[0], 1, '结构墙变化后檐口缓存没有失效')
  assertEqual(
    compiler.getComponentCompilationCacheStats().misses,
    2,
    '自动定位屋顶的檐口没有把结构墙纳入依赖缓存',
  )
}

function assertCurvedWallAttachment(compiler) {
  const source = createBlueprint()
  source.geometry.elements = [{
    type: 'wall', id: 'arc_wall', from: [5, 0, 0], to: [0, 3, 5],
    thickness: 0.24, curve: { type: 'arc', center: [0, 0, 0], sweep: 90, segments: 32 },
  }]
  source.geometry.components = [{
    type: 'window', id: 'arc_window', parentWall: 'arc_wall',
    from: [1, 0.9, 0], width: 1.2, height: 1.2,
  }]
  const result = compiler.compileBlueprintComponents(
    compiler.parseWildBlueprint(JSON.stringify(source)),
  )
  assertEqual(result.diagnostics, [], '曲线墙窗不应产生编译诊断')
  if (!result.blueprint.geometry.elements.some(element => element.id === 'arc_window__opening')) {
    throw new Error('曲线墙窗没有生成 opening')
  }
}

function assertCompilationCache(compiler) {
  compiler.clearComponentCompilationCache()
  const source = createBlueprint()
  compiler.compileBlueprintComponents(source)
  compiler.compileBlueprintComponents(source)
  const stats = compiler.getComponentCompilationCacheStats()
  if (stats.hits < source.geometry.components.length || stats.misses !== source.geometry.components.length) {
    throw new Error(`组件增量缓存未命中: ${JSON.stringify(stats)}`)
  }
}

function assertGeometryEvaluationCases(compiler) {
  for (const testCase of geometryEvaluationCases.validCases) {
    const result = compiler.compileBlueprintComponents(createEvaluationBlueprint(testCase.component))
    assertEqual(result.diagnostics, [], `${testCase.id} 不应产生编译诊断`)
    const generated = result.mapping.generatedElementIdsByComponentId[testCase.component.id] || []
    assertEqual(generated.length, testCase.expectedGeneratedCount, `${testCase.id} 生成数量不正确`)
    const generatedTypes = result.blueprint.geometry.elements
      .filter(element => generated.includes(element.id))
      .map(element => element.type)
    assertEqual(generatedTypes, testCase.expectedTypes, `${testCase.id} 生成类型不正确`)
  }

  for (const testCase of geometryEvaluationCases.invalidCases) {
    const result = compiler.compileBlueprintComponents(createEvaluationBlueprint(testCase.component))
    if (
      result.diagnostics.length !== 1
      || !result.diagnostics[0].message.includes(testCase.expectedError)
    ) {
      throw new Error(`${testCase.id} 未产生预期诊断: ${JSON.stringify(result.diagnostics)}`)
    }
  }
  console.log(`Geometry evaluation passed: ${geometryEvaluationCases.validCases.length + geometryEvaluationCases.invalidCases.length} cases.`)
}

function assertRepresentativeComponents(compiler) {
  const source = createBlueprint()
  const snapshot = JSON.stringify(source)
  const result = compiler.compileBlueprintComponents(source)

  assertEqual(result.diagnostics, [], '合法组合构件不应产生诊断')
  if (JSON.stringify(source) !== snapshot) {
    throw new Error('组合构件编译修改了源 Blueprint')
  }
  if ('components' in result.blueprint.geometry) {
    throw new Error('编译结果不应继续包含 geometry.components')
  }

  const elements = result.blueprint.geometry.elements
  assertEqual(elements.length, 19, '展开后的元素数量不正确')
  const ids = elements.map(element => element.id)
  if (new Set(ids).size !== ids.length) {
    throw new Error(`编译结果存在重复 ID: ${JSON.stringify(ids)}`)
  }

  assertTypesByPrefix(elements, 'front_door__', ['opening', 'primitive', 'primitive', 'primitive'])
  assertTypesByPrefix(elements, 'side_window__', [
    'opening',
    'primitive',
    'primitive',
    'primitive',
    'primitive',
    'primitive',
    'primitive',
  ])
  assertTypesByPrefix(elements, 'terrace_railing__', [
    'primitive',
    'primitive',
    'primitive',
    'primitive',
    'beam',
    'beam',
  ])

  const sideFrame = elements.find(element => element.id === 'side_window__frame_left')
  if (!sideFrame || Math.abs(sideFrame.rotation[1] + Math.PI / 2) > 1e-9) {
    throw new Error(`侧墙窗框旋转错误: ${JSON.stringify(sideFrame)}`)
  }
}

async function assertInteractiveWindowSashes(compiler) {
  const source = createBlueprint()
  source.geometry.components = [{
    type: 'window',
    id: 'interactive_window',
    parentWall: 'front_wall',
    from: [2, 0.9, 0],
    width: 2,
    height: 1.2,
    verticalMullions: 1,
    frameMaterial: 'frame',
    glassMaterial: 'glass',
    interaction: { mode: 'swing', hingeSide: 'right', openAngle: 70 },
  }]

  const result = compiler.compileBlueprintComponents(source)
  assertEqual(result.diagnostics, [], '交互窗不应产生编译诊断')
  const leftSash = result.blueprint.geometry.elements.find(
    element => element.id === 'interactive_window__sash_left',
  )
  const rightSash = result.blueprint.geometry.elements.find(
    element => element.id === 'interactive_window__sash_right',
  )
  if (!leftSash || !rightSash) throw new Error('交互窗没有保留左右两扇')
  if (leftSash._interaction?.mode !== 'swing') throw new Error('左窗扇缺少开合行为')
  if (rightSash._interaction?.mode !== 'swing') throw new Error('活动窗扇缺少开合行为')
  if (leftSash._interaction.openRotation[1] <= leftSash._interaction.closedRotation[1]) {
    throw new Error('左窗扇没有沿左铰链方向开启')
  }
  if (rightSash._interaction.openRotation[1] >= rightSash._interaction.closedRotation[1]) {
    throw new Error('右窗扇没有沿右铰链方向开启')
  }

  const entity = await compiler.reconstructWildEntity(source)
  const sashMeshes = entity.meshes.filter(mesh => mesh.elementId?.startsWith('interactive_window__sash_'))
  assertEqual(sashMeshes.length, 2, 'Core 重建后没有保留两扇窗')
  assertEqual(
    sashMeshes.filter(mesh => mesh.interactive).map(mesh => mesh.elementId),
    ['interactive_window__sash_left', 'interactive_window__sash_right'],
    '左右窗扇都应分别参与交互',
  )
}

async function assertDoorWindowDepthAlignment(compiler) {
  const source = createBlueprint()
  const result = compiler.compileBlueprintComponents(source)
  assertEqual(result.diagnostics, [], '默认门窗深度不应产生编译诊断')

  const doorFrame = result.blueprint.geometry.elements.find(
    element => element.id === 'front_door__frame_left',
  )
  const doorLeaf = result.blueprint.geometry.elements.find(
    element => element.id === 'front_door__opening',
  )
  const windowFrame = result.blueprint.geometry.elements.find(
    element => element.id === 'side_window__frame_left',
  )
  const windowGlass = result.blueprint.geometry.elements.find(
    element => element.id === 'side_window__opening',
  )
  assertEqual(doorFrame?.dimensions?.[2], 0.24, '门框默认深度必须继承父墙厚度')
  assertEqual(windowFrame?.dimensions?.[2], 0.24, '窗框默认深度必须继承父墙厚度')
  assertEqual(doorLeaf?.depth, 0.04, '门扇默认厚度错误')
  assertEqual(windowGlass?.depth, 0.012, '玻璃默认厚度错误')

  const entity = await compiler.reconstructWildEntity(source)
  const doorMesh = entity.meshes.find(mesh => mesh.elementId === 'front_door__opening')
  const glassMesh = entity.meshes.find(mesh => mesh.elementId === 'side_window__opening')
  assertEqual(localAxisExtent(doorMesh, 2), 0.04, '门扇没有生成真实厚度')
  assertEqual(localAxisExtent(glassMesh, 2), 0.012, '玻璃没有生成真实厚度')

  const invalid = createBlueprint()
  invalid.geometry.components = [{
    type: 'door', id: 'invalid_depth_door', parentWall: 'front_wall',
    from: [1, 0, 0], width: 1, height: 2.1,
    frameDepth: 0.03, leafDepth: 0.05,
  }]
  const invalidResult = compiler.compileBlueprintComponents(invalid)
  if (!invalidResult.diagnostics.some(item => (
    item.elementId === 'invalid_depth_door' && item.message.includes('leafDepth')
  ))) {
    throw new Error('门扇厚于门框时没有产生可读编译诊断')
  }
}

function localAxisExtent(mesh, axis) {
  if (!mesh) throw new Error('深度回归场景缺少预期网格')
  const values = []
  for (let index = axis; index < mesh.geometry.length; index += 3) values.push(mesh.geometry[index])
  const extent = Math.max(...values) - Math.min(...values)
  return Math.round(extent * 1_000_000) / 1_000_000
}

async function assertInteractiveLight(compiler) {
  const source = createBlueprint()
  source.geometry.components = [{
    type: 'light', id: 'movable_bulb', position: [1, 2.4, 1],
    fixtureType: 'bulb', lightType: 'point', lowIntensity: 20, highIntensity: 80,
    distance: 10, draggable: true,
  }]
  const parsed = compiler.parseWildBlueprint(JSON.stringify(source))
  const result = compiler.compileBlueprintComponents(parsed)
  assertEqual(result.diagnostics, [], '灯泡不应产生编译诊断')
  const bulb = result.blueprint.geometry.elements.find(element => element.id === 'movable_bulb__bulb')
  const base = result.blueprint.geometry.elements.find(element => element.id === 'movable_bulb__base')
  if (bulb?._interaction?.kind !== 'light') throw new Error('灯泡缺少灯光交互元数据')
  if (!bulb?._draggable || !base?._draggable) throw new Error('灯具子网格没有继承拖动开关')

  const entity = await compiler.reconstructWildEntity(parsed)
  const meshes = entity.meshes.filter(mesh => mesh.elementId?.startsWith('movable_bulb__'))
  if (meshes.length !== 2 || meshes.some(mesh => !mesh.draggable)) {
    throw new Error('Core 没有透传灯具拖动元数据')
  }
  const group = compiler.createSceneGroupFromEntity(entity)
  const lightMesh = group.children.find(child => child.userData.interaction?.kind === 'light')
  if (!lightMesh || !lightMesh.children.some(child => child instanceof compiler.PointLight)) {
    throw new Error('renderer 没有创建真实点光源')
  }

  const tableSource = createBlueprint()
  tableSource.geometry.components = [{
    type: 'light', id: 'table_lamp', fixtureType: 'table_lamp', position: [2, 0.8, 1],
    height: 0.72, shadeRadius: 0.28, lightType: 'point', draggable: true,
  }]
  const tableResult = compiler.compileBlueprintComponents(tableSource)
  assertEqual(tableResult.diagnostics, [], '台灯不应产生编译诊断')
  assertTypesByPrefix(tableResult.blueprint.geometry.elements, 'table_lamp__', [
    'primitive', 'primitive', 'primitive', 'primitive',
  ])
  for (const suffix of ['bulb', 'base', 'stem', 'shade']) {
    if (!tableResult.blueprint.geometry.elements.some(element => element.id === `table_lamp__${suffix}`)) {
      throw new Error(`台灯缺少 ${suffix} 子构件`)
    }
  }

  const originalRequestAnimationFrame = globalThis.requestAnimationFrame
  const queue = []
  let now = performance.now()
  globalThis.requestAnimationFrame = callback => {
    queue.push(callback)
    return queue.length
  }
  const drain = () => {
    let frames = 0
    while (queue.length > 0) {
      if (++frames > 100) throw new Error('灯光动画没有结束')
      now += 16
      queue.shift()(now)
    }
  }
  try {
    for (const expected of [1, 2, 0]) {
      if (!compiler.toggleRuntimeInteraction(lightMesh)) throw new Error('灯光右键交互没有启动')
      drain()
      if (lightMesh.userData.lightLevel !== expected) {
        throw new Error(`灯光循环状态错误: ${lightMesh.userData.lightLevel}`)
      }
    }
  } finally {
    if (originalRequestAnimationFrame === undefined) delete globalThis.requestAnimationFrame
    else globalThis.requestAnimationFrame = originalRequestAnimationFrame
  }
}

function assertComponentTranslation(compiler) {
  const source = createBlueprint()
  const wall = source.geometry.elements.find(element => element.id === 'side_wall')
  const attached = {
    type: 'window', id: 'drag_window', parentWall: wall.id,
    from: [1, 0.9, 0], width: 1.5, height: 1.2, draggable: true,
  }
  const attachedChanges = compiler.createComponentTranslationChanges(
    attached,
    [0, 0.2, 1],
    source.geometry.elements,
  )
  assertEqual(attachedChanges.from, [2, 1.1, 0], '墙挂组件世界位移没有转换为父墙局部坐标')

  const lightChanges = compiler.createComponentTranslationChanges(
    { type: 'light', id: 'drag_light', position: [1, 2, 3] },
    [0.5, -0.5, 1],
    source.geometry.elements,
  )
  assertEqual(lightChanges.position, [1.5, 1.5, 4], '自由组件拖动没有更新 position')
}

async function assertGeneratedBlueprintLoadsFreshFile(compiler) {
  const originalLocalStorage = globalThis.localStorage
  const originalFetch = globalThis.fetch
  const storedValues = new Map()
  const requests = []
  globalThis.localStorage = {
    getItem: key => storedValues.get(key) ?? null,
    setItem: (key, value) => storedValues.set(key, String(value)),
    removeItem: key => storedValues.delete(key),
    clear: () => storedValues.clear(),
  }

  try {
    compiler.setActivePinia(compiler.createPinia())
    const sceneStore = compiler.useSceneStore()
    const agentStore = compiler.useAgentStore()
    const sessionId = agentStore.createSession('generated-blueprint-check')
    agentStore.switchToSession(sessionId)
    const bridge = new compiler.AgentBridge('ws://localhost/ws/agent')
    globalThis.fetch = async (url, options) => {
      requests.push({ url: String(url), options })
      const fetchedBlueprint = createBlueprint()
      fetchedBlueprint.meta.name = 'HTTP 回退建筑'
      return {
        ok: true,
        status: 200,
        json: async () => fetchedBlueprint,
      }
    }

    await bridge.handleBlueprintGenerated({
      type: 'blueprint_generated',
      request_id: 'req_fresh_file',
      session_id: sessionId,
      filename: `${sessionId}.wild`,
      file_url: `/api/scenes/${sessionId}.wild`,
    })
    assertEqual(requests.length, 1, '生成事件应只拉取一次 Blueprint 文件')
    assertEqual(requests[0].options.cache, 'no-store', '生成文件拉取必须禁用同名文件缓存')
    if (!requests[0].url.includes('request_id=req_fresh_file')) {
      throw new Error('生成文件拉取没有携带请求级缓存隔离参数')
    }
    assertEqual(sceneStore.document.blueprint.meta.name, 'HTTP 回退建筑', '最新生成文件没有加载')
    if (!sceneStore.reconstructed) throw new Error('生成文件加载后没有完成场景重建')
  } finally {
    if (originalFetch === undefined) delete globalThis.fetch
    else globalThis.fetch = originalFetch
    if (originalLocalStorage === undefined) delete globalThis.localStorage
    else globalThis.localStorage = originalLocalStorage
  }
}

function assertPresenceUpdate(compiler) {
  const originalLocalStorage = globalThis.localStorage
  const storedValues = new Map()
  storedValues.set('wild_presence_visitor_name', '  张工  ')
  globalThis.localStorage = {
    getItem: key => storedValues.get(key) ?? null,
    setItem: (key, value) => storedValues.set(key, String(value)),
    removeItem: key => storedValues.delete(key),
    clear: () => storedValues.clear(),
  }

  try {
    compiler.setActivePinia(compiler.createPinia())
    const presenceStore = compiler.usePresenceStore()
    assertEqual(presenceStore.visitorName, '张工', '首次加载没有读取 localStorage 访客名称')
    assertEqual(presenceStore.hasVisitorName, true, '已有访客名称仍会触发首次输入页')
    const bridge = new compiler.AgentBridge('ws://localhost/ws/agent')
    bridge.handleMessage({
      type: 'presence_update',
      online_count: 2,
      clients: [
        { id: 'client_a', display_name: '张工', masked_ip: '113.96.*.*', region: '广东省', connected_at: 1 },
        { id: 'client_b', display_name: '李工', masked_ip: '1.2.*.*', region: '北京市', connected_at: 2 },
      ],
    })
    assertEqual(presenceStore.onlineCount, 2, '在线人数没有写入 Presence Store')
    assertEqual(presenceStore.onlineClients.length, 2, '在线列表没有写入 Presence Store')
    assertEqual(presenceStore.onlineClients[0].display_name, '张工', '在线列表没有访客名称')
    assertEqual(presenceStore.onlineClients[0].masked_ip, '113.96.*.*', '前端在线列表 IP 不是脱敏值')

    if (!presenceStore.setVisitorName('  王 工  ')) throw new Error('合法访客名称设置失败')
    assertEqual(presenceStore.visitorName, '王 工', '访客名称没有规范化保存')

    bridge.disconnect()
    assertEqual(presenceStore.onlineCount, 0, 'WebSocket 断开后在线人数没有归零')
    assertEqual(presenceStore.onlineClients.length, 0, 'WebSocket 断开后在线列表没有清空')
  } finally {
    if (originalLocalStorage === undefined) delete globalThis.localStorage
    else globalThis.localStorage = originalLocalStorage
  }
}

async function assertExplicitServerSave(compiler) {
  const originalLocalStorage = globalThis.localStorage
  const storedValues = new Map()
  globalThis.localStorage = {
    getItem: key => storedValues.get(key) ?? null,
    setItem: (key, value) => storedValues.set(key, String(value)),
    removeItem: key => storedValues.delete(key),
    clear: () => storedValues.clear(),
  }
  compiler.setActivePinia(compiler.createPinia())
  const sceneStore = compiler.useSceneStore()
  const agentStore = compiler.useAgentStore()
  const sessionId = agentStore.createSession('save-check')
  agentStore.switchToSession(sessionId)
  sceneStore.loadBlueprint(createBlueprint(), 'save-check')
  await waitForReconstruction(sceneStore)

  const originalFetch = globalThis.fetch
  const requests = []
  globalThis.fetch = async (url, options) => {
    requests.push({ url: String(url), options })
    return { ok: true, status: 200 }
  }
  try {
    const applied = await sceneStore.applyPatch({
      type: 'scene_patch',
      patch_id: 'explicit-save-check',
      base_revision: sceneStore.document.revision,
      source: 'user',
      mode: 'apply',
      requires_confirmation: false,
      summary: '添加灯泡草稿',
      operations: [{
        op: 'add_component',
        component: {
          type: 'light', id: 'draft_light', position: [0, 2.4, 0],
          draggable: true,
        },
      }],
    })
    if (!applied || !sceneStore.document.dirty) throw new Error('编辑后没有形成未保存草稿')
    assertEqual(requests.length, 0, '应用本地 Patch 时不应自动写入服务器')

    const saved = await compiler.agentBridge.syncBlueprintToBackend(
      sceneStore.document.blueprint,
    )
    if (!saved) throw new Error('显式保存请求失败')
    assertEqual(requests.length, 1, '显式保存应只产生一次服务器请求')
    const saveUrl = new URL(requests[0].url)
    const expectedSuffix = `/${sessionId}_component_compiler_check.wild`
    if (!/^\/api\/scenes\/\d{4}-\d{2}-\d{2}\//.test(saveUrl.pathname)
      || !saveUrl.pathname.endsWith(expectedSuffix)) {
      throw new Error(`保存目标会话错误: ${requests[0].url}`)
    }
    assertEqual(requests[0].options.method, 'PUT', '保存接口必须使用 PUT 覆盖语义')
    const savedBlueprint = JSON.parse(requests[0].options.body)
    if (!savedBlueprint.geometry.components.some(component => component.id === 'draft_light')) {
      throw new Error('显式保存请求没有携带最新组件草稿')
    }
    sceneStore.markSaved()
    if (sceneStore.document.dirty) throw new Error('服务器保存成功后未清除 dirty 状态')
  } finally {
    if (originalFetch === undefined) delete globalThis.fetch
    else globalThis.fetch = originalFetch
    if (originalLocalStorage === undefined) delete globalThis.localStorage
    else globalThis.localStorage = originalLocalStorage
  }
}

function assertReadableCompileFailure(compiler) {
  const source = createBlueprint()
  source.geometry.components = [{
    type: 'door',
    id: 'broken_door',
    parentWall: 'missing_wall',
    from: [0, 0, 0],
    width: 0.9,
    height: 2.1,
  }]
  const result = compiler.compileBlueprintComponents(source)
  assertEqual(result.blueprint.geometry.elements.length, 2, '失败组件不应追加部分子元素')
  assertEqual(result.diagnostics.length, 1, '失败组件应产生一条诊断')
  const diagnostic = result.diagnostics[0]
  if (
    diagnostic.code !== 'COMPONENT_COMPILE_FAILED'
    || diagnostic.elementId !== 'broken_door'
    || !diagnostic.message.includes('missing_wall')
  ) {
    throw new Error(`组件失败诊断不可读: ${JSON.stringify(diagnostic)}`)
  }
}

function assertComponentMapping(compiler) {
  const result = compiler.compileBlueprintComponents(createBlueprint())
  assertEqual(
    result.mapping.generatedElementIdsByComponentId.front_door,
    [
      'front_door__opening',
      'front_door__frame_left',
      'front_door__frame_right',
      'front_door__frame_top',
    ],
    '组件到生成元素的映射不正确',
  )
  assertEqual(
    compiler.resolveSelectableId('front_door__frame_left', result.mapping),
    'front_door',
    '临时元素未回溯到源组件',
  )
  assertEqual(
    compiler.getRenderedElementIds('front_wall', result.mapping),
    ['front_wall'],
    '原生元素选择映射不正确',
  )
}

async function assertRenderIntegration(compiler) {
  const source = createBlueprint()
  const parsed = compiler.parseWildBlueprint(JSON.stringify(source))
  if (parsed.geometry.components?.length !== 3) {
    throw new Error('parseWildBlueprint 未保留 geometry.components')
  }
  const entity = await compiler.reconstructWildEntity(parsed)
  const errors = entity.diagnostics.filter(item => item.level === 'error')
  if (errors.length > 0) {
    throw new Error(`组合构件渲染接入失败: ${JSON.stringify(errors)}`)
  }
  for (const expectedId of [
    'front_door__opening',
    'side_window__frame_left',
    'terrace_railing__rail_001_001',
  ]) {
    if (!entity.meshes.some(mesh => mesh.elementId === expectedId)) {
      throw new Error(`渲染结果缺少组合构件子元素: ${expectedId}`)
    }
  }
  if (entity.componentMapping.componentIdByGeneratedElementId['side_window__frame_left'] !== 'side_window') {
    throw new Error('渲染结果没有携带组件来源映射')
  }
  const interactiveDoor = entity.meshes.find(mesh => mesh.elementId === 'front_door__opening')
  if (!interactiveDoor?.interactive || interactiveDoor.interaction?.mode !== 'swing') {
    throw new Error(`门窗交互描述未透传到 renderer: ${JSON.stringify(interactiveDoor?.interaction)}`)
  }
}

async function assertReconstructionDiagnostics(compiler) {
  const validEntity = await compiler.reconstructWildEntity(createBlueprint())
  const door = validEntity.reconstructionReport.observations.find(
    item => item.sourceId === 'front_door',
  )
  const window = validEntity.reconstructionReport.observations.find(
    item => item.sourceId === 'side_window',
  )
  if (!door?.actualBounds || door.expectedRelation !== 'attached_to_parent') {
    throw new Error(`门组件缺少宿主墙重建诊断: ${JSON.stringify(door)}`)
  }
  if (!window?.actualBounds || window.targetId !== 'side_wall') {
    throw new Error(`窗组件缺少宿主墙重建诊断: ${JSON.stringify(window)}`)
  }

  const broken = createBlueprint()
  broken.geometry.components = [{
    type: 'door', id: 'detached_door', parentWall: 'missing_wall',
    from: [1, 0, 0], width: 1, height: 2.2,
  }]
  const brokenEntity = await compiler.reconstructWildEntity(broken)
  const diagnostic = brokenEntity.diagnostics.find(
    item => item.code === 'RECONSTRUCTION_MISSING_MESH' && item.elementId === 'detached_door',
  )
  if (!diagnostic || brokenEntity.reconstructionReport.errorCount !== 1) {
    throw new Error(`缺失网格没有形成结构化重建诊断: ${JSON.stringify(brokenEntity.diagnostics)}`)
  }
  compiler.setActivePinia(compiler.createPinia())
  const sceneStore = compiler.useSceneStore()
  if (await sceneStore.loadBlueprint(broken, 'broken-reconstruction')) {
    throw new Error('含重建错误的蓝图被 sceneStore 当作加载成功')
  }
  if (!sceneStore.reconstructed?.diagnostics.some(item => item.code === 'RECONSTRUCTION_MISSING_MESH')) {
    throw new Error('重建失败后前端没有保留可展示的结构化诊断')
  }
  console.log('Phase 3A reconstruction evaluation passed: attached door/window and missing mesh detection.')
}

function assertInvalidComponentSchemaIsRejected(compiler) {
  const cases = [
    {
      expectedField: 'width',
      mutate: source => { source.geometry.components[0].width = -1 },
    },
    {
      expectedField: 'swing',
      mutate: source => { source.geometry.components[0].swing = 'left' },
    },
  ]

  for (const testCase of cases) {
    const source = createBlueprint()
    testCase.mutate(source)
    const originalConsoleError = console.error
    try {
      console.error = () => {}
      compiler.parseWildBlueprint(JSON.stringify(source))
    } catch (error) {
      if (String(error).includes(testCase.expectedField)) continue
      throw error
    } finally {
      console.error = originalConsoleError
    }
    throw new Error(`Schema 接受了非法 door.${testCase.expectedField}`)
  }
}

function assertScenePatchIntegration(compiler) {
  const source = createBlueprint()
  source.geometry.components = []
  const added = compiler.applyPatchToBlueprint(source, {
    operations: [{
      op: 'add_component',
      component: {
        type: 'railing',
        id: 'patch_railing',
        path: [[0, 0, 0], [2, 0, 0]],
        height: 1,
      },
    }],
  })
  const updated = compiler.applyPatchToBlueprint(added, {
    operations: [{
      op: 'update_component',
      id: 'patch_railing',
      changes: { height: 1.2 },
    }],
  })
  assertEqual(updated.geometry.components[0].height, 1.2, 'update_component 未生效')
  const cleared = compiler.applyPatchToBlueprint(updated, {
    operations: [{
      op: 'update_component',
      id: 'patch_railing',
      changes: { height: 1.2, parentFloor: undefined },
    }],
  })
  if ('parentFloor' in cleared.geometry.components[0]) {
    throw new Error('update_component 无法清除可选字段')
  }
  const removed = compiler.applyPatchToBlueprint(cleared, {
    operations: [{ op: 'remove_component', id: 'patch_railing' }],
  })
  assertEqual(removed.geometry.components, [], 'remove_component 未生效')
}

async function assertComponentEditingHistory(compiler) {
  compiler.setActivePinia(compiler.createPinia())
  const sceneStore = compiler.useSceneStore()
  const historyStore = compiler.useHistoryStore()
  sceneStore.loadBlueprint(createBlueprint(), 'editor-check')
  await waitForReconstruction(sceneStore)

  const applied = await sceneStore.applyPatch({
    type: 'scene_patch',
    patch_id: 'component-editor-check',
    base_revision: sceneStore.document.revision,
    source: 'user',
    mode: 'apply',
    requires_confirmation: false,
    summary: '修改门宽',
    operations: [{ op: 'update_component', id: 'front_door', changes: { width: 1.1 } }],
  })
  if (!applied || !historyStore.canUndo) throw new Error('组件修改未写入撤销历史')
  assertEqual(
    sceneStore.document.blueprint.geometry.components[0].width,
    1.1,
    '组件属性修改未应用',
  )

  const undoEntry = historyStore.undo()
  if (!undoEntry || !await sceneStore.restoreBlueprint(undoEntry.before)) {
    throw new Error('组件修改无法撤销')
  }
  assertEqual(
    sceneStore.document.blueprint.geometry.components[0].width,
    1,
    '撤销后组件属性不正确',
  )

  const redoEntry = historyStore.redo()
  if (!redoEntry || !await sceneStore.restoreBlueprint(redoEntry.after)) {
    throw new Error('组件修改无法重做')
  }
  assertEqual(
    sceneStore.document.blueprint.geometry.components[0].width,
    1.1,
    '重做后组件属性不正确',
  )
}

async function waitForReconstruction(sceneStore) {
  while (sceneStore.isReconstructing) {
    await new Promise(resolve => setTimeout(resolve, 0))
  }
}

async function assertReactiveBlueprintWorkerTransfer(compiler) {
  const originalWorker = globalThis.Worker
  class CloneCheckingWorker {
    listeners = new Map()

    addEventListener(type, listener) {
      this.listeners.set(type, listener)
    }

    postMessage(message) {
      // 浏览器在这里会对 Proxy 抛出 DataCloneError；使用真实 structuredClone
      // 可确保回归测试覆盖本次故障，而不是只验证函数返回值。
      const cloned = structuredClone(message)
      queueMicrotask(() => {
        this.listeners.get('message')?.({
          data: {
            requestId: cloned.requestId,
            entity: { meshes: [], diagnostics: [], workerTransferVerified: true },
          },
        })
      })
    }

    terminate() {}
  }

  try {
    globalThis.Worker = CloneCheckingWorker
    const reactiveBlueprint = compiler.reactive(createBlueprint())
    const entity = await compiler.reconstructScene(reactiveBlueprint)
    assertEqual(entity.workerTransferVerified, true, '响应式 Blueprint 无法安全传入 Worker')
  } finally {
    if (originalWorker === undefined) delete globalThis.Worker
    else globalThis.Worker = originalWorker
  }
}

function assertOpeningAnimationFrames(compiler) {
  const originalRequestAnimationFrame = globalThis.requestAnimationFrame
  const queue = []
  let renderRequests = 0
  let now = performance.now()
  globalThis.requestAnimationFrame = callback => {
    queue.push(callback)
    return queue.length
  }

  const drain = (maximumFrames = 100) => {
    let frames = 0
    while (queue.length > 0) {
      if (++frames > maximumFrames) throw new Error('门窗动画没有在预期帧数内结束')
      now += 16
      queue.shift()(now)
    }
  }

  try {
    const mesh = new compiler.Mesh(
      new compiler.BoxGeometry(1, 2, 0.04),
      new compiler.MeshBasicMaterial(),
    )
    mesh.userData.interaction = {
      kind: 'opening',
      mode: 'swing',
      pivot: [-0.5, 0, 0],
      closedPosition: [0, 0, 0],
      closedRotation: [0, 0, 0],
      openRotation: [0, Math.PI / 2, 0],
    }
    mesh.userData.interactionOpen = false

    if (!compiler.toggleOpeningInteraction(mesh, () => { renderRequests++ })) {
      throw new Error('合法门窗没有启动开合动画')
    }
    drain()
    if (!mesh.userData.interactionOpen || mesh.userData.interactionProgress !== 1) {
      throw new Error('开门动画没有到达打开状态')
    }
    if (renderRequests < 10) {
      throw new Error(`动画没有逐帧请求视口重绘: ${renderRequests}`)
    }

    compiler.toggleOpeningInteraction(mesh, () => { renderRequests++ })
    for (let index = 0; index < 5; index++) {
      now += 16
      queue.shift()?.(now)
    }
    compiler.toggleOpeningInteraction(mesh, () => { renderRequests++ })
    drain()
    if (!mesh.userData.interactionOpen || mesh.userData.interactionProgress !== 1) {
      throw new Error('动画中途反向切换后状态不正确')
    }
  } finally {
    if (originalRequestAnimationFrame === undefined) delete globalThis.requestAnimationFrame
    else globalThis.requestAnimationFrame = originalRequestAnimationFrame
  }
}

function createBlueprint() {
  return {
    meta: { version: '1.1', type: 'building', name: 'component-compiler-check' },
    geometry: {
      elements: [
        {
          type: 'wall',
          id: 'front_wall',
          from: [0, 0, 0],
          to: [8, 3, 0],
          thickness: 0.24,
          material: 'wall',
        },
        {
          type: 'wall',
          id: 'side_wall',
          from: [8, 0, 0],
          to: [8, 3, 6],
          thickness: 0.24,
          material: 'wall',
        },
      ],
      components: [
        {
          type: 'door',
          id: 'front_door',
          parentWall: 'front_wall',
          from: [1, 0, 0],
          width: 1,
          height: 2.2,
          frameMaterial: 'wood',
          leafMaterial: 'wood',
          interaction: { mode: 'swing', hingeSide: 'left', openAngle: 90 },
        },
        {
          type: 'window',
          id: 'side_window',
          parentWall: 'side_wall',
          from: [1.2, 0.9, 0],
          width: 1.8,
          height: 1.2,
          verticalMullions: 1,
          horizontalMullions: 1,
          frameMaterial: 'frame',
          glassMaterial: 'glass',
        },
        {
          type: 'railing',
          id: 'terrace_railing',
          path: [[0, 0, 3], [2.4, 0, 3]],
          height: 1.1,
          postSpacing: 0.8,
          railLevels: [0.5, 1],
          material: 'metal',
        },
      ],
    },
    materials: {},
    behaviors: {},
  }
}

function createEvaluationBlueprint(component) {
  const source = createBlueprint()
  source.geometry.components = [component]
  return source
}

function assertTypesByPrefix(elements, prefix, expected) {
  const actual = elements
    .filter(element => element.id.startsWith(prefix))
    .map(element => element.type)
  assertEqual(actual, expected, `${prefix} 的展开类型不正确`)
}

function assertEqual(actual, expected, message) {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`${message}: expected=${JSON.stringify(expected)}, actual=${JSON.stringify(actual)}`)
  }
}

function assertVec3ArrayClose(actual, expected, message) {
  const flatActual = actual?.flat() || []
  const flatExpected = expected.flat()
  if (
    flatActual.length !== flatExpected.length
    || flatActual.some((value, index) => Math.abs(value - flatExpected[index]) > 1e-9)
  ) {
    throw new Error(`${message}: expected=${JSON.stringify(expected)}, actual=${JSON.stringify(actual)}`)
  }
}
