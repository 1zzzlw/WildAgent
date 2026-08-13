import assert from 'node:assert/strict'
import { createServer } from 'vite'


const server = await createServer({
  appType: 'custom',
  logLevel: 'silent',
  server: { middlewareMode: true },
})

try {
  const { createMaterialFromParams } = await server.ssrLoadModule(
    '/src/renderer/materialAdapter.ts',
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
  console.log('Rendering pipeline check passed: compatible double-sided solids, explicit front-side solids, physical glass and AO UVs.')
} finally {
  await server.close()
}
