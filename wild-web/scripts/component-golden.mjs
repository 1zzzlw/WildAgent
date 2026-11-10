// 构件编译黄金基线：证明「把几何装配数据化」前后编译输出没有变化。
//
// 只装 `compiler/index.ts` 一个入口，不碰 renderer —— 这里量的是
// `compileBlueprintComponents()` 吐出的 element 序列（id / type / 位置 / 尺寸 /
// 旋转 / 材质 / `_interaction` / `_cutoutOnly`），不是"渲染看起来一样"。
//
// 数值统一 round 到 1e-6 米（微米）：真改动一定能被抓到，浮点结合顺序的
// 末位差异不会造成假红。
//
// 用法：
//   node scripts/component-golden.mjs            # 比对，与基线不一致则退出码 1
//   node scripts/component-golden.mjs --write    # 重写基线（只在确认改动是有意的时候用）
import { readFile, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { mkdtemp } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { build } from 'vite';

const here = dirname(fileURLToPath(import.meta.url));
const webRoot = join(here, '..');
const coreSrc = join(webRoot, '..', 'wild-core', 'src').replaceAll('\\', '/');
const fixturePath = join(webRoot, '..', 'wild-core', 'fixtures', 'components-golden.json');
const baselinePath = join(webRoot, '..', 'wild-core', 'fixtures', 'components-golden.baseline.json');

const virtualEntry = `
export { compileBlueprintComponents } from 'wildsrc:compiler';
export { getComponentCapabilities, getRecipeCapabilities, getRecipeDefaults } from 'wildsrc:compiler';
export { reconstructEntity } from 'wildsrc:core';
export { buildComponentEntries, LEGACY_COMPONENT_DISPLAY } from 'wildsrc:display';
`;

/** 递归排序键 + 数值定精度，得到可逐字节比较的稳定表示。 */
function normalize(value, key = '') {
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return String(value);
    const rounded = Math.round(value * 1e6) / 1e6;
    return Object.is(rounded, -0) ? 0 : rounded;
  }
  if (Array.isArray(value)) return value.map(item => normalize(item, key));
  if (value && typeof value === 'object') {
    const out = {};
    for (const name of Object.keys(value).sort()) out[name] = normalize(value[name], name);
    return out;
  }
  return value;
}

/** 逐行找第一处差异，避免把整个 JSON 打出来。 */
function firstDifference(a, b, path = '') {
  if (JSON.stringify(a) === JSON.stringify(b)) return null;
  if (Array.isArray(a) && Array.isArray(b)) {
    if (a.length !== b.length) return `${path}: 数组长度 ${a.length} → ${b.length}`;
    for (let i = 0; i < a.length; i += 1) {
      const diff = firstDifference(a[i], b[i], `${path}[${i}]`);
      if (diff) return diff;
    }
    return `${path}: 未知数组差异`;
  }
  if (a && b && typeof a === 'object' && typeof b === 'object') {
    const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
    for (const name of [...keys].sort()) {
      const diff = firstDifference(a[name], b[name], path ? `${path}.${name}` : name);
      if (diff) return diff;
    }
    return `${path}: 未知对象差异`;
  }
  return `${path || '(root)'}: ${JSON.stringify(a)} → ${JSON.stringify(b)}`;
}

const probe = await mkdtemp(join(tmpdir(), 'wild-component-golden-'));

await build({
  root: webRoot,
  logLevel: 'silent',
  plugins: [
    {
      name: 'component-golden',
      resolveId(id) {
        if (id === 'virtual:component-golden') return '\0virtual:component-golden';
        if (id === 'wildsrc:compiler') return `${coreSrc}/compiler/index.ts`;
        if (id === 'wildsrc:core') return `${coreSrc}/primitive/index.ts`;
        if (id === 'wildsrc:display') return `${webRoot.replaceAll('\\', '/')}/src/wild/componentDisplay.ts`;
      },
      load(id) {
        if (id === '\0virtual:component-golden') return virtualEntry;
      },
    },
  ],
  build: {
    outDir: probe,
    emptyOutDir: false,
    minify: false,
    rollupOptions: {
      input: 'virtual:component-golden',
      preserveEntrySignatures: 'exports-only',
      output: { format: 'es', entryFileNames: 'golden.mjs' },
    },
  },
});

const engine = await import(`${pathToFileURL(join(probe, 'golden.mjs')).href}?t=${Date.now()}`);

const fixture = JSON.parse(await readFile(fixturePath, 'utf8'));
const compilation = engine.compileBlueprintComponents(fixture);

const snapshot = normalize({
  elements: compilation.blueprint.geometry.elements,
  diagnostics: compilation.diagnostics,
  mapping: compilation.mapping,
});

const payload = `${JSON.stringify(snapshot, null, 2)}\n`;

if (process.argv.includes('--write')) {
  await writeFile(baselinePath, payload, 'utf8');
  const elements = compilation.blueprint.geometry.elements.length;
  const errors = compilation.diagnostics.filter(item => item.level === 'error').length;
  console.log(`已写基线: ${elements} 个 element / ${errors} 条 error 诊断 -> ${baselinePath}`);
  process.exit(0);
}

