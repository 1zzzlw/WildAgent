import { mkdtemp, readFile, rm, readdir, stat } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { build } from 'vite';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const corePath = join(root, 'src/wild-core/src/primitive/index.ts').replaceAll('\\', '/');
const compilerPath = join(root, 'src/wild-compiler/index.ts').replaceAll('\\', '/');
const parserPath = join(root, 'src/wild-core/src/primitive/parser.ts').replaceAll('\\', '/');
const virtualEntry = `
export { parseBlueprint } from 'wildsrc:parser';
export { reconstructEntity } from 'wildsrc:core';
export { compileBlueprintComponents } from 'wildsrc:compiler';
`;
const TOL = 0.06;

async function walk(dir, out) {
  let entries;
  try { entries = await readdir(dir, { withFileTypes: true }); }
  catch { return; }
  for (const e of entries) {
    const p = join(dir, e.name);
    if (e.isDirectory()) await walk(p, out);
    else if (e.name.toLowerCase().endsWith('.wild')) out.push(p);
  }
}
async function collectPaths(args) {
  const out = [];
  for (const a of args) {
    const s = await stat(a).catch(() => null);
    if (s && s.isDirectory()) await walk(a, out);
    else out.push(resolve(a));
  }
  return out;
}
function r2(v) { return Math.round(v * 100) / 100; }

function getCompYRange(c) {
  const y0 = c.from ? c.from[1] : 0;
  let y1 = y0;
  // 注意: balcony/canopy 的 depth 是向外悬挑(水平), 不是竖向高度, 不能当作竖向范围
  if (c.height != null) y1 = y0 + c.height;
  else if (c.slabThickness != null) y1 = y0 + c.slabThickness;
  else if (c.thickness != null) y1 = y0 + c.thickness;
  return [y0, y1];
}

function analyzeGeometry(bp) {
  const f = { openCorners: [], overlappingWalls: [], verticalGaps: [], from2Offsets: [] };
  const els = bp.geometry?.elements || [];
  const walls = els.filter(e => e.type === 'wall');
  const floors = els.filter(e => e.type === 'floor');
  const eps = [];
  for (const w of walls) {
    eps.push({ id: w.id, p: [r2(w.from[0]), r2(w.from[2])] });
    eps.push({ id: w.id, p: [r2(w.to[0]), r2(w.to[2])] });
  }
  for (let i = 0; i < eps.length; i++) {
    let matched = false;
    for (let j = 0; j < eps.length; j++) {
      if (i === j) continue;
      if (Math.hypot(eps[i].p[0] - eps[j].p[0], eps[i].p[1] - eps[j].p[1]) < TOL) { matched = true; break; }
    }
    if (!matched) f.openCorners.push(`${eps[i].id}@(${eps[i].p[0]},${eps[i].p[1]})`);
  }
  const segs = walls.map(w => ({
    id: w.id, x1: w.from[0], z1: w.from[2], x2: w.to[0], z2: w.to[2],
    y1: Math.min(w.from[1], w.to[1]), y2: Math.max(w.from[1], w.to[1]),
  })).filter(s => Math.hypot(s.x2 - s.x1, s.z2 - s.z1) > 1e-6);
  for (let i = 0; i < segs.length; i++)
    for (let j = i + 1; j < segs.length; j++) {
      const a = segs[i], b = segs[j];
      if (Math.min(a.y2, b.y2) - Math.max(a.y1, b.y1) <= TOL) continue;
      const ov = segOverlap2D(a, b);
      if (ov > 0.5) f.overlappingWalls.push(`${a.id}<>${b.id}(${r2(ov)}m)`);
    }
  // vertical continuity: each floor slab should connect to walls above/below within TOL
  for (const fl of floors) {
    const fy = r2(fl.from[1]);
    const near = walls.filter(w => Math.abs(r2(w.from[1]) - fy) < TOL || Math.abs(r2(w.to[1]) - fy) < TOL);
    // a slab at fy should have walls whose bottom == fy (supporting) OR top == fy
    const hasBottom = walls.some(w => Math.abs(r2(w.from[1]) - fy) < TOL || Math.abs(r2(w.to[1]) - fy) < TOL);
    if (!hasBottom && floors.length > 1) f.verticalGaps.push(`slab ${fl.id}@y=${fy} 无相邻墙体`);
  }
  const comps = bp.geometry?.components || [];
  for (const c of comps)
    if (Array.isArray(c.from) && Math.abs(c.from[2]) > 0.05) f.from2Offsets.push(`${c.type}#${c.id} from[2]=${c.from[2]}`);
  f.wallCount = walls.length;
  f.floorCount = floors.length;
  return f;
}
function segOverlap2D(a, b) {
  const ax = a.x2 - a.x1, az = a.z2 - a.z1, bx = b.x2 - b.x1, bz = b.z2 - b.z1;
  const la = Math.hypot(ax, az), lb = Math.hypot(bx, bz);
  if (la < 1e-6 || lb < 1e-6) return 0;
  if (axmax(a) < bxmin(b) - TOL || bxmax(b) < axmin(a) - TOL) return 0;
  if (azmax(a) < bzmin(b) - TOL || bzmax(b) < azmin(a) - TOL) return 0;
  const dot = (ax * bx + az * bz) / (la * lb);
  if (Math.abs(dot) < 0.95) return 0;
  const ux = ax / la, uz = az / la;
  const proj = (x, z) => (x - a.x1) * ux + (z - a.z1) * uz;
  const b1 = proj(b.x1, b.z1), b2 = proj(b.x2, b.z2);
  return Math.max(0, Math.min(la, Math.max(b1, b2)) - Math.max(0, Math.min(b1, b2)));
}
const axmin = s => Math.min(s.x1, s.x2), axmax = s => Math.max(s.x1, s.x2);
const azmin = s => Math.min(s.z1, s.z2), azmax = s => Math.max(s.z1, s.z2);
const bxmin = s => Math.min(s.x1, s.x2), bxmax = s => Math.max(s.x1, s.x2);
const bzmin = s => Math.min(s.z1, s.z2), bzmax = s => Math.max(s.z1, s.z2);

