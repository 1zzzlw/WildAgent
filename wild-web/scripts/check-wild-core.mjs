import { mkdtemp, readdir, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { build } from 'vite';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const outputDirectory = await mkdtemp(join(tmpdir(), 'wild-core-smoke-'));
const parserPath = join(root, 'src/wild-core/src/primitive/parser.ts').replaceAll('\\', '/');
const corePath = join(root, 'src/wild-core/src/primitive/index.ts').replaceAll('\\', '/');
const virtualEntry = `
export { parseBlueprint } from 'wildsrc:parser';
export { reconstructEntity, getEngineCapabilities } from 'wildsrc:core';
`;

try {
  await build({
    root,
    logLevel: 'silent',
    plugins: [{
      name: 'wild-core-smoke-entry',
      resolveId(id) {
        if (id === 'virtual:wild-core-smoke') return '\0virtual:wild-core-smoke';
        if (id === 'wildsrc:parser') return parserPath;
        if (id === 'wildsrc:core') return corePath;
      },
      load(id) {
        if (id === '\0virtual:wild-core-smoke') return virtualEntry;
      },
    }],
    build: {
      outDir: outputDirectory,
      emptyOutDir: false,
      minify: false,
      rollupOptions: {
        input: 'virtual:wild-core-smoke',
        preserveEntrySignatures: 'exports-only',
        output: {
          format: 'es',
          entryFileNames: 'wild-core-smoke.mjs',
        },
      },
    },
  });

  const core = await import(`${pathToFileURL(join(outputDirectory, 'wild-core-smoke.mjs')).href}?t=${Date.now()}`);
  await assertPrimitiveBoxDimensionCompatibility(core);
  await assertProfileSweepValidation(core);
  await assertSlopedBeamDirection(core);
  await assertSteppedFlatRoofBoundary(core);
  await assertChineseCurvedGableFill(core);
  const sampleDirectory = join(root, 'lantu');
  const sampleNames = (await readdir(sampleDirectory))
    .filter(name => name.endsWith('.wild'))
    .sort();
  const results = [];

  for (const sampleName of sampleNames) {
    const startedAt = performance.now();
    const blueprint = core.parseBlueprint(await readFile(join(sampleDirectory, sampleName), 'utf8'));
    const entity = await core.reconstructEntity(blueprint);
    const errors = entity.diagnostics.filter(diagnostic => diagnostic.level === 'error');
    const validMeshes = entity.meshes.every(validateMesh);
    const finiteBounds = [
      ...entity.boundingBox.min,
      ...entity.boundingBox.max,
    ].every(Number.isFinite);

    if (errors.length > 0 || !validMeshes || !finiteBounds) {
      throw new Error(`${sampleName} 回归失败: ${JSON.stringify({
        errors,
        validMeshes,
        finiteBounds,
      })}`);
    }

    results.push({
      sample: sampleName,
      meshes: entity.meshes.length,
      vertices: entity.meshes.reduce((sum, mesh) => sum + mesh.geometry.length / 3, 0),
      diagnostics: entity.diagnostics.length,
      milliseconds: Math.round((performance.now() - startedAt) * 10) / 10,
    });
  }

  assertInvalidBlueprintIsRejected(core.parseBlueprint);
  assertVersionMigration(core.parseBlueprint);
  await assertSideWallOpeningAlignment(core);
  await assertRightAngleWallJointCoverage(core);
  await assertArchitecturalWallAttributes(core);
  await assertInvalidRuntimeMaterialFallsBack(core);

  console.table(results);
  console.log(`Core smoke check passed: ${sampleNames.length} samples, ${core.getEngineCapabilities().length} capabilities.`);
} finally {
  await rm(outputDirectory, { recursive: true, force: true });
}

async function assertChineseCurvedGableFill(core) {
  const entity = await core.reconstructEntity({
    meta: { version: '1.1', type: 'building', name: 'curved-roof-gable-fill' },
    geometry: { elements: [
      { type: 'wall', id: 'front_wall', from: [0, 0, 0], to: [8, 3.2, 0], thickness: 0.24, material: 'wall' },
      { type: 'wall', id: 'right_wall', from: [8, 0, 0], to: [8, 3.2, 6], thickness: 0.24, material: 'wall' },
      { type: 'wall', id: 'back_wall', from: [8, 0, 6], to: [0, 3.2, 6], thickness: 0.24, material: 'wall' },
      { type: 'wall', id: 'left_wall', from: [0, 0, 6], to: [0, 3.2, 0], thickness: 0.24, material: 'wall' },
      { type: 'roof', id: 'roof_main', roofType: 'chinese_curved', span: 8, depth: 6, height: 2.5, thickness: 0.3, position: [4, 3.2, 3], material: 'roof' },
    ] },
    materials: {}, behaviors: {},
  });
  const gables = entity.meshes.filter(mesh => mesh.elementId === 'roof_main' && mesh.materialRef === 'wall');
  if (gables.length !== 2) throw new Error(`曲面屋顶没有生成两端山墙填充: ${gables.length}`);
  for (const mesh of gables) {
    const bounds = meshWorldBounds(mesh);
    if (Math.abs(bounds.min[1] - 3.2) > 1e-5 || bounds.max[1] < 5.2) {
      throw new Error(`山墙填充没有从墙顶连续到屋脊: ${JSON.stringify(bounds)}`);
    }
  }
}

async function assertSteppedFlatRoofBoundary(core) {
  const walls = [
    { type: 'wall', id: 'base_front', from: [0, 0, 0], to: [18, 3.2, 0], thickness: 0.24 },
    { type: 'wall', id: 'base_right', from: [18, 0, 0], to: [18, 3.2, 12], thickness: 0.24 },
    { type: 'wall', id: 'base_back', from: [18, 0, 12], to: [0, 3.2, 12], thickness: 0.24 },
    { type: 'wall', id: 'base_left', from: [0, 0, 12], to: [0, 3.2, 0], thickness: 0.24 },
    { type: 'wall', id: 'upper_front', from: [3, 3.2, 0.8], to: [15, 6.4, 0.8], thickness: 0.24 },
    { type: 'wall', id: 'upper_right', from: [15, 3.2, 0.8], to: [15, 6.4, 10.8], thickness: 0.24 },
    { type: 'wall', id: 'upper_back', from: [15, 3.2, 10.8], to: [3, 6.4, 10.8], thickness: 0.24 },
    { type: 'wall', id: 'upper_left', from: [3, 3.2, 10.8], to: [3, 6.4, 0.8], thickness: 0.24 },
  ];
  const reconstruct = roof => core.reconstructEntity({
    meta: { version: '1.1', type: 'building', name: 'stepped-flat-roof-check' },
    geometry: { elements: [...walls, roof] },
    materials: {}, behaviors: {},
  });

  const explicit = await reconstruct({
    type: 'roof', id: 'roof_explicit', roofType: 'flat',
    span: 13.2, depth: 11.2, height: 0.3, thickness: 0.3,
    position: [9, 6.4, 5.8],
  });
  assertRoofMesh(explicit, 'roof_explicit', {
    localMin: [-6.6, 0, -5.6], localMax: [6.6, 0.3, 5.6],
    position: [9, 6.4, 5.8],
  });

  const inferred = await reconstruct({
    type: 'roof', id: 'roof_inferred', roofType: 'flat',
    span: 1, depth: 1, height: 0.3, thickness: 0.3,
  });
  assertRoofMesh(inferred, 'roof_inferred', {
    localMin: [-6.5, 0, -5.5], localMax: [6.5, 0.3, 5.5],
    position: [9, 6.4, 5.8],
  });
}

function assertRoofMesh(entity, elementId, expected) {
  const mesh = entity.meshes.find(item => item.elementId === elementId);
  if (!mesh) throw new Error(`${elementId} 没有生成屋顶 mesh`);
  const bounds = localBounds(mesh.geometry);
  for (const [label, actual, wanted] of [
    ['localMin', bounds.min, expected.localMin],
    ['localMax', bounds.max, expected.localMax],
    ['position', mesh.transform.position, expected.position],
  ]) {
    const error = Math.max(...actual.map((value, index) => Math.abs(value - wanted[index])));
    if (error > 1e-5) {
      throw new Error(`${elementId} ${label} 错误: ${JSON.stringify({ actual, wanted })}`);
    }
  }
}

function localBounds(geometry) {
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  for (let index = 0; index < geometry.length; index += 3) {
    for (let axis = 0; axis < 3; axis++) {
      min[axis] = Math.min(min[axis], geometry[index + axis]);
      max[axis] = Math.max(max[axis], geometry[index + axis]);
    }
  }
  return { min, max };
}

async function assertProfileSweepValidation(core) {
  const valid = await core.reconstructEntity({
    meta: { version: '1.1', type: 'asset', name: 'profile-sweep-check' },
    geometry: { elements: [{
      type: 'primitive', id: 'cornice_sweep', shape: 'profile_sweep',
      path: [[0, 0, 0], [2, 0, 0], [2, 0, 1]],
      profile: [[-0.1, -0.1], [0.1, -0.1], [0.1, 0.1], [-0.1, 0.1]],
    }] },
    materials: {}, behaviors: {},
  });
  if (valid.diagnostics.some(item => item.level === 'error') || valid.meshes.length !== 1) {
    throw new Error(`profile_sweep 合法用例失败: ${JSON.stringify(valid.diagnostics)}`);
  }
  const invalid = await core.reconstructEntity({
    meta: { version: '1.1', type: 'asset', name: 'profile-sweep-invalid' },
    geometry: { elements: [{
      type: 'primitive', id: 'broken_sweep', shape: 'profile_sweep',
      path: [[0, 0, 0], [0, 0, 0]],
      profile: [[0, 0], [1, 0], [0, 1]],
    }] },
    materials: {}, behaviors: {},
  });
  if (!invalid.diagnostics.some(item => item.elementId === 'broken_sweep' && item.level === 'error')) {
    throw new Error('profile_sweep 重复路径点未产生可读错误');
  }
}

async function assertSlopedBeamDirection(core) {
  const from = [0, 0, 0];
  const to = [5.4, 0.45, 0];
  const entity = await core.reconstructEntity({
    meta: { version: '1.1', type: 'asset', name: 'sloped-beam-direction' },
    geometry: { elements: [{
      type: 'beam', id: 'sloped_handrail', from, to,
      crossSection: 'circular', width: 0.08, height: 0.08,
    }] },
    materials: {}, behaviors: {},
  });
  const mesh = entity.meshes.find(item => item.elementId === 'sloped_handrail');
  if (!mesh) throw new Error('斜梁没有生成 mesh');

  const [rx, ry] = mesh.transform.rotation;
  const actualAxis = [
    Math.sin(ry),
    -Math.sin(rx) * Math.cos(ry),
    Math.cos(rx) * Math.cos(ry),
  ];
  const length = Math.hypot(to[0] - from[0], to[1] - from[1], to[2] - from[2]);
  const expectedAxis = [
    (to[0] - from[0]) / length,
    (to[1] - from[1]) / length,
    (to[2] - from[2]) / length,
  ];
  const error = Math.hypot(...actualAxis.map((value, index) => value - expectedAxis[index]));
  if (error > 1e-9) {
    throw new Error(`斜梁轴线没有对齐 from→to: ${JSON.stringify({ actualAxis, expectedAxis })}`);
  }
}

function assertVersionMigration(parseBlueprint) {
  const migrated = parseBlueprint(JSON.stringify({
    meta: { version: '1.0', type: 'building', name: 'migration-check' },
    geometry: { elements: [] },
    materials: {},
  }));
  if (migrated.meta.version !== '1.1') {
    throw new Error(`WILD 1.0 未显式迁移到 1.1: ${migrated.meta.version}`);
  }
}

async function assertPrimitiveBoxDimensionCompatibility(core) {
  const source = {
    meta: { version: '1.1', type: 'asset', name: 'primitive-box-dimensions' },
    geometry: {
      elements: [{
        type: 'primitive',
        id: 'sofa_base',
        shape: 'box',
        position: [0, 0.15, 0],
        dimensions: { width: 2.2, height: 0.3, depth: 0.9 },
      }],
      components: [],
    },
    materials: {},
    behaviors: {},
  };

  const blueprint = core.parseBlueprint(JSON.stringify(source));
  const dimensions = blueprint.geometry.elements[0].dimensions;
  if (JSON.stringify(dimensions) !== JSON.stringify([2.2, 0.3, 0.9])) {
    throw new Error(`primitive box dimensions were not normalized: ${JSON.stringify(dimensions)}`);
  }

  const entity = await core.reconstructEntity(source);
  const errors = entity.diagnostics.filter(diagnostic => diagnostic.level === 'error');
  if (errors.length > 0 || entity.meshes.length !== 1) {
    throw new Error(`normalized primitive box did not reconstruct: ${JSON.stringify(errors)}`);
  }

  const invalidEntity = await core.reconstructEntity({
    ...source,
    geometry: {
      elements: [{
        ...source.geometry.elements[0],
        id: 'broken_box',
        dimensions: { width: 2.2, height: 0.3 },
      }],
      components: [],
    },
  });
  const invalidDiagnostic = invalidEntity.diagnostics.find(
    diagnostic => diagnostic.elementId === 'broken_box' && diagnostic.level === 'error',
  );
  if (!invalidDiagnostic?.message.includes('[width, height, depth]')) {
    throw new Error(
      `invalid primitive box did not report a readable dimensions error: ${JSON.stringify(invalidDiagnostic)}`,
    );
  }
}

async function assertInvalidRuntimeMaterialFallsBack(core) {
  const entity = await core.reconstructEntity({
    meta: { version: '1.1', type: 'building', name: 'invalid-material-runtime' },
    geometry: {
      elements: [{
        type: 'floor',
        id: 'test-floor',
        from: [0, 0, 0],
        to: [2, 0, 2],
        thickness: 0.2,
        material: 'broken',
      }],
    },
    materials: {
      broken: {
        roughness: 0.9,
        metallic: 0,
        albedo: 1,
        lightingCondition: 'D65_noon',
      },
    },
    behaviors: {},
  });

  const baseColor = entity.materialParams[0]?.baseColor;
  if (JSON.stringify(baseColor) !== JSON.stringify([0.5, 0.5, 0.5])) {
    throw new Error(`Invalid runtime material did not use fallback: ${JSON.stringify(baseColor)}`);
  }
}

function validateMesh(mesh) {
  const vertexCount = mesh.geometry.length / 3;
  const finiteGeometry = Array.from(mesh.geometry).every(Number.isFinite);
  const validIndices = !mesh.indices
    || Array.from(mesh.indices).every(index => index >= 0 && index < vertexCount);
  const validNormals = !mesh.normals || mesh.normals.length === mesh.geometry.length;
  const validUvs = !mesh.uvs || mesh.uvs.length === vertexCount * 2;
  const finiteTransform = [
    ...mesh.transform.position,
    ...mesh.transform.rotation,
    ...mesh.transform.scale,
  ].every(Number.isFinite);
  return finiteGeometry && validIndices && validNormals && validUvs && finiteTransform;
}

async function assertRightAngleWallJointCoverage(core) {
  const source = {
    meta: { version: '1.1', type: 'building', name: 'right-angle-wall-joint' },
    geometry: {
      elements: [
        {
          type: 'wall', id: 'front_wall', from: [0, 0, 0], to: [8, 3, 0],
          thickness: 0.24, material: 'wall',
        },
        {
          type: 'wall', id: 'side_wall', from: [8, 0, 0], to: [8, 3, 6],
          thickness: 0.3, material: 'wall',
        },
        {
          type: 'wall', id: 'upper_side_wall', from: [8, 3, 0], to: [8, 6, 6],
          thickness: 0.8, material: 'wall',
        },
        {
          type: 'opening', id: 'front_door', parentWall: 'front_wall',
          from: [2, 0, 0], width: 1, height: 2.1, depth: 0.04,
          style: 'rectangular', material: 'door',
        },
      ],
    },
    materials: {},
    behaviors: {},
  };
  const sourceBefore = JSON.stringify(source);
  const entity = await core.reconstructEntity(source);
  if (JSON.stringify(source) !== sourceBefore) {
    throw new Error('直角墙角解析修改了源蓝图中心线');
  }

  const front = entity.meshes.find(mesh => mesh.elementId === 'front_wall');
  const side = entity.meshes.find(mesh => mesh.elementId === 'side_wall');
  const door = entity.meshes.find(mesh => mesh.elementId === 'front_door');
  if (!front || !side || !door) throw new Error('直角墙角回归场景缺少预期网格');

  assertNear(front.transform.position[0], 4.075, '前墙端点没有按相邻墙半厚延伸');
  assertNear(side.transform.position[2], 2.94, '侧墙起点没有按相邻墙半厚延伸');
  assertNear(door.transform.position[0], 2.5, '墙角延伸错误移动了门的位置');
  assertNear(door.transform.position[2], 0, '墙角延伸错误改变了门的法向位置');

  const frontBounds = meshWorldBounds(front);
  const sideBounds = meshWorldBounds(side);
  assertNear(frontBounds.max[0], 8.15, '前墙渲染端没有覆盖侧墙全厚');
  assertNear(sideBounds.min[2], -0.12, '侧墙渲染端没有覆盖前墙全厚');

  const oblique = await core.reconstructEntity({
    meta: { version: '1.1', type: 'building', name: 'oblique-wall-joint' },
    geometry: { elements: [
      { type: 'wall', id: 'wall_a', from: [0, 0, 0], to: [4, 3, 0], thickness: 0.24 },
      { type: 'wall', id: 'wall_b', from: [4, 0, 0], to: [6, 3, 3.464], thickness: 0.24 },
    ] },
    materials: {}, behaviors: {},
  });
  const obliqueWall = oblique.meshes.find(mesh => mesh.elementId === 'wall_a');
  if (!obliqueWall) throw new Error('斜角墙回归场景缺少 wall_a');
  assertNear(obliqueWall.transform.position[0], 2, '非直角墙被错误执行渲染延伸');
}

function assertNear(actual, expected, message, tolerance = 1e-5) {
  if (Math.abs(actual - expected) > tolerance) {
    throw new Error(`${message}: actual=${actual}, expected=${expected}`);
  }
}

function meshWorldBounds(mesh) {
  const [px, py, pz] = mesh.transform.position;
  const [rx, ry, rz] = mesh.transform.rotation;
  if (Math.abs(rx) > 1e-9 || Math.abs(rz) > 1e-9) {
    throw new Error('墙角回归仅支持绕 Y 轴旋转的测试网格');
  }
  const cosine = Math.cos(ry);
  const sine = Math.sin(ry);
  const bounds = { min: [Infinity, Infinity, Infinity], max: [-Infinity, -Infinity, -Infinity] };
  for (let index = 0; index < mesh.geometry.length; index += 3) {
    const x = mesh.geometry[index];
    const y = mesh.geometry[index + 1];
    const z = mesh.geometry[index + 2];
    const world = [cosine * x + sine * z + px, y + py, -sine * x + cosine * z + pz];
    for (let axis = 0; axis < 3; axis++) {
      bounds.min[axis] = Math.min(bounds.min[axis], world[axis]);
      bounds.max[axis] = Math.max(bounds.max[axis], world[axis]);
    }
  }
  return bounds;
}

function assertInvalidBlueprintIsRejected(parseBlueprint) {
  const invalidBlueprint = {
    meta: { version: '1.1', type: 'asset', name: 'invalid-radius-test' },
    geometry: {
      elements: [{
        type: 'primitive',
        id: 'broken-sphere',
        shape: 'sphere',
        radius: -1,
      }],
    },
  };

  try {
    parseBlueprint(JSON.stringify(invalidBlueprint));
  } catch (error) {
    if (String(error).includes('radius')) return;
    throw error;
  }
  throw new Error('Schema validator accepted an invalid primitive radius');
}

async function assertSideWallOpeningAlignment(core) {
  const blueprint = core.parseBlueprint(JSON.stringify({
    meta: { version: '1.1', type: 'building', name: 'side-wall-opening-regression' },
    geometry: {
      elements: [
        {
          type: 'wall',
          id: 'side_wall',
          from: [0, 0, 0],
          to: [0, 3, 6],
          thickness: 0.3,
          material: 'wall',
        },
        {
          type: 'opening',
          id: 'side_window',
          parentWall: 'side_wall',
          from: [2.5, 0.9, 0],
          width: 1.2,
          height: 1.2,
          style: 'rectangular',
          material: 'glass',
        },
        {
          type: 'wall',
          id: 'curved_wall',
          from: [5, 0, 0],
          to: [5, 3, 0],
          thickness: 0.3,
          curve: { type: 'arc', center: [0, 0, 0], sweep: 360, segments: 32 },
          material: 'wall',
        },
        {
          type: 'opening',
          id: 'curved_window',
          parentWall: 'curved_wall',
          from: [0, 0.9, 0],
          width: 2,
          height: 1.2,
          style: 'rectangular',
          material: 'glass',
        },
      ],
    },
    materials: {
      wall: {
        baseColor: [0.75, 0.75, 0.75],
        roughness: 0.9,
        metallic: 0,
        albedo: 1,
        lightingCondition: 'D65_noon',
      },
      glass: {
        baseColor: [0.55, 0.75, 0.85],
        roughness: 0.1,
        metallic: 0,
        albedo: 1,
        opacity: 0.35,
        lightingCondition: 'D65_noon',
      },
    },
    behaviors: {},
  }));

  const sourceBeforeRebuild = JSON.stringify(blueprint);
  const entity = await core.reconstructEntity(blueprint);
  if (JSON.stringify(blueprint) !== sourceBeforeRebuild) {
    throw new Error('Core reconstruction mutated the source blueprint');
  }
  const wallMesh = entity.meshes.find(mesh => mesh.elementId === 'side_wall');
  const openingMesh = entity.meshes.find(mesh => mesh.elementId === 'side_window');
  if (!wallMesh || !openingMesh) {
    throw new Error('Side-wall opening regression scene did not produce both meshes');
  }

  const wallLength = 6;
  const openingStartAlongWall = 2.5;
  const openingWidth = 1.2;
  const openingCenterAlongWall = openingStartAlongWall + openingWidth / 2;
  const localX = openingCenterAlongWall - wallLength / 2;
  const angle = wallMesh.transform.rotation[1];
  const cutoutCenter = [
    wallMesh.transform.position[0] + Math.cos(angle) * localX,
    wallMesh.transform.position[2] - Math.sin(angle) * localX,
  ];
  const paneCenter = [
    openingMesh.transform.position[0],
    openingMesh.transform.position[2],
  ];
  const error = Math.hypot(
    cutoutCenter[0] - paneCenter[0],
    cutoutCenter[1] - paneCenter[1],
  );

  if (error > 1e-6) {
    throw new Error(
      `Side-wall opening misaligned by ${error.toFixed(3)}m: `
      + `cutout=${JSON.stringify(cutoutCenter)}, pane=${JSON.stringify(paneCenter)}`,
    );
  }

  if (Math.abs(paneCenter[1] - openingCenterAlongWall) > 1e-6) {
    throw new Error(
      `Side-wall opening center should be ${openingCenterAlongWall}m along the wall, `
      + `received ${paneCenter[1]}m`,
    );
  }

  const radius = 5;
  const curvedOpeningWidth = 2;
  const curvedOpeningMesh = entity.meshes.find(mesh => mesh.elementId === 'curved_window');
  if (!curvedOpeningMesh) {
    throw new Error('Curved-wall opening regression scene did not produce an opening mesh');
  }

  const centerAlong = curvedOpeningWidth / 2;
  const curvedAngle = centerAlong / radius;
  const expected = [radius * Math.cos(curvedAngle), radius * Math.sin(curvedAngle)];
  const actual = [
    curvedOpeningMesh.transform.position[0],
    curvedOpeningMesh.transform.position[2],
  ];
  const curvedError = Math.hypot(actual[0] - expected[0], actual[1] - expected[1]);
  if (curvedError > 1e-6) {
    throw new Error(
      `Curved-wall opening misaligned by ${curvedError.toFixed(3)}m: `
      + `expected=${JSON.stringify(expected)}, actual=${JSON.stringify(actual)}`,
    );
  }
}

async function assertArchitecturalWallAttributes(core) {
  const entity = await core.reconstructEntity({
    meta: { version: '1.1', type: 'building', name: 'wall-surface-attributes' },
    geometry: {
      elements: [
        { type: 'wall', id: 'wall', from: [0, 0, 0], to: [8, 3, 0], thickness: 0.3, material: 'wall' },
        { type: 'opening', id: 'opening', parentWall: 'wall', from: [3, 0.9, 0], width: 1.5, height: 1.2 },
      ],
      components: [],
    },
    materials: { wall: { baseColor: [0.8, 0.8, 0.8], roughness: 0.8, metallic: 0, albedo: 1 } },
    behaviors: {},
  });
  const wall = entity.meshes.find(mesh => mesh.elementId === 'wall');
  if (!wall?.uvs || wall.uvs.length !== wall.geometry.length / 3 * 2) {
    throw new Error('墙体没有生成完整逐面 UV');
  }
  if (!wall.normals || wall.normals.length !== wall.geometry.length) {
    throw new Error('墙体没有生成硬边法线');
  }
  const uSpan = Math.max(...wall.uvs) - Math.min(...wall.uvs);
  if (uSpan < 2) throw new Error(`墙体 UV 未按米展开: span=${uSpan}`);
}