let baseline;
try {
  baseline = JSON.parse(await readFile(baselinePath, 'utf8'));
} catch (error) {
  console.error(`读不到基线 ${baselinePath}: ${error.message}`);
  console.error('先跑 node scripts/component-golden.mjs --write 建立基线。');
  process.exit(2);
}

const diff = firstDifference(baseline, snapshot);
const componentCount = (fixture.geometry.components || []).length;
const elementCount = compilation.blueprint.geometry.elements.length;
const errors = compilation.diagnostics.filter(item => item.level === 'error');

if (diff) {
  console.error(`✗ 构件编译输出与基线不一致（${componentCount} 个构件 / ${elementCount} 个 element）`);
  console.error(`  第一处差异: ${diff}`);
  process.exit(1);
}

if (errors.length > 0) {
  console.error(`✗ 输出与基线一致，但有 ${errors.length} 条 error 诊断（基线本身可能是坏的）`);
  for (const item of errors) console.error(`  ${item.elementId}: ${item.message}`);
  process.exit(1);
}

// 编译通过不等于引擎能重建：element 齐全但几何退化（空网格、包围盒退化）
// 在编译层完全看不出来。这里真跑一次 reconstructEntity，按构件类型统计三角形。
const entity = await engine.reconstructEntity(compilation.blueprint);
const buildErrors = entity.diagnostics.filter(item => item.level === 'error');
const emptyGeometry = entity.diagnostics.filter(item => item.code === 'EMPTY_GEOMETRY');
const triangles = entity.meshes.reduce((sum, mesh) => sum + mesh.geometry.length / 9, 0);

if (buildErrors.length > 0 || emptyGeometry.length > 0) {
  console.error(`✗ 引擎重建失败：${buildErrors.length} 条 error / ${emptyGeometry.length} 条空几何`);
  for (const item of [...buildErrors, ...emptyGeometry].slice(0, 8)) {
    console.error(`  [${item.code}] ${item.elementId || ''} ${item.message}`);
  }
  process.exit(1);
}
if (triangles <= 0) {
  console.error('✗ 引擎重建出 0 个三角形 —— 输出是退化的');
  process.exit(1);
}

console.log(`✓ 构件编译输出与基线逐字段一致（${componentCount} 个构件 / ${elementCount} 个 element）`);
console.log(`✓ 引擎重建通过（${entity.meshes.length} 个 mesh / ${triangles} 个三角形 / 0 error）`);

// 配方必须出现在能力清单里，否则前端的构件面板看不到它。
// 这条守的是「注册了但没进 capabilities」这种静默失败 —— 编译和渲染都正常，
// 只有面板少一个条目，肉眼很难发现。
const capabilities = engine.getComponentCapabilities();
const registered = new Set(capabilities.map(item => item.type));
const missing = (fixture.geometry.components || [])
  .map(item => item.type)
  .filter(type => !registered.has(type));
if (missing.length > 0) {
  console.error(`✗ 以下构件类型没有进能力清单: ${[...new Set(missing)].join(', ')}`);
  process.exit(1);
}
console.log(`✓ 能力清单包含全部 ${registered.size} 种构件类型`);

// 配方构件从面板拖进场景时，初始字段完全来自 `getRecipeDefaults()`。
// 缺 position 会落到 NaN 坐标 —— 编译期完全看不出来，只在视口里表现为"构件不见了"。
const missingDefaults = [];
for (const capability of engine.getRecipeCapabilities()) {
  const defaults = engine.getRecipeDefaults(capability.type);
  if (!defaults) { missingDefaults.push(`${capability.type}: 无默认值`); continue; }
  if (capability.host !== 'none' && !Array.isArray(defaults.position)) {
    missingDefaults.push(`${capability.type}: 缺 position 默认值`);
  }
}
if (missingDefaults.length > 0) {
  console.error('✗ 配方默认值不完整：');
  for (const line of missingDefaults) console.error(`  ${line}`);
  process.exit(1);
}
console.log(`✓ 配方默认值完整（${engine.getRecipeCapabilities().length} 份配方都带 position）`);

// 面板覆盖：引擎注册了什么，构件面板上就必须能点到什么。
// 这类失败不留任何痕迹 —— 编译、渲染、校验全绿，只是面板少一格。
const panelEntries = engine.buildComponentEntries();
const panelTypes = new Set(panelEntries.map(entry => entry.type));
const unseen = capabilities.map(item => item.type).filter(type => !panelTypes.has(type));
const unlabeled = panelEntries.filter(entry => !entry.label || !entry.icon);
if (unseen.length > 0) {
  console.error(`✗ 这些构件在面板上点不到: ${unseen.join(', ')}`);
  process.exit(1);
}
if (unlabeled.length > 0) {
  console.error(`✗ 这些面板条目缺显示名或图标: ${unlabeled.map(entry => entry.type).join(', ')}`);
  process.exit(1);
}
console.log(`✓ 面板覆盖全部 ${panelTypes.size} 种构件（${panelEntries.length} 个条目，含 light 的两种形态）`);
