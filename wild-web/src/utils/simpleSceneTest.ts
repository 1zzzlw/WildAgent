/**
 * 简单场景测试
 * 
 * 用于验证Three.js基础渲染是否正常工作
 */

import * as THREE from 'three';

export function createTestScene(scene: THREE.Scene) {
  console.log('🧪 创建测试场景');
  
  // 1. 红色立方体在原点
  const cubeGeo = new THREE.BoxGeometry(1, 1, 1);
  const cubeMat = new THREE.MeshStandardMaterial({ color: 0xff0000 });
  const cube = new THREE.Mesh(cubeGeo, cubeMat);
  cube.position.set(0, 0.5, 0);
  cube.name = 'TestCube';
  scene.add(cube);
  console.log('✓ 添加红色立方体', cube.position);
  
  // 2. 绿色地板
  const floorGeo = new THREE.BoxGeometry(5, 0.2, 5);
  const floorMat = new THREE.MeshStandardMaterial({ color: 0x00ff00 });
  const floor = new THREE.Mesh(floorGeo, floorMat);
  floor.position.set(0, -0.1, 0);
  floor.name = 'TestFloor';
  scene.add(floor);
  console.log('✓ 添加绿色地板', floor.position);
  
  // 3. 蓝色墙壁
  const wallGeo = new THREE.BoxGeometry(5, 2, 0.2);
  const wallMat = new THREE.MeshStandardMaterial({ color: 0x0000ff });
  const wall = new THREE.Mesh(wallGeo, wallMat);
  wall.position.set(0, 1, -2.5);
  wall.name = 'TestWall';
  scene.add(wall);
  console.log('✓ 添加蓝色墙壁', wall.position);
  
  console.log('🧪 测试场景创建完成');
  console.log('场景对象:', scene.children.map(c => c.name));
}

export function clearTestScene(scene: THREE.Scene) {
  const testObjects = scene.children.filter(c => 
    c.name === 'TestCube' || c.name === 'TestFloor' || c.name === 'TestWall'
  );
  
  testObjects.forEach(obj => {
    scene.remove(obj);
    if (obj instanceof THREE.Mesh) {
      obj.geometry.dispose();
      if (obj.material instanceof THREE.Material) {
        obj.material.dispose();
      }
    }
  });
  
  console.log('🧹 测试场景已清除');
}
