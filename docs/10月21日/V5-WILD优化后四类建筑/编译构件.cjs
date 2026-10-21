// 离线调用当前 Core 的解析与构件编译入口，不构建前端、不启动浏览器。
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../../..');
const ts = require(path.join(root, 'wild-web/node_modules/typescript'));
const cache = new Map();

function sourceModule(filename) {
  if (cache.has(filename)) return cache.get(filename).exports;
  if (filename.endsWith('.json')) return JSON.parse(fs.readFileSync(filename, 'utf8'));
  const module = { exports: {} };
  cache.set(filename, module);
  const output = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, esModuleInterop: true },
    fileName: filename,
  }).outputText;
  function relativeRequire(id) {
    if (!id.startsWith('.')) return require(id);
    const base = path.resolve(path.dirname(filename), id);
    const resolved = [base, base + '.ts', path.join(base, 'index.ts')]
      .find(candidate => fs.existsSync(candidate) && fs.statSync(candidate).isFile());
    if (!resolved) throw new Error('找不到源码模块: ' + id);
    return sourceModule(resolved);
  }
  new Function('require', 'module', 'exports', output)(relativeRequire, module, module.exports);
  return module.exports;
}

const { parseBlueprintWithReport } = sourceModule(path.join(root, 'wild-core/src/primitive/parser.ts'));
const { compileBlueprintComponents } = sourceModule(path.join(root, 'wild-core/src/compiler/index.ts'));
for (const folder of ['欧式别墅', '新中式别墅', '凉亭', '写字楼']) {
  const directory = path.join(__dirname, folder);
  const name = fs.readdirSync(directory).find(file => file.endsWith('.wild'));
  const source = fs.readFileSync(path.join(directory, name), 'utf8');
  const parsed = parseBlueprintWithReport(source);
  const result = compileBlueprintComponents(parsed.blueprint);
  if (result.diagnostics.some(row => row.level === 'error')) {
    throw new Error(folder + ': ' + JSON.stringify(result.diagnostics));
  }
  const recordPath = path.join(directory, '生成记录.json');
  const record = JSON.parse(fs.readFileSync(recordPath, 'utf8'));
  record.route.push('当前 wild-core parseBlueprintWithReport / compileBlueprintComponents');
  record.core_component_compilation = { diagnostics: result.diagnostics,
    source_migrations: parsed.changes, native_element_count: result.blueprint.geometry.elements.length,
    mapping: result.mapping };
  fs.writeFileSync(recordPath, JSON.stringify(record, null, 2) + '\n');
  process.stdout.write(JSON.stringify({ folder, native_elements: result.blueprint.geometry.elements.length,
    diagnostics: result.diagnostics.length, migrations: parsed.changes.length }) + '\n');
}