function detectOverlapComps(bp) {
  const comps = bp.geometry?.components || [];
  const byWall = {};
  for (const c of comps) if (c.parentWall && c.width != null) (byWall[c.parentWall] ||= []).push(c);
  const overlaps = [];
  for (const [wall, list] of Object.entries(byWall)) {
    const sorted = list.slice().sort((x, y) => x.from[0] - y.from[0]);
    for (let i = 1; i < sorted.length; i++) {
      const prev = sorted[i - 1], cur = sorted[i];
      const prevEnd = prev.from[0] + prev.width, curEnd = cur.from[0] + cur.width;
      const ov = Math.min(prevEnd, curEnd) - cur.from[0];
      if (ov <= 0.02) continue;
      const [py0, py1] = getCompYRange(prev), [cy0, cy1] = getCompYRange(cur);
      const yov = Math.min(py1, cy1) - Math.max(py0, cy0);
      if (yov > 0.05) overlaps.push(`${wall}: ${prev.id}(${r2(prev.from[0])}-${r2(prevEnd)}) X ${cur.id}(${r2(cur.from[0])}-${r2(curEnd)}) ov=${r2(ov)}m yov=${r2(yov)}m`);
    }
  }
  return overlaps;
}

const outDir = await mkdtemp(join(tmpdir(), 'wild-analyze-'));
const summary = { files: 0, parseFail: 0, compileErr: 0, reconErr: 0, openCorner: 0, dblWall: 0, compOverlap: 0, from2: 0, vgap: 0 };
try {
  await build({
    root, logLevel: 'silent',
    plugins: [{
      name: 'wild-analyze-entry',
      resolveId(id) {
        if (id === 'virtual:wild-analyze') return '\0virtual:wild-analyze';
        if (id === 'wildsrc:parser') return parserPath;
        if (id === 'wildsrc:core') return corePath;
        if (id === 'wildsrc:compiler') return compilerPath;
      },
      load(id) { if (id === '\0virtual:wild-analyze') return virtualEntry; },
    }],
    build: { outDir, emptyOutDir: false, minify: false, rollupOptions: { input: 'virtual:wild-analyze', preserveEntrySignatures: 'exports-only', output: { format: 'es', entryFileNames: 'wild-analyze.mjs' } } },
  });
  const core = await import(`${pathToFileURL(join(outDir, 'wild-analyze.mjs')).href}?t=${Date.now()}`);
  const paths = await collectPaths(process.argv.slice(2));
  console.log(`待分析蓝图: ${paths.length}\n`);
  for (const p of paths) {
    summary.files++;
    const name = p.split(/[\\/]/).pop();
    let bp;
    try { bp = core.parseBlueprint(await readFile(p, 'utf8')); }
    catch (e) { summary.parseFail++; console.log(`[PARSE FAIL] ${name}: ${e.message.split(';')[0]}`); continue; }
    const geo = analyzeGeometry(bp);
    const compOverlaps = detectOverlapComps(bp);
    const compilation = core.compileBlueprintComponents(bp);
    const ce = compilation.diagnostics.filter(d => d.level === 'error');
    if (ce.length) summary.compileErr++;
    let errs = [], warns = 0, meshes = 0;
    try {
      const entity = await core.reconstructEntity(compilation.blueprint);
      errs = entity.diagnostics.filter(d => d.level === 'error');
      warns = entity.diagnostics.filter(d => d.level === 'warning').length;
      meshes = entity.meshes.length;
    } catch (e) { errs.push({ message: 'reconstruct threw: ' + e.message }); }
    if (errs.length) summary.reconErr++;
    if (geo.openCorners.length) summary.openCorner++;
    if (geo.overlappingWalls.length) summary.dblWall++;
    if (compOverlaps.length) summary.compOverlap++;
    if (geo.from2Offsets.length) summary.from2++;
    if (geo.verticalGaps.length) summary.vgap++;

    const issues = [];
    if (ce.length) issues.push(`组件错误${ce.length}`);
    if (errs.length) issues.push(`重建错误${errs.length}`);
    if (warns) issues.push(`警告${warns}`);
    if (geo.openCorners.length) issues.push(`开口角${geo.openCorners.length}`);
    if (geo.overlappingWalls.length) issues.push(`重叠墙${geo.overlappingWalls.length}`);
    if (compOverlaps.length) issues.push(`组件重叠${compOverlaps.length}`);
    if (geo.from2Offsets.length) issues.push(`from2偏移${geo.from2Offsets.length}`);
    if (geo.verticalGaps.length) issues.push(`竖向缝${geo.verticalGaps.length}`);
    const tag = issues.length ? 'ISSUES' : 'ok';
    console.log(`[${tag}] ${name} 墙=${geo.wallCount} 楼板=${geo.floorCount} 网格=${meshes}${issues.length ? ' :: ' + issues.join(', ') : ''}`);
    if (compOverlaps.length) for (const o of compOverlaps.slice(0, 4)) console.log(`     重叠: ${o}`);
    if (geo.openCorners.length) console.log(`     开口角: ${geo.openCorners.slice(0, 6).join('; ')}`);
    if (geo.overlappingWalls.length) console.log(`     重叠墙: ${geo.overlappingWalls.slice(0, 6).join('; ')}`);
  }
  console.log(`\n==== 汇总 (${summary.files} 文件) ====`);
  console.log(`解析失败: ${summary.parseFail}`);
  console.log(`组件编译错误: ${summary.compileErr}`);
  console.log(`重建错误: ${summary.reconErr}`);
  console.log(`开口墙角(墙未闭合): ${summary.openCorner}`);
  console.log(`重叠/双墙: ${summary.dblWall}`);
  console.log(`同墙真实组件重叠(Y重叠): ${summary.compOverlap}`);
  console.log(`from[2]法向偏移: ${summary.from2}`);
  console.log(`竖向缝隙(楼板无相邻墙): ${summary.vgap}`);
} finally {
  await rm(outDir, { recursive: true, force: true });
}
