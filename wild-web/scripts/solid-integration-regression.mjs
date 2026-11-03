import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('..', import.meta.url))
const server = await createServer({ root, logLevel: 'error' })
try {
  const { reconstructWildEntity } = await server.ssrLoadModule('/src/renderer/wildCoreAdapter.ts')
  const { parseBlueprint } = await server.ssrLoadModule('../wild-core/src/primitive/index.ts')
  const { compileBlueprintComponents } = await server.ssrLoadModule('../wild-core/src/compiler/index.ts')
  const { createGeometryTranslationOperations, getGeometryTranslationIds, createGeometryRotationOperations } =
    await server.ssrLoadModule('/src/wild/componentDrag.ts')
  const { applyPatchToBlueprint, createGeometryRemovalOperations } =
    await server.ssrLoadModule('/src/wild/scenePatch.ts')
  const { validateBlueprint } = await server.ssrLoadModule('/src/wild/sceneValidator.ts')
  const materials = Object.fromEntries(
    ['body', 'cut'].map((key, index) => [
      key,
      {
        baseColor: [0.5, 0.6, 0.7],
        roughness: 0.7,
        metallic: 0,
        albedo: 1,
        lightingCondition: 'D65_noon',
        surfacePattern: index ? 'planks' : 'quartz'
      }
    ])
  )
  const blueprint = elements => ({
    meta: { version: '1.1', type: 'asset', name: '实体接入回归' },
    geometry: { elements },
    materials
  })
  const source = blueprint([
    {
      type: 'primitive',
      id: 'body',
      shape: 'box',
      position: [0, 1, 0],
      dimensions: [2, 2, 2],
      material: 'body'
    },
    {
      type: 'primitive',
      id: 'tool',
      shape: 'box',
      position: [1, 1, 0],
      dimensions: [2, 2, 2],
      material: 'body'
    },
    {
      type: 'solid',
      id: 'result',
      kind: 'boolean',
      operation: 'difference',
      operands: ['body', 'tool'],
      cutMaterial: 'cut'
    }
  ])
  const original = JSON.stringify(source)
  const entity = await reconstructWildEntity(source)
  assert.deepEqual(
    entity.diagnostics.filter(d => d.level === 'error'),
    []
  )
  assert.deepEqual(new Set(entity.hiddenElementIds), new Set(['body', 'tool']))
  assert.deepEqual(
    entity.reconstructionReport.observations.map(o => o.sourceId),
    ['result']
  )
  assert.equal(JSON.stringify(source), original)
  assert.ok(entity.meshes.some(m => m.materialRef === 'cut'))
  for (const mesh of entity.meshes) {
    assert.ok([...mesh.geometry, ...mesh.normals, ...mesh.uvs].every(Number.isFinite))
    for (let offset = 0; offset < mesh.indices.length; offset += 3) {
      const [a, b, c] = Array.from(mesh.indices.slice(offset, offset + 3))
      const determinant =
        (mesh.uvs[b * 2] - mesh.uvs[a * 2]) * (mesh.uvs[c * 2 + 1] - mesh.uvs[a * 2 + 1]) -
        (mesh.uvs[c * 2] - mesh.uvs[a * 2]) * (mesh.uvs[b * 2 + 1] - mesh.uvs[a * 2 + 1])
      assert.ok(Math.abs(determinant) > 1e-9, '继承材质和切面都必须具有非退化米制 UV')
    }
  }
  const apply = (bp, operations) => applyPatchToBlueprint(bp, { operations })
  for (const selection of [['result'], ['result', 'body', 'tool']]) {
    const operations = createGeometryTranslationOperations(source, selection, [3, 2, -1])
    assert.deepEqual(new Set(operations.map(op => op.id)), new Set(['body', 'tool']))
    const moved = apply(source, operations)
    assert.equal(moved.geometry.elements[2].position, undefined)
    const rebuilt = await reconstructWildEntity(moved)
    assert.deepEqual(
      rebuilt.diagnostics.filter(d => d.level === 'error'),
      []
    )
    for (const side of ['min', 'max'])
      for (let axis = 0; axis < 3; axis++) {
        assert.ok(
          Math.abs(rebuilt.boundingBox[side][axis] - entity.boundingBox[side][axis] - [3, 2, -1][axis]) < 1e-5
        )
      }
  }
  assert.deepEqual(new Set(getGeometryTranslationIds(source, ['body'])), new Set(['body', 'result']))
  assert.deepEqual(createGeometryRotationOperations(source, ['result']), [])
  assert.deepEqual(createGeometryRotationOperations(source, ['body']), [])
  const removed = apply(source, createGeometryRemovalOperations(source, ['body']))
  assert.deepEqual(
    removed.geometry.elements.map(e => e.id),
    ['tool']
  )
  const resultRemoved = apply(source, createGeometryRemovalOperations(source, ['result']))
  assert.deepEqual(
    resultRemoved.geometry.elements.map(e => e.id),
    ['body', 'tool']
  )
  const nested = structuredClone(source)
  nested.geometry.elements.push({
    type: 'solid',
    id: 'nested',
    kind: 'boolean',
    operation: 'union',
    operands: ['result', 'tool']
  })
  const nestedOperations = createGeometryTranslationOperations(nested, ['nested'], [1, 0, 0])
  assert.deepEqual(new Set(nestedOperations.map(op => op.id)), new Set(['body', 'tool']))

  const empty = structuredClone(source)
  empty.geometry.elements[1].position = [10, 1, 0]
  Object.assign(empty.geometry.elements[2], { operation: 'intersection' })
  delete empty.geometry.elements[2].cutMaterial
  const emptyEntity = await reconstructWildEntity(empty)
  assert.deepEqual(
    emptyEntity.diagnostics.filter(d => d.level === 'error'),
    []
  )
  assert.ok(emptyEntity.diagnostics.some(d => d.code === 'SOLID_BOOLEAN_EMPTY'))
  const failed = structuredClone(source)
  failed.geometry.elements[2].operands[1] = 'missing'
  const failedEntity = await reconstructWildEntity(failed)
  assert.ok(failedEntity.diagnostics.some(d => d.level === 'error'))
  assert.deepEqual(new Set(failedEntity.meshes.map(m => m.elementId)), new Set(['body', 'tool']))

  const leaf = {
    parts: [
      {
        shape: 'box',
        position: [0.3, 0.8, 0],
        dimensions: [0.6, 1.6, 0.04],
        rotation: [0.2, 0.3, 0.1],
        material: 'body'
      }
    ]
  }
  for (const type of ['door', 'window'])
    for (const mode of [false, 'swing', 'slide', 'lift']) {
      const opening = blueprint([
        { type: 'wall', id: 'wall', from: [0, 0, 0], to: [6, 3, 3], thickness: 0.2 }
      ])
      opening.geometry.components = [
        {
          type,
          id: 'opening',
          parentWall: 'wall',
          from: [1, 0.3, 0],
          width: 2,
          height: 2,
          interaction: mode ? { mode } : false,
          leaves: Array.from({ length: type === 'door' || !mode ? 1 : 2 }, () => structuredClone(leaf))
        }
      ]
      parseBlueprint(JSON.stringify(opening))
      const compiled = compileBlueprintComponents(opening)
      assert.deepEqual(compiled.diagnostics, [], `${type}/${mode}`)
      assert.ok(compiled.mapping.generatedElementIdsByComponentId.opening.some(id => id.includes('__part_')))
      const built = await reconstructWildEntity(opening)
      assert.deepEqual(
        built.diagnostics.filter(d => d.level === 'error'),
        [],
        `${type}/${mode}`
      )
      const parts = built.meshes.filter(mesh => mesh.elementId.includes('__part_'))
      assert.equal(parts.length, opening.geometry.components[0].leaves.length)
      assert.ok(parts.every(mesh => !!mesh.interaction === !!mode))
      const invalid = structuredClone(opening)
      invalid.geometry.components[0].leaves[0].parts[0]._interaction = { kind: 'opening' }
      assert.throws(() => parseBlueprint(JSON.stringify(invalid)))
      const wrongCount = structuredClone(opening)
      wrongCount.geometry.components[0].leaves.push(leaf)
      assert.ok(compileBlueprintComponents(wrongCount).diagnostics.some(d => d.level === 'error'))
      const missingMaterial = structuredClone(opening)
      missingMaterial.geometry.components[0].leaves[0].parts[0].material = 'missing'
      assert.ok(validateBlueprint(missingMaterial).some(issue => issue.message.includes('missing')))
      if (type === 'door') {
        const both = structuredClone(opening)
        both.geometry.components[0].leafParts = []
        assert.throws(() => parseBlueprint(JSON.stringify(both)))
        assert.ok(compileBlueprintComponents(both).diagnostics.some(d => d.level === 'error'))
      }
    }
  console.log(
    'SOLID_INTEGRATION_PASS: adapter diagnostics, cut UVs, move/delete dependencies, empty/failed booleans, 8 custom leaf modes and invalid inputs'
  )
} finally {
  await server.close()
}
