import fs from 'fs';
import { parseBlueprint, reconstructEntity } from '../src/wild-core/src/primitive/index.js';

const blueprintText = fs.readFileSync('./lantu/bieshu.wild', 'utf-8');
const blueprint = parseBlueprint(blueprintText);

console.log('=== 蓝图信息 ===');
console.log(`元素数量: ${blueprint.geometry.elements.length}`);

const walls = blueprint.geometry.elements.filter(e => e.type === 'wall');
console.log(`\n=== 墙体 (${walls.length}个) ===`);
walls.forEach(w => {
  const h = Math.abs(w.to[1] - w.from[1]);
  console.log(`${w.id.padEnd(25)} Y: ${w.from[1].toFixed(1)} → ${w.to[1].toFixed(1)} (${h.toFixed(1)}m)`);
});

const roofs = blueprint.geometry.elements.filter(e => e.type === 'roof');
console.log(`\n=== 屋顶 (${roofs.length}个) ===`);
roofs.forEach(r => {
  console.log(`${r.id}: span=${r.span}, depth=${r.depth}, height=${r.height}`);
  console.log(`  position: ${r.position || '(auto)'}`);
});

console.log('\n=== 重建场景 ===');
const entity = await reconstructEntity(blueprint);
console.log(`生成网格: ${entity.meshes.length}个`);
console.log(`材质参数: ${entity.materialParams.length}个`);
console.log(`边界盒: ${JSON.stringify(entity.boundingBox)}`);

// 找到屋顶网格
const roofMeshes = entity.meshes.filter(m => m.materialRef === 'roof_tile' || m.elementId === 'main_roof');
console.log(`\n=== 屋顶网格 (${roofMeshes.length}个) ===`);
roofMeshes.forEach((m, i) => {
  console.log(`#${i}: elementId=${m.elementId}, materialRef=${m.materialRef}`);
  console.log(`  transform.position: [${m.transform.position.map(v => v.toFixed(2)).join(', ')}]`);
  console.log(`  transform.rotation: [${m.transform.rotation.map(v => v.toFixed(2)).join(', ')}]`);
  console.log(`  geometry vertices: ${m.geometry.length / 3}`);
});

// 找到墙体网格
const wallMeshes = entity.meshes.filter(m => m.elementId && m.elementId.includes('wall'));
console.log(`\n=== 墙体网格 (${wallMeshes.length}个) ===`);
wallMeshes.slice(0, 5).forEach((m, i) => {
  console.log(`#${i}: ${m.elementId}`);
  console.log(`  position: [${m.transform.position.map(v => v.toFixed(2)).join(', ')}]`);
  console.log(`  rotation: [${m.transform.rotation.map(v => v.toFixed(2)).join(', ')}]`);
});

// 检查resolver对屋顶position的修改
console.log('\n=== 检查蓝图修改 ===');
const roofAfter = blueprint.geometry.elements.find(e => e.type === 'roof');
console.log(`屋顶position（resolver后）: ${JSON.stringify(roofAfter.position)}`);
