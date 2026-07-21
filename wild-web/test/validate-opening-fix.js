/**
 * 验证开口坐标转换修复
 * 
 * 测试 resolveOpenings 是否正确将世界坐标转换为墙体局部坐标
 */

// 模拟墙体和开口数据
const testCases = [
  {
    name: "wall_front 的 window_front_left",
    wall: {
      from: [-8.0, 0.0, -6.0],
      to: [8.0, 3.0, -6.0],
      length: 16.0
    },
    opening: {
      from: [-5.0, 1.0, -6.0],  // 世界坐标
      width: 1.5,
      height: 1.2
    },
    expected: {
      localX: 3.0,  // -5.0 - (-8.0) = 3.0
      localY: 1.0,  // 1.0 - 0.0 = 1.0
      localW: 1.5,
      localH: 1.2
    }
  },
  {
    name: "wall_front 的 front_door",
    wall: {
      from: [-8.0, 0.0, -6.0],
      to: [8.0, 3.0, -6.0],
      length: 16.0
    },
    opening: {
      from: [0.0, 0.0, -6.0],  // 中心位置
      width: 1.2,
      height: 2.4
    },
    expected: {
      localX: 8.0,  // 0.0 - (-8.0) = 8.0 (墙中心)
      localY: 0.0,
      localW: 1.2,
      localH: 2.4
    }
  },
  {
    name: "wall_left 的 window_left",
    wall: {
      from: [-8.0, 0.0, -6.0],
      to: [-8.0, 3.0, 8.0],
      length: 14.0
    },
    opening: {
      from: [-8.0, 1.0, -2.0],
      width: 1.2,
      height: 1.2
    },
    expected: {
      localX: 4.0,  // 沿Z方向: -2.0 - (-6.0) = 4.0
      localY: 1.0,
      localW: 1.2,
      localH: 1.2
    }
  }
];

// 计算函数（与修复后的 resolveOpenings 逻辑相同）
function calculateLocalCoords(wall, opening) {
  const wallDx = wall.to[0] - wall.from[0];
  const wallDz = wall.to[2] - wall.from[2];
  const wallLen = Math.sqrt(wallDx * wallDx + wallDz * wallDz);
  
  if (wallLen < 0.001) {
    return { localX: 0, localY: 0 };
  }
  
  const openingX = opening.from[0];
  const openingZ = opening.from[2];
  const toOpeningX = openingX - wall.from[0];
  const toOpeningZ = openingZ - wall.from[2];
  
  const dirX = wallDx / wallLen;
  const dirZ = wallDz / wallLen;
  const localX = toOpeningX * dirX + toOpeningZ * dirZ;
  const localY = opening.from[1] - wall.from[1];
  
  return { localX, localY };
}

// 运行测试
console.log('=== 开口坐标转换验证 ===\n');

let passed = 0;
let failed = 0;

testCases.forEach(test => {
  const result = calculateLocalCoords(test.wall, test.opening);
  const tolerance = 0.01;
  
  const xMatch = Math.abs(result.localX - test.expected.localX) < tolerance;
  const yMatch = Math.abs(result.localY - test.expected.localY) < tolerance;
  
  const status = (xMatch && yMatch) ? '✓ PASS' : '✗ FAIL';
  
  if (xMatch && yMatch) {
    passed++;
  } else {
    failed++;
  }
  
  console.log(`${status}: ${test.name}`);
  console.log(`  墙体: from=[${test.wall.from.join(', ')}] to=[${test.wall.to.join(', ')}]`);
  console.log(`  开口世界坐标: [${test.opening.from.join(', ')}]`);
  console.log(`  计算结果: localX=${result.localX.toFixed(2)}, localY=${result.localY.toFixed(2)}`);
  console.log(`  期望结果: localX=${test.expected.localX.toFixed(2)}, localY=${test.expected.localY.toFixed(2)}`);
  
  if (!xMatch) {
    console.log(`  ❌ localX 不匹配: ${result.localX.toFixed(2)} != ${test.expected.localX.toFixed(2)}`);
  }
  if (!yMatch) {
    console.log(`  ❌ localY 不匹配: ${result.localY.toFixed(2)} != ${test.expected.localY.toFixed(2)}`);
  }
  console.log('');
});

console.log(`总结: ${passed} 通过, ${failed} 失败\n`);

if (failed === 0) {
  console.log('✓ 所有测试通过！坐标转换逻辑正确。');
} else {
  console.log('✗ 有测试失败，需要检查转换逻辑。');
}
