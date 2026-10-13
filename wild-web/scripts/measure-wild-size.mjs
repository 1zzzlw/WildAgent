import { mkdtemp, readFile, readdir, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { build } from 'vite';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const outDir = await mkdtemp(join(tmpdir(), 'wild-size-'));
const P = (rel) => join(root, '..', 'wild-core', rel).replaceAll('\\', '/');

try {
  await build({
    root, logLevel: 'silent',
    plugins: [{
      name: 'entry',
      resolveId: (id) => ({
        'virtual:entry': '\0virtual:entry',
        'src:parser': P('src/primitive/parser.ts'),
        'src:core': P('src/primitive/index.ts'),
        'src:compiler': P('src/compiler/index.ts'),
      }[id]),
      load: (id) => (id === '\0virtual:entry'
        ? `export { parseBlueprint } from 'src:parser';
           export { reconstructEntity } from 'src:core';
           export { compileBlueprintComponents } from 'src:compiler';`
        : undefined),
    }],
    build: {
      outDir, emptyOutDir: false, minify: false,
      rollupOptions: {
        input: 'virtual:entry',
        preserveEntrySignatures: 'exports-only',
        output: { format: 'es', entryFileNames: 'core.mjs' },
      },
      lib: { entry: 'virtual:entry', formats: ['es'], fileName: () => 'core.mjs' },
    },
  });

  const { parseBlueprint, reconstructEntity, compileBlueprintComponents } =
    await import(pathToFileURL(join(outDir, 'core.mjs')).href);

  const scenes = join(root, '..', 'wild-server', 'storage', 'scenes');
  const paths = [];
  for (const d of await readdir(scenes, { withFileTypes: true })) {
    if (!d.isDirectory()) continue;
    for (const f of await readdir(join(scenes, d.name))) {
      if (f.endsWith('.wild')) paths.push(join(scenes, d.name, f));
    }
  }

  const rows = [];
  const fail = { json: 0, compile: 0, parse: 0, reconstruct: 0, empty: 0, ok: 0 };
  const firstErr = {};

  for (const path of paths) {
    const raw = await readFile(path, 'utf8');
    let bp;
    try { bp = JSON.parse(raw); } catch (e) { fail.json++; firstErr.json ??= e.message; continue; }

    let compiled;
    try { compiled = compileBlueprintComponents(bp); }
    catch (e) { fail.compile++; firstErr.compile ??= e.message; continue; }

    const bp2 = compiled?.blueprint ?? bp;

    let parsed;
    try { parsed = parseBlueprint(JSON.stringify(bp2)); }
    catch (e) { fail.parse++; firstErr.parse ??= e.message; continue; }

    let rec;
    try { rec = await reconstructEntity(parsed); }
    catch (e) { fail.reconstruct++; firstErr.reconstruct ??= e.message; continue; }

    const meshes = rec?.meshes ?? [];
    if (!meshes.length) { fail.empty++; firstErr.empty ??= `meshes=0, diagnostics=${JSON.stringify((rec?.diagnostics ?? []).slice(0, 2))}`; continue; }

    let tris = 0, verts = 0;
    for (const m of meshes) {
      // wild-core 的 MeshData: geometry 为扁平 Float32Array（位置 xyz 交错）
      const pos = m?.geometry?.length ?? 0;
      const idx = m?.indices?.length ?? 0;
      verts += pos / 3;
      tris += idx ? idx / 3 : pos / 9;
    }
    if (!tris) { fail.empty++; firstErr.empty ??= `tris=0, geometry keys=${JSON.stringify(Object.keys(meshes[0] ?? {}))}`; continue; }
    fail.ok++;

    const geo = parsed?.geometry ?? {};
    rows.push({
      name: path.split(/[\\/]/).pop().replace(/^session_\d+_/, '').replace(/\.wild$/, ''),
      wild: Buffer.byteLength(raw),
      el: (geo.elements?.length ?? 0) + (geo.components?.length ?? 0),
      tris, verts, mesh: meshes.length,
      errors: (rec?.diagnostics ?? []).filter((d) => d?.level === 'error').length,
    });
  }

  console.log(`场景文件 ${paths.length} 个 -> 成功 ${fail.ok}，失败 ${fail.json + fail.compile + fail.parse + fail.reconstruct + fail.empty}`);
  console.log(`  json=${fail.json} compile=${fail.compile} parse=${fail.parse} reconstruct=${fail.reconstruct} empty=${fail.empty}`);
  for (const [k, v] of Object.entries(firstErr)) console.log(`   ${k}: ${v}`);
  console.log();

  rows.sort((a, b) => b.tris - a.tris);
  const n = (x) => Math.round(x).toLocaleString('en-US');

  console.log(`可重建场景 ${rows.length} 个\n`);
  console.log('场景'.padEnd(30) + 'wild'.padStart(10) + '实体'.padStart(7) +
    '三角面'.padStart(11) + '网格'.padStart(7) + '字节/面'.padStart(9));
  console.log('-'.repeat(76));
  for (const r of rows.slice(0, 10)) {
    console.log(r.name.slice(0, 28).padEnd(30) +
      `${n(r.wild)}B`.padStart(10) + n(r.el).padStart(7) +
      n(r.tris).padStart(11) + n(r.mesh).padStart(7) +
      (r.wild / r.tris).toFixed(2).padStart(9));
  }

  const T = rows.reduce((s, r) => s + r.tris, 0);
  const W = rows.reduce((s, r) => s + r.wild, 0);
  const V = rows.reduce((s, r) => s + r.verts, 0);
  const E = rows.reduce((s, r) => s + r.el, 0);
  console.log('-'.repeat(76));
  console.log('合计'.padEnd(30) + `${n(W)}B`.padStart(10) + n(E).padStart(7) + n(T).padStart(11) + ''.padStart(7));

  console.log(`\n全量 ${n(T)} 三角面 / ${n(V)} 顶点，对应 .wild 合计 ${n(W)} B`);
  console.log(`平均每三角面 ${(W / T).toFixed(2)} B，每顶点 ${(W / V).toFixed(2)} B\n`);

  console.log('同一批内容若网格化后的体积估算：');
  const VERT = 32;   // 位置 12 + 法线 12 + UV 8 (f32)
  const IDX = 4;     // 每索引 4 字节
  const meshBytes = V * VERT + T * 3 * IDX;
  const mb = (b) => (b / 1048576).toFixed(1);
  console.log(`  未压缩网格（位置+法线+UV ${VERT}B/顶点，索引 ${IDX}B）`);
  console.log(`      ${n(V)} 顶点 + ${n(T * 3)} 索引 = ${n(meshBytes)} B = ${mb(meshBytes)} MB`);
  console.log(`  顶点量化压缩 glTF（约 1/8）: ${n(meshBytes / 8)} B = ${mb(meshBytes / 8)} MB`);
  console.log(`  draco 几何压缩（约 1/20）  : ${n(meshBytes / 20)} B = ${mb(meshBytes / 20)} MB`);
  console.log(`\n  .wild 合计                : ${n(W)} B = ${mb(W)} MB`);
  console.log(`  → 相对未压缩网格          : ${(meshBytes / W).toFixed(0)} 倍`);
  console.log(`  → 相对 draco 压缩网格      : ${(meshBytes / 20 / W).toFixed(0)} 倍`);
  console.log(`\n  注：wild-core 不做顶点焊接，上述网格值为上界；`);
  console.log(`      生产级网格若焊接顶点，顶点数通常可降到 1/3~1/6。`);

  const s = rows[0];
  console.log(`\n【单例】${s.name}`);
  console.log(`  .wild          ${n(s.wild)} B (${(s.wild/1024).toFixed(1)} KB)`);
  console.log(`  实体数         ${n(s.el)}`);
  console.log(`  重建后三角面   ${n(s.tris)}`);
  console.log(`  网格化后约     ${n(s.tris*3*32/3)} B (${(s.tris*32/1048576).toFixed(2)} MB 量级)`);
  console.log(`  倍数           约 ${(s.tris*32/s.wild).toFixed(0)} 倍`);
} finally {
  await rm(outDir, { recursive: true, force: true });
}