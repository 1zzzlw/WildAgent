/**
 * 渲染调试工具
 * 
 * 用于输出渲染过程中的详细信息，帮助诊断几何问题
 */

import type { Blueprint } from '../types/blueprint';
import type { ReconstructedEntity } from '../types/scene';

export function logBlueprintInfo(blueprint: Blueprint) {
  console.group('🔍 蓝图信息');
  console.log(`元素数量: ${blueprint.geometry.elements.length}`);
  
  const walls = blueprint.geometry.elements.filter(e => e.type === 'wall');
  console.groupCollapsed(`墙体 (${walls.length}个)`);
  walls.forEach((w: any) => {
    const h = Math.abs(w.to[1] - w.from[1]);
    console.log(`${w.id.padEnd(25)} Y: ${w.from[1].toFixed(1)} → ${w.to[1].toFixed(1)} (${h.toFixed(1)}m)`);
  });
  console.groupEnd();
  
  const roofs = blueprint.geometry.elements.filter(e => e.type === 'roof');
  console.groupCollapsed(`屋顶 (${roofs.length}个)`);
  roofs.forEach((r: any) => {
    console.log(`${r.id}: span=${r.span}, depth=${r.depth}, height=${r.height}`);
    console.log(`  position: ${r.position ? JSON.stringify(r.position) : '(auto)'}`);
  });
  console.groupEnd();
  
  console.groupEnd();
}

export function logEntityInfo(entity: ReconstructedEntity) {
  console.group('📦 渲染实体');
  console.log(`网格数量: ${entity.meshes.length}`);
  console.log(`材质数量: ${entity.materialParams.length}`);
  console.log(`边界盒:`, entity.boundingBox);
  
  // 检查包围盒异常
  const size = {
    x: entity.boundingBox.max[0] - entity.boundingBox.min[0],
    y: entity.boundingBox.max[1] - entity.boundingBox.min[1],
    z: entity.boundingBox.max[2] - entity.boundingBox.min[2]
  };
  console.log(`边界盒尺寸: X=${size.x.toFixed(1)}m, Y=${size.y.toFixed(1)}m, Z=${size.z.toFixed(1)}m`);
  
  if (size.x > 25 || size.y > 15 || size.z > 25) {
    console.warn('⚠️ 边界盒异常大！可能有mesh坐标错误');
  }
  
  // 按elementId分组统计
  const byElementId = new Map<string, number>();
  entity.meshes.forEach(m => {
    const id = m.elementId || '(no-id)';
    byElementId.set(id, (byElementId.get(id) || 0) + 1);
  });
  console.log('网格分布:', Object.fromEntries(byElementId));
  
  // 打印边界盒的实际min/max值
  console.log('边界盒详情:');
  console.log(`  min: [${entity.boundingBox.min.map(v => v.toFixed(2)).join(', ')}]`);
  console.log(`  max: [${entity.boundingBox.max.map(v => v.toFixed(2)).join(', ')}]`);
  
  // 检查每个mesh的世界坐标边界
  console.groupCollapsed('🔍 检查异常mesh');
  entity.meshes.forEach((m, i) => {
    const { position, scale } = m.transform;
    let minX = Infinity, maxX = -Infinity;
    let minY = Infinity, maxY = -Infinity;
    let minZ = Infinity, maxZ = -Infinity;
    
    for (let j = 0; j < m.geometry.length; j += 3) {
      const x = m.geometry[j] * scale[0] + position[0];
      const y = m.geometry[j + 1] * scale[1] + position[1];
      const z = m.geometry[j + 2] * scale[2] + position[2];
      
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
      if (z < minZ) minZ = z;
      if (z > maxZ) maxZ = z;
    }
    
    const meshSize = {
      x: maxX - minX,
      y: maxY - minY,
      z: maxZ - minZ
    };
    
    // 如果mesh范围异常大，输出警告
    if (meshSize.x > 20 || meshSize.y > 10 || meshSize.z > 20) {
      console.warn(`#${i} ${m.elementId || '(no-id)'}: 异常大！`);
      console.log(`  范围: X[${minX.toFixed(1)}, ${maxX.toFixed(1)}] Y[${minY.toFixed(1)}, ${maxY.toFixed(1)}] Z[${minZ.toFixed(1)}, ${maxZ.toFixed(1)}]`);
      console.log(`  尺寸: ${meshSize.x.toFixed(1)} × ${meshSize.y.toFixed(1)} × ${meshSize.z.toFixed(1)}`);
      console.log(`  position:`, position);
      console.log(`  scale:`, scale);
      console.log(`  顶点数: ${m.geometry.length / 3}`);
      console.log(`  materialRef:`, m.materialRef);
    }
  });
  console.groupEnd();
  
  const roofMeshes = entity.meshes.filter(m => 
    m.materialRef === 'roof_tile' || 
    m.materialRef === 'roof_structure' ||
    m.materialRef === 'roof_blue' ||
    (m.elementId && m.elementId.includes('roof'))
  );
  console.groupCollapsed(`屋顶网格 (${roofMeshes.length}个)`);
  roofMeshes.forEach((m, i) => {
    console.log(`#${i}: ${m.elementId || '(无ID)'}`);
    console.log(`  materialRef: ${m.materialRef}`);
    console.log(`  position: [${m.transform.position.map(v => v.toFixed(2)).join(', ')}]`);
    console.log(`  rotation: [${m.transform.rotation.map(v => v.toFixed(2)).join(', ')}]`);
    console.log(`  scale: [${m.transform.scale.map(v => v.toFixed(2)).join(', ')}]`);
    console.log(`  vertices: ${m.geometry.length / 3}`);
    // 输出几何范围
    let minY = Infinity, maxY = -Infinity;
    for (let i = 0; i < m.geometry.length; i += 3) {
      const y = m.geometry[i + 1];
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
    }
    console.log(`  geometry Y range: ${minY.toFixed(2)} to ${maxY.toFixed(2)}`);
  });
  console.groupEnd();
  
  const wallMeshes = entity.meshes.filter(m => m.elementId && m.elementId.includes('wall'));
  console.groupCollapsed(`墙体网格 (${wallMeshes.length}个)`);
  wallMeshes.forEach((m, i) => {
    console.log(`#${i}: ${m.elementId}`);
    console.log(`  position: [${m.transform.position.map(v => v.toFixed(2)).join(', ')}]`);
    console.log(`  rotation: [${m.transform.rotation.map(v => v.toFixed(2)).join(', ')}]`);
  });
  console.groupEnd();
  
  const floorMeshes = entity.meshes.filter(m => m.elementId && m.elementId.includes('floor'));
  console.groupCollapsed(`地板网格 (${floorMeshes.length}个)`);
  floorMeshes.forEach((m, i) => {
    console.log(`#${i}: ${m.elementId}`);
    console.log(`  position: [${m.transform.position.map(v => v.toFixed(2)).join(', ')}]`);
  });
  console.groupEnd();
  
  console.groupEnd();
}

export function logResolverChanges(blueprint: Blueprint) {
  console.group('🔧 Resolver修改');
  
  const roof = blueprint.geometry.elements.find(e => e.type === 'roof') as any;
  if (roof) {
    console.log(`屋顶position: ${JSON.stringify(roof.position)}`);
  }
  
  console.groupEnd();
}
