import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { build } from 'vite';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const target = process.argv[2] || join(root, 'lantu', 'generated_modern_villa.wild');

const parserPath = join(root, 'src/wild-core/src/primitive/parser.ts').replaceAll('\\', '/');
const corePath = join(root, 'src/wild-core/src/primitive/index.ts').replaceAll('\\', '/');
const compilerPath = join(root, 'src/wild-compiler/index.ts').replaceAll('\\', '/');
const virtualEntry = `
export { parseBlueprint } from 'wildsrc:parser';
export { reconstructEntity } from 'wildsrc:core';
export { compileBlueprintComponents } from 'wildsrc:compiler';
`;

const outputDirectory = await mkdtemp(join(tmpdir(), 'wild-validate-'));
try {
  await build({
    root,
    logLevel: 'silent',
    plugins: [{
      name: 'wild-validate-entry',
      resolveId(id) {
        if (id === 'virtual:wild-validate') return '\0virtual:wild-validate';
        if (id === 'wildsrc:parser') return parserPath;
        if (id === 'wildsrc:core') return corePath;
        if (id === 'wildsrc:compiler') return compilerPath;
      },
      load(id) {
        if (id === '\0virtual:wild-validate') return virtualEntry;
      },
    }],
    build: {
      outDir: outputDirectory,
      emptyOutDir: false,
      minify: false,
      rollupOptions: {
        input: 'virtual:wild-validate',
        preserveEntrySignatures: 'exports-only',
        output: { format: 'es', entryFileNames: 'wild-validate.mjs' },
      },
    },
  });

  const core = await import(`${pathToFileURL(join(outputDirectory, 'wild-validate.mjs')).href}?t=${Date.now()}`);
  const jsonText = await readFile(target, 'utf8');
  const blueprint = core.parseBlueprint(jsonText);
  const compilation = core.compileBlueprintComponents(blueprint);
  const compileErrors = compilation.diagnostics.filter(d => d.level === 'error');
  const entity = await core.reconstructEntity(compilation.blueprint);
  const errors = entity.diagnostics.filter(d => d.level === 'error');
  const warnings = entity.diagnostics.filter(d => d.level === 'warning');

  const finiteBounds = [...entity.boundingBox.min, ...entity.boundingBox.max].every(Number.isFinite);
  const validMeshes = entity.meshes.every(m => Array.from(m.geometry).every(Number.isFinite));

  console.log(`蓝图: ${target}`);
  console.log(`组件编译诊断: ${compilation.diagnostics.length} (错误 ${compileErrors.length})`);
  for (const d of compilation.diagnostics) {
    console.log(`  [${d.level}] ${d.elementType}#${d.elementId}: ${d.message}`);
  }
  console.log(`网格数: ${entity.meshes.length}`);
  console.log(`材质参数: ${entity.materialParams.length}`);
  console.log(`包围盒: min=${JSON.stringify(entity.boundingBox.min)} max=${JSON.stringify(entity.boundingBox.max)}`);
  console.log(`finiteBounds=${finiteBounds} validMeshes=${validMeshes}`);
  console.log(`重建诊断: 错误 ${errors.length}, 警告 ${warnings.length}`);
  for (const d of errors) {
    console.log(`  [error] ${d.elementType || ''}#${d.elementId || ''}: ${d.message}`);
  }
  for (const w of warnings.slice(0, 20)) {
    console.log(`  [warn] ${w.elementType || ''}#${w.elementId || ''}: ${w.message}`);
  }

  const totalErrors = compileErrors.length + errors.length;
  if (totalErrors > 0 || !finiteBounds || !validMeshes) {
    console.log(`\n校验失败: ${totalErrors} 个错误`);
    process.exit(1);
  }
  console.log('\n校验通过: 0 错误');
} finally {
  await rm(outputDirectory, { recursive: true, force: true });
}
