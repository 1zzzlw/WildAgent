// 物品实例回归：验证复杂 WILD 物品在放置后仍保留内部引用、材质与整体编辑语义。
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { build } from 'vite';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const output = await mkdtemp(join(tmpdir(), 'wild-item-placement-'));
const virtualEntry = `
export { createBlockPlacement } from './src/wild/blockPlacement.ts';
export { applyPatchToBlueprint, createGeometryRemovalOperations, createPatch } from './src/wild/scenePatch.ts';
export { createGeometryRotationOperations, createGeometryTranslationOperations } from './src/wild/componentDrag.ts';
export { expandItemSelection } from './src/wild/itemGroups.ts';
`;

let failures = 0;
const check = (condition, message) => {
  if (condition) return;
  failures += 1;
  console.error(`✗ ${message}`);
};

try {
  await build({
    root,
    logLevel: 'silent',
    plugins: [{
      name: 'item-placement-smoke',
      resolveId(id) { if (id === 'virtual:item-placement-smoke') return '\0virtual:item-placement-smoke'; },
      load(id) { if (id === '\0virtual:item-placement-smoke') return virtualEntry; },
    }],
    build: {
      outDir: output,
      emptyOutDir: false,
      minify: false,
      rollupOptions: {
        input: 'virtual:item-placement-smoke',
        preserveEntrySignatures: 'exports-only',
        output: { format: 'es', entryFileNames: 'probe.mjs' },
      },
    },
  });
  const api = await import(`${pathToFileURL(join(output, 'probe.mjs')).href}?t=${Date.now()}`);
  const blueprint = {
    meta: { version: '1.0', type: 'scene', name: 'probe' },
    geometry: { elements: [] },
    materials: {},
    editor: { groups: {} },
  };
  const asset = {
    itemId: 'boolean-chair',
    materials: {
      wood: { baseColor: [0.4, 0.2, 0.1], roughness: 0.7, metallic: 0, albedo: 1, lightingCondition: 'D65_noon' },
    },
    assets: {},
    parts: [
      { type: 'primitive', id: 'left', shape: 'box', position: [-0.5, 0.5, 0], dimensions: [1, 1, 1], material: 'wood' },
      { type: 'primitive', id: 'right', shape: 'box', position: [0.5, 0.5, 0], dimensions: [1, 1, 1], material: 'wood' },
      { type: 'solid', id: 'seat', kind: 'boolean', operation: 'union', operands: ['left', 'right'], material: 'wood' },
    ],
  };
  const draft = api.createBlockPlacement(
    { kind: 'item', id: 'item_probe', label: '测试椅', asset },
    blueprint,
    [4, 0, 5],
  );
  const placed = api.applyPatchToBlueprint(blueprint, api.createPatch(0, draft.operations));
  const ids = placed.geometry.elements.map(element => element.id);
  const boolean = placed.geometry.elements.find(element => element.id === 'item_probe_seat');
  check(ids.length === 3 && ids.every(id => id.startsWith('item_probe_')), '每次放置必须命名空间化全部零件 id');
  check(boolean?.operands?.join(',') === 'item_probe_left,item_probe_right', '布尔 operands 必须同步重写');
  check(placed.geometry.elements.every(element => element.material === 'item_boolean-chair_wood'), '零件材质引用必须同步重写');
  check(Boolean(placed.materials?.['item_boolean-chair_wood']), '物品材质定义必须进入场景');
  check(placed.editor.groups.item_probe.elements.length === 3, '物品实例必须持久化编辑分组');
  check(api.expandItemSelection(placed, ['item_probe_left']).length === 3, '点击任一零件必须展开为整件选择');

  const move = api.createGeometryTranslationOperations(placed, ['item_probe_left'], [1, 0, 0]);
  check(move.length === 2, '移动整件时应更新两个实体输入，布尔结果不写非法 transform');
  const rotate = api.createGeometryRotationOperations(placed, draft.selectionIds);
  check(rotate.length === 2, '旋转整件时应围绕共同中心更新所有实体输入');
  const remove = api.createGeometryRemovalOperations(placed, ['item_probe_right']);
  check(remove.length === 3, '删除任一零件必须删除完整物品');

  if (!failures) console.log('✓ 物品放置、引用、材质、整体选择/移动/旋转/删除回归通过');
} finally {
  await rm(output, { recursive: true, force: true });
}

process.exit(failures ? 1 : 0);
