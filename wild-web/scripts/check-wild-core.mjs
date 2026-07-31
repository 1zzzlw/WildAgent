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
  await assertSideWallOpeningAlignment(core);

  console.table(results);
  console.log(`Core smoke check passed: ${sampleNames.length} samples, ${core.getEngineCapabilities().length} capabilities.`);
} finally {
  await rm(outputDirectory, { recursive: true, force: true });
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
  const openingAlongWall = 2.5;
  const localX = openingAlongWall - wallLength / 2;
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
}
