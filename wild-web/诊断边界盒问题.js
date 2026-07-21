/**
 * 在浏览器控制台运行此脚本来诊断边界盒异常
 * 
 * 使用方法：
 * 1. 加载 bieshu.wild
 * 2. 打开控制台（F12）
 * 3. 复制整个脚本
 * 4. 粘贴到控制台
 * 5. 按回车运行
 */

console.clear();
console.log('=== 边界盒诊断工具 ===\n');

// 获取WildScene组
const wildScene = debugScene.scene.children.find(c => c.name === 'WildScene');
if (!wildScene) {
  console.error('❌ 找不到WildScene组！');
} else {
  console.log(`✓ WildScene组找到，包含 ${wildScene.children.length} 个mesh\n`);
  
  // 计算每个mesh的世界边界盒
  const meshBounds = [];
  
  wildScene.children.forEach((mesh, i) => {
    if (!mesh.geometry) return;
    
    const pos = mesh.position;
    const scale = mesh.scale;
    const rotation = mesh.rotation;
    
    // 获取几何体顶点
    const geometry = mesh.geometry;
    const position_attr = geometry.attributes.position;
    
    if (!position_attr) return;
    
    let minX = Infinity, maxX = -Infinity;
    let minY = Infinity, maxY = -Infinity;
    let minZ = Infinity, maxZ = -Infinity;
    
    // 计算世界坐标边界
    for (let j = 0; j < position_attr.count; j++) {
      const x = position_attr.getX(j) * scale.x + pos.x;
      const y = position_attr.getY(j) * scale.y + pos.y;
      const z = position_attr.getZ(j) * scale.z + pos.z;
      
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
      if (z < minZ) minZ = z;
      if (z > maxZ) maxZ = z;
    }
    
    const sizeX = maxX - minX;
    const sizeY = maxY - minY;
    const sizeZ = maxZ - minZ;
    
    meshBounds.push({
      index: i,
      name: mesh.name || '(unnamed)',
      minX, maxX, minY, maxY, minZ, maxZ,
      sizeX, sizeY, sizeZ,
      position: [pos.x.toFixed(2), pos.y.toFixed(2), pos.z.toFixed(2)],
      vertexCount: position_attr.count
    });
  });
  
  // 找出超出正常范围的mesh
  console.log('🔍 异常mesh（超出正常范围）:\n');
  
  const abnormal = meshBounds.filter(m => 
    m.sizeX > 20 || m.sizeY > 10 || m.sizeZ > 20 ||
    Math.abs(m.minX) > 15 || Math.abs(m.maxX) > 15 ||
    Math.abs(m.minZ) > 15 || Math.abs(m.maxZ) > 15
  );
  
  if (abnormal.length === 0) {
    console.log('✓ 没有发现异常mesh！');
  } else {
    abnormal.forEach(m => {
      console.log(`#${m.index}: ${m.name}`);
      console.log(`  范围: X[${m.minX.toFixed(1)}, ${m.maxX.toFixed(1)}]  Y[${m.minY.toFixed(1)}, ${m.maxY.toFixed(1)}]  Z[${m.minZ.toFixed(1)}, ${m.maxZ.toFixed(1)}]`);
      console.log(`  尺寸: ${m.sizeX.toFixed(1)} × ${m.sizeY.toFixed(1)} × ${m.sizeZ.toFixed(1)}`);
      console.log(`  position: [${m.position.join(', ')}]`);
      console.log(`  顶点数: ${m.vertexCount}`);
      console.log('');
    });
  }
  
  // 计算总边界盒
  let globalMinX = Infinity, globalMaxX = -Infinity;
  let globalMinY = Infinity, globalMaxY = -Infinity;
  let globalMinZ = Infinity, globalMaxZ = -Infinity;
  
  meshBounds.forEach(m => {
    if (m.minX < globalMinX) globalMinX = m.minX;
    if (m.maxX > globalMaxX) globalMaxX = m.maxX;
    if (m.minY < globalMinY) globalMinY = m.minY;
    if (m.maxY > globalMaxY) globalMaxY = m.maxY;
    if (m.minZ < globalMinZ) globalMinZ = m.minZ;
    if (m.maxZ > globalMaxZ) globalMaxZ = m.maxZ;
  });
  
  console.log('\n📏 总边界盒:');
  console.log(`  min: [${globalMinX.toFixed(2)}, ${globalMinY.toFixed(2)}, ${globalMinZ.toFixed(2)}]`);
  console.log(`  max: [${globalMaxX.toFixed(2)}, ${globalMaxY.toFixed(2)}, ${globalMaxZ.toFixed(2)}]`);
  console.log(`  尺寸: ${(globalMaxX - globalMinX).toFixed(1)}m × ${(globalMaxY - globalMinY).toFixed(1)}m × ${(globalMaxZ - globalMinZ).toFixed(1)}m`);
  
  const expectedSize = {
    x: 16.3,
    y: 9.1,
    z: 16.8
  };
  
  const actualSize = {
    x: globalMaxX - globalMinX,
    y: globalMaxY - globalMinY,
    z: globalMaxZ - globalMinZ
  };
  
  console.log('\n✓ 预期尺寸: ~16.3m × 9.1m × ~16.8m');
  
  if (actualSize.x > 20 || actualSize.z > 20) {
    console.log('❌ 实际尺寸异常！');
  } else {
    console.log('✓ 实际尺寸正常！');
  }
}

console.log('\n===================\n');
