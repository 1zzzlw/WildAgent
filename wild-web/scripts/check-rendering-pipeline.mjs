import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { BlobWriter, TextReader, Uint8ArrayReader, ZipWriter } from '@zip.js/zip.js'
import * as THREE from 'three'
import { createServer } from 'vite'


const server = await createServer({
  appType: 'custom',
  logLevel: 'silent',
  server: { middlewareMode: true },
})

try {
  const { createMaterialFromParams, MaterialCache, getGlobalMaterialResourceStats } = await server.ssrLoadModule(
    '/src/renderer/materialAdapter.ts',
  )
  const { parseWorldPackageManifest, WorldPackageValidationError } = await server.ssrLoadModule(
    '/src/wild-core/src/materials/index.ts',
  )
  const { worldLookRuntime, registerWorldLookProfile, registerShaderFeature } = await server.ssrLoadModule(
    '/src/renderer/worldLookRuntime.ts',
  )
  const {
    assertWorldPackageKind,
    decodeWorldPackage,
    decodeWorldPackageBundle,
    getWorldPackageDecoderIds,
    getWorldPackageKind,
  } = await server.ssrLoadModule(
    '/src/renderer/worldPackageImport.ts',
  )
  const {
    getWorldRenderingUniforms,
    getWorldEnvironmentState,
    updateWorldRenderingState,
    updateWorldEnvironmentState,
  } = await server.ssrLoadModule('/src/renderer/worldEnvironmentRuntime.ts')
  const {
    deriveWorldAtmosphere,
    matchWorldWeatherPreset,
    WORLD_WEATHER_PRESETS,
    WorldWeatherVisuals,
  } = await server.ssrLoadModule('/src/renderer/worldWeatherRuntime.ts')
  const { WorldRuntime } = await server.ssrLoadModule('/src/renderer/worldRuntime.ts')
  const { createEditorWorldDocument, parseWorldDocument, serializeWorldDocument } = await server.ssrLoadModule(
    '/src/renderer/worldDocumentPersistence.ts',
  )
  const {
    registerWorldAssetResolver,
    resolveWorldAsset,
  } = await server.ssrLoadModule('/src/renderer/worldAssetResolver.ts')
  const { normalizeProceduralBrick } = await server.ssrLoadModule(
    '/src/renderer/proceduralMaterials/index.ts',
  )
  const { meshDataToGeometry } = await server.ssrLoadModule(
    '/src/renderer/meshDataToGeometry.ts',
  )
  const { clearSceneObjectResources, updateSceneGroup } = await server.ssrLoadModule(
    '/src/renderer/renderEntity.ts',
  )
  const { selectionAfterClick } = await server.ssrLoadModule(
    '/src/wild/componentSelection.ts',
  )
  const { buildReconstructionDiagnostics } = await server.ssrLoadModule(
    '/src/renderer/reconstructionDiagnostics.ts',
  )

  assert.deepEqual(selectionAfterClick(['wall_1'], 'wall_2', 'toggle'), ['wall_1', 'wall_2'])
  assert.deepEqual(selectionAfterClick(['wall_1', 'wall_2'], 'wall_1', 'toggle'), ['wall_2'])
  assert.deepEqual(selectionAfterClick(['wall_1', 'wall_2'], 'wall_3', 'replace'), ['wall_3'])

  const missingComponent = buildReconstructionDiagnostics({
    geometry: {
      elements: [{ id: 'wall_1', type: 'wall' }],
      components: [{ id: 'door_1', type: 'door', parentWall: 'wall_1' }],
    },
  }, [{
    elementId: 'wall_1',
    geometry: [0, 0, 0, 1, 0, 0, 0, 1, 0],
  }], {
    generatedElementIdsByComponentId: { door_1: [] },
  }).diagnostics.find(item => item.code === 'RECONSTRUCTION_MISSING_MESH')
  assert.equal(missingComponent.category, 'compiler_geometry')
  assert.equal(missingComponent.repairLayer, 'compiler')

  const standard = createMaterialFromParams({
    baseColor: [0.7, 0.7, 0.7],
    roughness: 0.72,
    metallic: 0,
    albedo: 1,
  })
  assert.equal(standard.isMeshStandardMaterial, true)
  assert.equal(standard.isMeshPhysicalMaterial, undefined)
  assert.equal(standard.side, 2, '历史构件兼容模式必须默认 DoubleSide')

  const auditedSolid = createMaterialFromParams({
    baseColor: [0.7, 0.7, 0.7],
    roughness: 0.72,
    metallic: 0,
    albedo: 1,
    side: 'front',
  })
  assert.equal(auditedSolid.side, 0, '显式验证过的封闭实体应支持 FrontSide')

  const tintedTexture = createMaterialFromParams({
    baseColor: [0.8, 0.6, 0.4],
    roughness: 0.7,
    metallic: 0,
    albedo: 1,
    textures: {
      baseColor: {
        encoding: 'url',
        uri: '/texture.png',
        mimeType: 'image/png',
        sha256: 'test',
        colorSpace: 'srgb',
      },
    },
  }, false, () => null)
  assert.ok(tintedTexture.color.r < 1, '颜色贴图应与材质染色相乘，而不是强制白色')
  assert.ok(tintedTexture.color.g < tintedTexture.color.r)
  assert.ok(tintedTexture.color.b < tintedTexture.color.g)

  const glass = createMaterialFromParams({
    baseColor: [0.72, 0.88, 0.96],
    roughness: 0.08,
    metallic: 0,
    albedo: 1,
    materialClass: 'glass',
    transmission: 0.92,
    ior: 1.5,
    thickness: 0.012,
  })
  assert.equal(glass.isMeshPhysicalMaterial, true)
  assert.equal(glass.transmission, 0.92)
  assert.equal(glass.opacity, 1)
  assert.equal(glass.transparent, false)
  assert.equal(glass.side, 2, '薄玻璃必须双面渲染')

  const brickParams = {
    baseColor: [0.52, 0.11, 0.055],
    roughness: 0.84,
    metallic: 0,
    albedo: 1,
    procedural: {
      type: 'brick',
      seed: 42,
      brickSize: [0.24, 0.065],
      mortarWidth: 0.01,
      mortarDepth: 0.006,
      bond: 'running',
      colorVariation: 0.14,
      roughnessVariation: 0.16,
      edgeWear: 0.06,
      weathering: {
        amount: 0.28,
        scale: 1.8,
        efflorescence: 0.22,
        verticalStreaks: 0.14,
        baseDampness: 0.1,
      },
    },
  }
  const brick = createMaterialFromParams(brickParams)
  assert.equal(brick.userData.wildProcedural?.type, 'brick')
  assert.equal(brick.customProgramCacheKey(), 'wild-procedural:brick-v1')
  const shader = {
    uniforms: {},
    vertexShader: '#include <common>\nvoid main() {\n#include <uv_vertex>\n#include <defaultnormal_vertex>\n#include <worldpos_vertex>\n}',
    fragmentShader: [
      '#include <common>',
      'void main() {',
      '#include <map_fragment>',
      '#include <roughnessmap_fragment>',
      '#include <normal_fragment_maps>',
      '}',
    ].join('\n'),
  }
  brick.onBeforeCompile(shader)
  assert.ok(shader.vertexShader.includes('vWildSurfaceUv = uv'))
  assert.ok(shader.fragmentShader.includes('wildMortarMask'))
  assert.ok(shader.fragmentShader.includes('wildEfflorescenceMask'))
  assert.ok(shader.fragmentShader.includes('wildSurfaceHeight'))
  assert.ok(shader.fragmentShader.includes('wildGlobalWetness'))
  assert.ok(shader.fragmentShader.includes('wildBrickBaseNormal = normal'))
  assert.ok(!shader.fragmentShader.includes('geometryNormal'))
  assert.deepEqual(shader.uniforms.wildBrickSize.value.toArray(), [0.24, 0.065])
  assert.equal(
    normalizeProceduralBrick({ type: 'brick', brickSize: [2, 1], mortarWidth: 1 }, [0.5, 0.1, 0.05]).mortarWidth,
    0.03,
    'renderer 防御性归一化仍必须遵守协议的砖缝宽度上限',
  )

  const unsupportedProcedural = createMaterialFromParams({
    baseColor: [0.5, 0.5, 0.5], roughness: 0.8, metallic: 0, albedo: 1,
    procedural: { type: 'future-material' },
  })
  assert.equal(unsupportedProcedural.userData.wildProcedural, undefined)

  const defaultSurfaceParams = {
    baseColor: [0.62, 0.6, 0.56],
    roughness: 0.82,
    metallic: 0,
    albedo: 1,
    renderDescriptor: {
      family: 'mineral',
      source: 'constant',
      implementation: 'surface.default.v1',
      implementationVersion: 1,
      quality: 'low',
      requiredFeatures: ['surface.micro-variation.v1'],
      environmentResponse: {
        wetness: { absorption: 0.48, colorDarkening: 0.16, roughnessReduction: 0.24 },
      },
    },
  }
  const defaultSurface = createMaterialFromParams(
    defaultSurfaceParams,
    false,
    undefined,
    'wall_plaster',
  )
  assert.equal(defaultSurface.userData.wildDefaultSurface?.family, 'mineral')
  assert.equal(defaultSurface.customProgramCacheKey(), 'wild-surface:default-surface-v1')
  const defaultSurfaceShader = {
    uniforms: {},
    vertexShader: '#include <common>\nvoid main() {\n#include <uv_vertex>\n#include <defaultnormal_vertex>\n#include <worldpos_vertex>\n}',
    fragmentShader: [
      '#include <common>',
      'void main() {',
      '#include <map_fragment>',
      '#include <color_fragment>',
      '#include <roughnessmap_fragment>',
      '#include <normal_fragment_maps>',
      '}',
    ].join('\n'),
  }
  defaultSurface.onBeforeCompile(defaultSurfaceShader)
  assert.ok(defaultSurfaceShader.fragmentShader.includes('wildDefaultPattern'))
  assert.ok(defaultSurfaceShader.fragmentShader.includes('wildMaterialWetness'))
  assert.ok(defaultSurfaceShader.fragmentShader.includes('wildSnowMask'))
  assert.ok(defaultSurfaceShader.fragmentShader.includes('wildDefaultBaseNormal = normal'))
  assert.ok(!defaultSurfaceShader.fragmentShader.includes('geometryNormal'))
  assert.equal(defaultSurfaceShader.uniforms.wildWorldWetness.value, 0)

  updateWorldRenderingState({ surfaceEnabled: false, surfaceQuality: 'high' })
  assert.equal(getWorldRenderingUniforms().surfaceEnabled.value, 0)
  assert.equal(getWorldRenderingUniforms().surfaceQuality.value, 1)
  updateWorldRenderingState({ surfaceEnabled: true, surfaceQuality: 'medium' })

  const pbrWeather = createMaterialFromParams({
    baseColor: [1, 1, 1], roughness: 0.7, metallic: 0, albedo: 1,
    textures: { baseColor: { encoding: 'url', uri: '/pbr.png', mimeType: 'image/png', sha256: 'pbr', colorSpace: 'srgb' } },
    renderDescriptor: {
      family: 'mineral', source: 'texture-set', implementation: 'surface.pbr.v1', implementationVersion: 1,
      quality: 'medium', requiredFeatures: ['surface.wetness.v1'],
      environmentResponse: { wetness: { absorption: 0.5, colorDarkening: 0.2, roughnessReduction: 0.3 } },
    },
  }, false, () => null, 'pbr_weather')
  const pbrShader = {
    uniforms: {},
    vertexShader: '#include <common>\nvoid main() {\n#include <defaultnormal_vertex>\n#include <worldpos_vertex>\n}',
    fragmentShader: [
      '#include <common>', 'void main() {', '#include <map_fragment>', '#include <color_fragment>',
      '#include <roughnessmap_fragment>', '#include <normal_fragment_maps>', '}',
    ].join('\n'),
  }
  pbrWeather.onBeforeCompile(pbrShader)
  assert.ok(pbrShader.fragmentShader.includes('wildPbrWetness'))
  assert.ok(pbrShader.fragmentShader.includes('wildPbrSnowMask'))
  assert.ok(pbrShader.fragmentShader.includes('wildPbrBaseNormal = normal'))
  assert.ok(!pbrShader.fragmentShader.includes('geometryNormal'))

  const realPbrShader = {
    uniforms: {},
    vertexShader: THREE.ShaderLib.standard.vertexShader,
    fragmentShader: THREE.ShaderLib.standard.fragmentShader,
  }
  pbrWeather.onBeforeCompile(realPbrShader)
  assert.ok(
    realPbrShader.fragmentShader.indexOf('wildPbrBaseNormal = normal')
      < realPbrShader.fragmentShader.indexOf('#include <normal_fragment_maps>'),
    '必须在 Three.js 法线贴图计算前保存基础法线，不能依赖版本私有变量',
  )
  assert.ok(!realPbrShader.fragmentShader.includes('geometryNormal'))

  updateWorldEnvironmentState(WORLD_WEATHER_PRESETS.rain.environment)
  assert.equal(matchWorldWeatherPreset(getWorldEnvironmentState()), 'rain')
  const rainyAtmosphere = deriveWorldAtmosphere(getWorldEnvironmentState(), true)
  assert.ok(rainyAtmosphere.fog >= 0.38)
  assert.ok(rainyAtmosphere.directLightScale < 0.5)
  assert.equal(deriveWorldAtmosphere(getWorldEnvironmentState(), false).rain, 0)
  const weatherScene = new THREE.Scene()
  const weatherVisuals = new WorldWeatherVisuals(weatherScene)
  weatherVisuals.setBounds(new THREE.Vector3(0, 4, 0), 12, 0)
  weatherVisuals.setEnvironment(getWorldEnvironmentState(), true)
  assert.equal(weatherVisuals.tick(1 / 60), true)
  assert.ok(weatherScene.getObjectByName('WorldWeatherVisuals'))
  weatherVisuals.dispose()
  assert.equal(weatherScene.getObjectByName('WorldWeatherVisuals'), undefined)
  updateWorldEnvironmentState(WORLD_WEATHER_PRESETS.clear.environment)

  const materialCache = new MaterialCache()
  const cachedBrick = materialCache.getOrCreate('brick', brickParams, false)
  const changedBrick = materialCache.getOrCreate('brick', {
    ...brickParams,
    procedural: { ...brickParams.procedural, brickSize: [0.3, 0.08] },
  }, false)
  assert.notEqual(cachedBrick, changedBrick, '程序化参数变化必须更新材质缓存实例')
  assert.equal(
    cachedBrick.customProgramCacheKey(),
    changedBrick.customProgramCacheKey(),
    '数值参数变化不应生成不同的 GPU Program',
  )
  materialCache.clear()

  const sharedScopeA = new MaterialCache('test-blueprint-a')
  const sharedScopeB = new MaterialCache('test-blueprint-b')
  const sharedA = sharedScopeA.getOrCreate('wall', defaultSurfaceParams, false)
  const sharedB = sharedScopeB.getOrCreate('facade', defaultSurfaceParams, false)
  assert.equal(sharedA, sharedB, '不同蓝图的相同材质参数必须共享同一 GPU 材质')
  assert.deepEqual(getGlobalMaterialResourceStats(), {
    materials: 1,
    textures: 0,
    materialReferences: 2,
    textureReferences: 0,
  })
  let sharedDisposeCount = 0
  sharedA.addEventListener('dispose', () => { sharedDisposeCount++ })
  sharedScopeA.clear()
  assert.equal(sharedDisposeCount, 0, '释放一个蓝图不能销毁其他蓝图仍在使用的材质')
  assert.equal(getGlobalMaterialResourceStats().materialReferences, 1)
  sharedScopeB.clear()
  assert.equal(sharedDisposeCount, 1)
  assert.equal(getGlobalMaterialResourceStats().materials, 0)

  const validLookJson = JSON.stringify({
    format: 'wild.render-profile',
    version: '1.0',
    profileId: 'look:test-v1',
    name: '测试光影',
    features: { lighting: 'test.look.feature.v1' },
    appearance: { exposureScale: 0.9, shadowOpacity: 0.8 },
  })
  assert.equal(parseWorldPackageManifest(validLookJson).profileId, 'look:test-v1')
  const validLookManifest = parseWorldPackageManifest(validLookJson)
  assert.equal(getWorldPackageKind(validLookManifest), 'look')
  assert.throws(
    () => assertWorldPackageKind(validLookManifest, 'material'),
    /素材面板只允许导入/,
  )
  assert.ok(getWorldPackageDecoderIds().includes('builtin:json-manifest-v1'))
  assert.equal((await decodeWorldPackage({
    name: 'test.wildlook',
    size: validLookJson.length,
    text: async () => validLookJson,
  })).profileId, 'look:test-v1')

  const pngBytes = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])
  const pngHash = createHash('sha256').update(pngBytes).digest('hex')
  const materialManifest = JSON.stringify({
    format: 'wild.material-package', version: '1.0', packageId: 'material:test', materialId: 'test_surface',
    name: '测试材质包', contentHash: `sha256:${pngHash}`, license: 'CC0', family: 'mineral',
    channels: { baseColor: {
      uri: 'package:/textures/base.png', mimeType: 'image/png', sha256: pngHash, colorSpace: 'srgb', byteSize: pngBytes.length,
      variants: { low: { uri: 'package:/textures/base-low.png', mimeType: 'image/png', sha256: pngHash, colorSpace: 'srgb', byteSize: pngBytes.length } },
    } },
  })
  const zipWriter = new ZipWriter(new BlobWriter('application/zip'), { useWebWorkers: false })
  await zipWriter.add('manifest.json', new TextReader(materialManifest))
  await zipWriter.add('textures/base.png', new Uint8ArrayReader(pngBytes))
  await zipWriter.add('textures/base-low.png', new Uint8ArrayReader(pngBytes))
  const zipBlob = await zipWriter.close()
  const decodedZip = await decodeWorldPackageBundle({
    name: 'test.wildmat', size: zipBlob.size, text: () => zipBlob.text(), arrayBuffer: () => zipBlob.arrayBuffer(),
  })
  assert.equal(decodedZip.source, 'zip')
  assert.equal(getWorldPackageKind(decodedZip.manifest), 'material')
  assert.doesNotThrow(() => assertWorldPackageKind(decodedZip.manifest, 'material'))
  assert.throws(
    () => assertWorldPackageKind(decodedZip.manifest, 'look'),
    /光影设置只允许导入/,
  )
  assert.ok(decodedZip.resources['package:/textures/base.png'].startsWith('blob:'))
  assert.ok(decodedZip.resources['package:/textures/base-low.png'].startsWith('blob:'))
  decodedZip.dispose()
  assert.throws(
    () => parseWorldPackageManifest(JSON.stringify({
      format: 'wild.render-profile',
      version: '1.0',
      profileId: 'look:unsafe',
      name: '不安全光影',
      features: { lighting: 'test.look.feature.v1' },
      fragmentShader: 'void main() {}',
    })),
    error => error instanceof WorldPackageValidationError && error.issues.some(issue => issue.includes('可执行代码')),
  )

  let lookActivationCount = 0
  let lookDisposeCount = 0
  const unregisterFeature = registerShaderFeature({
    id: 'test.look.feature.v1',
    activate() {
      lookActivationCount++
      return { dispose() { lookDisposeCount++ } }
    },
  })
  const unregisterProfile = registerWorldLookProfile(parseWorldPackageManifest(validLookJson))
  await worldLookRuntime.activateProfile('look:test-v1', { renderer: {}, scene: {} })
  assert.equal(lookActivationCount, 1)
  assert.equal(worldLookRuntime.getActiveProfile().profileId, 'look:test-v1')
  await worldLookRuntime.restoreDefault({ renderer: {}, scene: {} })
  assert.equal(lookDisposeCount, 1, '切回默认光影后必须释放外部光影运行时资源')
  assert.equal(worldLookRuntime.getActiveProfile().profileId, 'builtin:default')
  unregisterProfile()
  unregisterFeature()

  const assetBytes = new Uint8Array([1, 2, 3, 4])
  const assetHash = createHash('sha256').update(assetBytes).digest('hex')
  const unregisterResolver = registerWorldAssetResolver({
    id: 'test:memory-resolver', priority: 1000,
    canResolve: uri => uri === 'memory:test',
    async resolve() { return { bytes: assetBytes, mimeType: 'application/octet-stream', sourceId: 'test:memory-resolver', fromCache: false } },
  })
  assert.deepEqual((await resolveWorldAsset({ uri: 'memory:test', sha256: assetHash, mimeType: 'application/octet-stream' })).bytes, assetBytes)
  unregisterResolver()

  const worldRuntime = new WorldRuntime('test-world')
  const editorWorld = createEditorWorldDocument({
    id: 'scene-weather-boundary',
    name: '环境边界测试',
    revision: 1,
    blueprint: {
      meta: { version: '1.1', type: 'building', name: '不携带世界天气的建筑' },
      geometry: { elements: [], components: [] },
      environment: { rain: 1, fog: 1 },
    },
  })
  assert.equal(editorWorld.environment, undefined, 'Blueprint 中的历史环境字段不能覆盖世界天气')
  const worldDocument = parseWorldDocument({
    format: 'wild.world', version: '1.0', worldId: 'test-world', name: '测试世界', revision: 1,
    blueprints: { tower: { blueprintId: 'tower', contentHash: `sha256:${pngHash}` } },
    chunks: [{ chunkId: 'chunk-a' }, { chunkId: 'chunk-b' }],
    instances: [
      { instanceId: 'a', blueprintId: 'tower', chunkId: 'chunk-a', transform: { position: [0, 0, 0] } },
      { instanceId: 'b', blueprintId: 'tower', chunkId: 'chunk-b', transform: { position: [20, 0, 0] } },
    ],
  })
  assert.ok(serializeWorldDocument(worldDocument).includes('wild.world'))
  worldRuntime.mountDocument(worldDocument)
  worldDocument.instances.forEach(instance => worldRuntime.ensureInstance(instance))
  assert.deepEqual(worldRuntime.getStats(), { instances: 2, loadedChunks: 2, visibleInstances: 2 })
  assert.equal(worldRuntime.unloadChunk('chunk-a'), 1)
  assert.deepEqual(worldRuntime.getStats(), { instances: 1, loadedChunks: 1, visibleInstances: 1 })
  worldRuntime.dispose()

  const geometry = meshDataToGeometry({
    geometry: new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]),
    indices: new Uint32Array([0, 1, 2]),
    uvs: new Float32Array([0, 0, 1, 0, 0, 1]),
    materialRef: 'test',
    transform: {
      position: [0, 0, 0],
      rotation: [0, 0, 0],
      scale: [1, 1, 1],
    },
  })
  assert.ok(geometry.getAttribute('uv1'), 'AO 需要 uv1')
  assert.ok(geometry.getAttribute('uv2'), '兼容旧版 Three.js 的 AO UV')
  assert.equal(geometry.getAttribute('uv'), geometry.getAttribute('uv1'), '复用主 UV，不能复制整份数组')
  assert.equal(geometry.getAttribute('uv'), geometry.getAttribute('uv2'), '兼容 UV 也必须共享 BufferAttribute')

  const renderGroup = new THREE.Group()
  const renderCache = new MaterialCache('render-resource-test')
  updateSceneGroup(renderGroup, {
    meshes: [{
      elementId: 'fallback_mesh',
      geometry: new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]),
      indices: new Uint32Array([0, 1, 2]),
      materialRef: 'missing_material',
      transform: { position: [0, 0, 0], rotation: [0, 0, 0], scale: [1, 1, 1] },
    }],
    materialParams: [],
  }, renderCache)
  const fallbackMesh = renderGroup.children[0]
  assert.equal(fallbackMesh.userData.ownsMaterial, true, '默认兜底材质必须由网格负责释放')
  let fallbackDisposeCount = 0
  fallbackMesh.material.addEventListener('dispose', () => { fallbackDisposeCount++ })
  clearSceneObjectResources(renderGroup)
  assert.equal(fallbackDisposeCount, 1, '清空场景时必须释放自有材质')
  assert.equal(renderGroup.children.length, 0)
  renderCache.clear()

  geometry.dispose()
  standard.dispose()
  auditedSolid.dispose()
  tintedTexture.dispose()
  glass.dispose()
  brick.dispose()
  unsupportedProcedural.dispose()
  defaultSurface.dispose()
  pbrWeather.dispose()
  console.log('Rendering pipeline check passed: default/PBR weather, ZIP64 packages, shared resources, world instances, resolvers and look lifecycle.')
} finally {
  await server.close()
}
