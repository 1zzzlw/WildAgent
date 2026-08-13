import assert from 'node:assert/strict'
import { createServer } from 'vite'


const server = await createServer({
  appType: 'custom',
  logLevel: 'silent',
  server: { middlewareMode: true },
})

try {
  const { createMaterialFromParams, MaterialCache } = await server.ssrLoadModule(
    '/src/renderer/materialAdapter.ts',
  )
  const { normalizeProceduralBrick } = await server.ssrLoadModule(
    '/src/renderer/proceduralMaterials/index.ts',
  )
  const { meshDataToGeometry } = await server.ssrLoadModule(
    '/src/renderer/meshDataToGeometry.ts',
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
    vertexShader: '#include <common>\nvoid main() {\n#include <uv_vertex>\n}',
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

  geometry.dispose()
  standard.dispose()
  auditedSolid.dispose()
  tintedTexture.dispose()
  glass.dispose()
  brick.dispose()
  unsupportedProcedural.dispose()
  console.log('Rendering pipeline check passed: solids, physical glass, AO UVs and procedural brick shader.')
} finally {
  await server.close()
}
