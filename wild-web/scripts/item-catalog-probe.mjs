// 探测 reconstructEntity 的返回结构，供 item-catalog 出图脚本对齐字段。
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { build } from 'vite';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const core = join(root, '..', 'wild-core', 'src').replaceAll('\\', '/');

const virtualEntry = `
export { parseBlueprint } from 'wildsrc:parser';
export { reconstructEntity } from 'wildsrc:core';
export { compileBlueprintComponents } from 'wildsrc:compiler';
`;

const out = await mkdtemp(join(tmpdir(), 'wild-probe-'));
try {
  await build({
    root,
    logLevel: 'silent',
    plugins: [
      {
        name: 'probe',
        resolveId(id) {
          if (id === 'virtual:probe') return '\0virtual:probe';
          if (id === 'wildsrc:parser') return `${core}/primitive/parser.ts`;
          if (id === 'wildsrc:core') return `${core}/primitive/index.ts`;
          if (id === 'wildsrc:compiler') return `${core}/compiler/index.ts`;
        },
        load(id) {
          if (id === '\0virtual:probe') return virtualEntry;
        },
      },
    ],
    build: {
      outDir: out,
      emptyOutDir: false,
      minify: false,
      rollupOptions: {
        input: 'virtual:probe',
        preserveEntrySignatures: 'exports-only',
        output: { format: 'es', entryFileNames: 'probe.mjs' },
      },
    },
  });

  const m = await import(`${pathToFileURL(join(out, 'probe.mjs')).href}?t=${Date.now()}`);
  const target = join(root, '..', 'wild-server', 'storage', 'item_catalog', 'items', 'sofa_three.wild');
  const text = await readFile(target, 'utf8');
  const bp = m.parseBlueprint(text);
  const comp = m.compileBlueprintComponents(bp);
  const entity = await m.reconstructEntity(comp.blueprint);
  console.log('entity keys:', Object.keys(entity));
  console.log('diagnostics:', JSON.stringify(entity.diagnostics));
  console.log('bounds:', JSON.stringify(entity.boundingBox));
  console.log('mesh count:', entity.meshes.length);
  const m0 = entity.meshes[0];
  console.log('mesh[0] keys:', Object.keys(m0));
  console.log('mesh[0] transform:', JSON.stringify(m0.transform), 'materialRef:', m0.materialRef);
  console.log('geometry len:', m0.geometry?.length, 'indices len:', m0.indices?.length);
  console.log('materialParams[0]:', JSON.stringify(entity.materialParams?.[0]).slice(0, 400));
} finally {
  await rm(out, { recursive: true, force: true });
}
