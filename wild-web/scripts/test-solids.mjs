import { createServer } from 'vite'
import { readFile, writeFile, mkdir } from 'node:fs/promises'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import * as THREE from 'three'
const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const server = await createServer({ root, logLevel: 'error' })
try {
  const api = await server.ssrLoadModule('../wild-core/src/primitive/index.ts')
  const materials = Object.fromEntries(
    ['base', 'cut'].map(k => [
      k,
      {
        baseColor: k === 'cut' ? [0.8, 0.25, 0.1] : [0.4, 0.6, 0.7],
        roughness: 0.8,
        metallic: 0,
        albedo: 1,
        lightingCondition: 'D65_noon'
      }
    ])
  )
  const rect = (x, z) => ({
      outer: [
        [-x, -z],
        [x, -z],
        [x, z],
        [-x, z]
      ]
    }),
    circle = (r, n = 32, offset = 0) =>
      Array.from({ length: n }, (_, i) => [
        offset + r * Math.cos((i * 2 * Math.PI) / n),
        r * Math.sin((i * 2 * Math.PI) / n)
      ])
  const solid = (kind, extra, id = 's') => ({ type: 'solid', id, kind, material: 'base', ...extra })
  const box = (id, x = 0) => ({
    type: 'primitive',
    id,
    shape: 'box',
    position: [x, 1, 0],
    dimensions: [2, 2, 2],
    material: 'base'
  })
  const bp = es => ({
    meta: { version: '1.1', type: 'building', name: 'solid-validation' },
    geometry: { elements: es },
    materials
  })
  function metrics(entity) {
    const tris = []
    const owners = []
    for (const m of entity.meshes) {
      const mat = new THREE.Matrix4().compose(
        new THREE.Vector3(...m.transform.position),
        new THREE.Quaternion().setFromEuler(new THREE.Euler(...m.transform.rotation, 'XYZ')),
        new THREE.Vector3(...m.transform.scale)
      )
      const ids = m.indices ?? Array.from({ length: m.geometry.length / 3 }, (_, i) => i)
      for (let i = 0; i < ids.length; i += 3) {
        tris.push(
          [0, 1, 2].map(j => new THREE.Vector3().fromArray(m.geometry, 3 * ids[i + j]).applyMatrix4(mat))
        )
        owners.push(m.elementId)
      }
    }
    let volume = 0
    const edges = new Map()
    for (const [ti, t] of tris.entries()) {
      volume += t[0].dot(t[1].clone().cross(t[2])) / 6
      for (let i = 0; i < 3; i++) {
        const k = p =>
            p
              .toArray()
              .map(v => Math.round(v / 1e-5))
              .join(','),
          a = k(t[i]),
          b = k(t[(i + 1) % 3]),
          key = owners[ti] + ':' + (a < b ? a + '/' + b : b + '/' + a)
        const [n, d] = edges.get(key) ?? [0, 0]
        edges.set(key, [n + 1, d + (a < b ? 1 : -1)])
      }
    }
    return {
      triangles: tris.length,
      volume,
      closed: [...edges.values()].every(([n, d]) => n === 2 && d === 0),
      ids: [...new Set(entity.meshes.map(m => m.elementId))],
      materials: [...new Set(entity.meshes.map(m => m.materialRef))]
    }
  }
  const results = []
  async function good(name, es, volume, tolerance = 1e-4, extra) {
    const source = JSON.stringify(bp(es))
    const parsed = api.parseBlueprint(source),
      entity = await api.reconstructEntity(parsed)
    const errors = entity.diagnostics.filter(d => d.level === 'error')
    if (errors.length) throw Error(name + ': ' + JSON.stringify(errors))
    const m = metrics(entity)
    if (m.triangles && !m.closed) throw Error(name + ' not closed')
    if (volume !== undefined && Math.abs(m.volume - volume) > tolerance)
      throw Error(name + ' volume ' + m.volume + ' expected ' + volume)
    if (JSON.stringify(bp(es)) !== source) throw Error('source mutated')
    if (extra) extra(m, entity)
    results.push({
      name,
      ok: true,
      ...m,
      warnings: entity.diagnostics.filter(d => d.level === 'warning').map(d => d.code)
    })
  }
  async function bad(name, es) {
    let rejected = false
    try {
      const p = api.parseBlueprint(JSON.stringify(bp(es)))
      const e = await api.reconstructEntity(p)
      rejected = e.diagnostics.some(d => d.level === 'error')
    } catch {
      rejected = true
    }
    if (!rejected) throw Error('invalid case accepted: ' + name)
    results.push({ name, rejected: true })
  }
  const n = 48
  await good(
    'exact_cone',
    [solid('cone', { radius: 1, height: 2, segments: n })],
    (n * Math.sin((2 * Math.PI) / n)) / 3
  )
  await good('pyramid', [solid('pyramid', { base: rect(1, 1).outer, height: 2 })], 8 / 3)
  await good(
    'offset_frustum',
    [solid('frustum', { bottom: rect(1, 1), top: rect(0.6, 0.6), height: 2, topOffset: [0.2, 0.3] })],
    (2 * (4 + 1.44 + 2.4)) / 3
  )
  await good('zero_edge_wedge', [solid('wedge', { width: 2, depth: 4, endHeights: [0, 1] })], 4)
  const hollow = { ...rect(1, 1), holes: [rect(0.7, 0.7).outer.reverse()] }
  await good('hollow_extrusion', [solid('extrude', { profile: hollow, vector: [0, 3, 0] })], 6.12)
  await good(
    'negative_slanted_extrusion',
    [solid('extrude', { profile: hollow, vector: [0.5, -3, 0.2] })],
    6.12
  )
  await good(
    'concave_extrusion',
    [
      solid('extrude', {
        profile: {
          outer: [
            [0, 0],
            [2, 0],
            [2, 1],
            [1, 1],
            [1, 2],
            [0, 2]
          ]
        },
        vector: [0, 2, 0]
      })
    ],
    6
  )
  const section = {
    outer: [
      [0.8, 0],
      [1, 0],
      [1, 2],
      [0.8, 2]
    ]
  }
  await good(
    'full_hollow_revolve',
    [solid('revolve', { section, angle: Math.PI * 2, segments: 64 })],
    64 * Math.sin((2 * Math.PI) / 64) * 0.36
  )
  await good(
    'half_revolve',
    [solid('revolve', { section, angle: Math.PI, segments: 64 })],
    64 * Math.sin(Math.PI / 64) * 0.36
  )
  await good(
    'torus',
    [solid('revolve', { section: { outer: circle(0.3, 32, 2) }, angle: 2 * Math.PI, segments: 64 })],
    0.5 * 32 * 0.09 * Math.sin((2 * Math.PI) / 32) * 2 * 64 * Math.sin((2 * Math.PI) / 64)
  )
  const sphereProfile = [
    [0, -1],
    ...Array.from({ length: 31 }, (_, i) => {
      const t = -Math.PI / 2 + ((i + 1) * Math.PI) / 32
      return [Math.cos(t), Math.sin(t)]
    }),
    [0, 1]
  ]
  await good(
    'axis_welded_sphere',
    [solid('revolve', { section: { outer: sphereProfile }, angle: Math.PI * 2, segments: 64 })],
    (4 * Math.PI) / 3,
    0.03
  )
  await good(
    'loft',
    [
      solid('loft', {
        sections: [
          { height: 0, profile: rect(1, 1) },
          { height: 3, profile: rect(0.5, 0.5), offset: [0.3, 0.2] }
        ],
        segmentsPerSpan: 5
      })
    ],
    7
  )
  await good(
    'straight_sweep',
    [
      solid('sweep', {
        path: [
          [0, 0, 0],
          [0, 3, 0]
        ],
        profile: rect(1, 1)
      })
    ],
    12
  )
  await good(
    'varying_sweep',
    [
      solid('sweep', {
        path: [
          [0, 0, 0],
          [0, 3, 0]
        ],
        sections: [
          { t: 0, profile: rect(1, 1) },
          { t: 1, profile: rect(0.5, 0.5) }
        ]
      })
    ],
    7
  )
  await good('bent_sweep', [
    solid('sweep', {
      path: [
        [0, 0, 0],
        [2, 0.5, 0],
        [4, 0.5, 1]
      ],
      profile: rect(0.1, 0.15)
    })
  ])
  const closedPath = Array.from({ length: 32 }, (_, i) => [
    2 * Math.cos((i * 2 * Math.PI) / 32),
    0,
    2 * Math.sin((i * 2 * Math.PI) / 32)
  ])
  await good(
    'closed_sweep',
    [solid('sweep', { path: closedPath, profile: rect(0.2, 0.1), closedPath: true })],
    2 * Math.PI * 2 * 0.08,
    0.02
  )
  const bool = (op, operands = ['a', 'b'], id = 'result') =>
    solid('boolean', { operation: op, operands, cutMaterial: op === 'difference' ? 'cut' : undefined }, id)
  for (const [op, vol] of [
    ['union', 12],
    ['difference', 4],
    ['intersection', 4]
  ])
    await good('boolean_' + op, [box('a'), box('b', 1), bool(op)], vol, 0.001, m => {
      if (m.ids.some(id => id !== 'result')) throw Error('consumed operands visible')
      if (op === 'difference' && !m.materials.includes('cut')) throw Error('cut material missing')
    })
  await good(
    'shared_keep_operands',
    [
      box('a'),
      box('b', 1),
      { ...bool('union', undefined, 'visible_union'), keepOperands: true },
      bool('intersection', undefined, 'visible_intersection')
    ],
    32,
    0.001,
    m => {
      if (!m.ids.includes('a') || !m.ids.includes('b')) throw Error('explicit keepOperands lost shared input')
    }
  )
  const nested = [
    box('a'),
    box('b', 1),
    bool('union', undefined, 'u'),
    { ...box('tool', 0.5), dimensions: [1, 3, 3] },
    bool('difference', ['u', 'tool'], 'nested')
  ]
  await good('nested_boolean', nested, 8, 0.001)
  await good('order_independent_boolean', [...nested].reverse(), 8, 0.001)
  await good(
    'transformed_boolean',
    [
      { ...box('a'), position: [10, 1, 10], scale: [2, 1, 1], rotation: [0, Math.PI / 4, 0] },
      {
        ...box('b'),
        position: [10 + Math.SQRT2, 1, 10 - Math.SQRT2],
        scale: [2, 1, 1],
        rotation: [0, Math.PI / 4, 0]
      },
      bool('union')
    ],
    24,
    0.003
  )
  await good('empty_intersection', [box('a'), box('b', 10), bool('intersection')], 0)
  await good('difference_no_overlap', [box('a'), box('b', 10), bool('difference')], 8)
  await good('coplanar_face_union', [box('a'), box('b', 2), bool('union')], 16, 0.001)
  const buildingFixtures = JSON.parse(
    await readFile(new URL('./test-fixtures/solid-building.json', import.meta.url), 'utf8')
  )
  for (const f of buildingFixtures) await good(f.name, f.elements)
  await bad('negative_radius', [solid('cone', { radius: -1, height: 2 })])
  await bad('bow_tie', [
    solid('extrude', {
      profile: {
        outer: [
          [0, 0],
          [1, 1],
          [0, 1],
          [1, 0]
        ]
      },
      vector: [0, 1, 0]
    })
  ])
  await bad('outside_hole', [
    solid('extrude', { profile: { ...rect(1, 1), holes: [rect(2, 2).outer] }, vector: [0, 1, 0] })
  ])
  await bad('concave_pyramid', [
    solid('pyramid', {
      base: [
        [0, 0],
        [2, 0],
        [2, 1],
        [1, 1],
        [1, 2],
        [0, 2]
      ],
      height: 2
    })
  ])
  await bad('coplanar_extrude', [solid('extrude', { profile: rect(1, 1), vector: [1, 0, 0] })])
  await bad('loft_topology', [
    solid('loft', {
      sections: [
        { height: 0, profile: rect(1, 1) },
        {
          height: 1,
          profile: {
            outer: [
              [0, 0],
              [1, 0],
              [0, 1]
            ]
          }
        }
      ]
    })
  ])
  await bad('loft_unordered', [
    solid('loft', {
      sections: [
        { height: 1, profile: rect(1, 1) },
        { height: 0, profile: rect(1, 1) }
      ]
    })
  ])
  await bad('sweep_reversal', [
    solid('sweep', {
      path: [
        [0, 0, 0],
        [1, 0, 0],
        [0, 0, 0]
      ],
      profile: rect(0.1, 0.1)
    })
  ])
  await bad('sweep_self_intersection', [
    solid('sweep', {
      path: [
        [-2, 0, -2],
        [2, 0, 2],
        [-2, 0, 2],
        [2, 0, -2]
      ],
      profile: rect(0.2, 0.2)
    })
  ])
  await bad('boolean_cycle', [bool('union', ['result', 'a']), box('a')])
  await bad('boolean_missing', [bool('union', ['missing', 'a']), box('a')])
  await bad('boolean_open_operand', [
    {
      type: 'primitive',
      id: 'a',
      shape: 'profile_sweep',
      path: [
        [0, 0, 0],
        [0, 2, 0]
      ],
      radius: 0.5,
      material: 'base'
    },
    box('b'),
    bool('union')
  ])
  await bad('boolean_transformed_result', [box('a'), box('b', 1), { ...bool('union'), position: [1, 0, 0] }])
  await bad('boolean_cut_on_union', [box('a'), box('b', 1), { ...bool('union'), cutMaterial: 'cut' }])
  const report = {
    ok: true,
    positiveCases: results.filter(r => r.ok).length,
    negativeCases: results.filter(r => r.rejected).length,
    results
  }
  const reportPath = process.argv[2] ?? join(root, '../output/solid-test-results.json')
  await mkdir(dirname(reportPath), { recursive: true })
  await writeFile(reportPath, JSON.stringify(report, null, 2))
  console.log(
    JSON.stringify({
      ok: report.ok,
      positiveCases: report.positiveCases,
      negativeCases: report.negativeCases
    })
  )
} finally {
  await server.close()
}
