// 用**真引擎**编译物品库里的每个 `.wild`，导出三角形供离线出图与体检。
//
// 为什么要真编译：物品是手写坐标，schema 合法不等于几何合理
// （悬空、穿插、尺寸离谱都不会让 schema 报错）。这里跑
// parseBlueprint -> compileBlueprintComponents -> reconstructEntity，
// 任何 error 级诊断都算失败。
//
// 用法：
//   node scripts/item-catalog-verify.mjs                # 全量
//   node scripts/item-catalog-verify.mjs sofa_three     # 指定物品
// 产物（系统临时目录 /wild-item-catalog）：
//   meshes.json   每个物品的世界坐标三角形 + 材质色
//   report.json   诊断、包围盒、三角数汇总
import { mkdir, mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { build } from 'vite';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const coreSrc = join(root, '..', 'wild-core', 'src').replaceAll('\\', '/');
const itemsDir = join(root, '..', 'wild-server', 'storage', 'item_catalog', 'items');
const outDir = join(tmpdir(), 'wild-item-catalog');

const virtualEntry = `
export { parseBlueprint } from 'wildsrc:parser';
export { reconstructEntity } from 'wildsrc:core';
export { compileBlueprintComponents } from 'wildsrc:compiler';
`;

function rotate(point, rotation) {
  const [x, y, z] = point;
  const [rx, ry, rz] = rotation || [0, 0, 0];
  const cx = Math.cos(rx), sx = Math.sin(rx);
  const cy = Math.cos(ry), sy = Math.sin(ry);
  const cz = Math.cos(rz), sz = Math.sin(rz);
  return [
    cy * cz * x - cy * sz * y + sy * z,
    (sx * sy * cz + cx * sz) * x + (-sx * sy * sz + cx * cz) * y - sx * cy * z,
    (-cx * sy * cz + sx * sz) * x + (cx * sy * sz + sx * cz) * y + cx * cy * z,
  ];
}

const probe = await mkdtemp(join(tmpdir(), 'wild-item-verify-'));
let failures = 0;
const report = [];
const meshesOut = {};

try {
  await build({
    root,
    logLevel: 'silent',
    plugins: [
      {
        name: 'item-verify',
        resolveId(id) {
          if (id === 'virtual:item-verify') return '\0virtual:item-verify';
          if (id === 'wildsrc:parser') return `${coreSrc}/primitive/parser.ts`;
          if (id === 'wildsrc:core') return `${coreSrc}/primitive/index.ts`;
          if (id === 'wildsrc:compiler') return `${coreSrc}/compiler/index.ts`;
        },
        load(id) {
          if (id === '\0virtual:item-verify') return virtualEntry;
        },
      },
    ],
    build: {
      outDir: probe,
      emptyOutDir: false,
      minify: false,
      rollupOptions: {
        input: 'virtual:item-verify',
        preserveEntrySignatures: 'exports-only',
        output: { format: 'es', entryFileNames: 'verify.mjs' },
      },
    },
  });

  const engine = await import(`${pathToFileURL(join(probe, 'verify.mjs')).href}?t=${Date.now()}`);

  const only = new Set(process.argv.slice(2));
  const files = (await readdir(itemsDir)).filter(file => file.endsWith('.wild'));
  const selected = only.size > 0 ? files.filter(file => only.has(file.replace(/\.wild$/, ''))) : files;
  if (only.size > 0 && selected.length !== only.size) {
    const found = new Set(selected.map(file => file.replace(/\.wild$/, '')));
    for (const missing of only) if (!found.has(missing)) console.error(`未知物品: ${missing}`);
  }

  for (const file of selected.sort()) {
    const id = file.replace(/\.wild$/, '');
    const text = await readFile(join(itemsDir, file), 'utf8');
    let blueprint;
    try {
      blueprint = engine.parseBlueprint(text);
    } catch (error) {
      failures += 1;
      report.push({ id, stage: 'parse', errors: [String(error?.message || error)] });
      console.error(`✗ ${id} 解析失败: ${error?.message || error}`);
      continue;
    }

    const compilation = engine.compileBlueprintComponents(blueprint);
    const compileErrors = compilation.diagnostics.filter(item => item.level === 'error');
    let entity;
    try {
      entity = await engine.reconstructEntity(compilation.blueprint);
    } catch (error) {
      failures += 1;
      report.push({ id, stage: 'reconstruct', errors: [String(error?.message || error)] });
      console.error(`✗ ${id} 重建抛错: ${error?.message || error}`);
      continue;
    }
    const errors = entity.diagnostics.filter(item => item.level === 'error');
    const warnings = entity.diagnostics.filter(item => item.level === 'warning');

    // 材质色以蓝图里的材质表为准：materialParams 与 meshes 同序但没有
    // materialRef 字段，靠下标对齐属于隐性约定，换实现就会错位。
    const declaredMaterials = blueprint.materials || {};
    const materialColor = name => {
      const declared = declaredMaterials[name];
      return declared?.baseColor || [0.72, 0.72, 0.72];
    };

    let triangles = 0;
    const meshes = [];
    for (const mesh of entity.meshes) {
      const transform = mesh.transform || {};
      const position = transform.position || [0, 0, 0];
      const rotation = transform.rotation || [0, 0, 0];
      const scale = transform.scale || [1, 1, 1];
      const geometry = Array.from(mesh.geometry || []);
      const indices = Array.from(mesh.indices || []);
      const world = new Array(geometry.length);
      for (let i = 0; i < geometry.length; i += 3) {
        const scaled = [geometry[i] * scale[0], geometry[i + 1] * scale[1], geometry[i + 2] * scale[2]];
        const rotated = rotate(scaled, rotation);
        world[i] = rotated[0] + position[0];
        world[i + 1] = rotated[1] + position[1];
        world[i + 2] = rotated[2] + position[2];
      }
      triangles += indices.length / 3;
      meshes.push({
        positions: world.map(value => Math.round(value * 10000) / 10000),
        indices,
        color: materialColor(mesh.materialRef),
      });
    }

    const bounds = entity.boundingBox;
    const size = [0, 1, 2].map(axis =>
      Math.round((bounds.max[axis] - bounds.min[axis]) * 1000) / 1000,
    );
    const ok = compileErrors.length + errors.length === 0;
    if (!ok) failures += 1;

    report.push({
      id,
      ok,
      triangles: Math.round(triangles),
      meshes: meshes.length,
      size,
      min: bounds.min.map(value => Math.round(value * 1000) / 1000),
      compileErrors: compileErrors.map(item => item.message),
      errors: errors.map(item => item.message),
      warnings: warnings.map(item => item.message),
    });
    meshesOut[id] = { size, min: bounds.min, max: bounds.max, meshes };
    console.log(
      `${ok ? '✓' : '✗'} ${id.padEnd(26)} 三角 ${String(Math.round(triangles)).padStart(5)} ` +
        `尺寸 ${size.join('×')} 网格 ${meshes.length}` +
        (warnings.length ? ` 警告 ${warnings.length}` : ''),
    );
  }

  await mkdir(outDir, { recursive: true });
  await writeFile(join(outDir, 'meshes.json'), JSON.stringify(meshesOut), 'utf8');
  await writeFile(join(outDir, 'report.json'), JSON.stringify(report, null, 1), 'utf8');
  console.log(`\n产物: ${outDir}`);
  console.log(`成功 ${report.filter(item => item.ok).length} / ${report.length}，失败 ${failures}`);
  if (failures > 0) process.exitCode = 1;
} finally {
  await rm(probe, { recursive: true, force: true });
}
