#!/usr/bin/env node
/**
 * 验证蓝图修复脚本
 * 
 * 检查修复后的蓝图文件是否符合几何约束
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

function loadBlueprint(filename) {
  const filepath = path.join(__dirname, 'lantu', filename);
  const content = fs.readFileSync(filepath, 'utf-8');
  return JSON.parse(content);
}

function validateWallCorners(blueprint) {
  const walls = blueprint.geometry.elements.filter(e => e.type === 'wall');
  const issues = [];
  const tolerance = 0.01;
  
  for (let i = 0; i < walls.length; i++) {
    for (let j = i + 1; j < walls.length; j++) {
      const w1 = walls[i];
      const w2 = walls[j];
      
      // 检查端点距离
      const distances = [
        { type: 'from-from', dist: distance3D(w1.from, w2.from) },
        { type: 'from-to', dist: distance3D(w1.from, w2.to) },
        { type: 'to-from', dist: distance3D(w1.to, w2.from) },
        { type: 'to-to', dist: distance3D(w1.to, w2.to) }
      ];
      
      for (const d of distances) {
        if (d.dist > tolerance && d.dist < 0.5) {
          issues.push({
            severity: 'warning',
            message: `墙角gap: ${w1.id} - ${w2.id}, ${d.type}, gap=${d.dist.toFixed(3)}m`
          });
        }
      }
    }
  }
  
  return issues;
}

function validateCircularWallOpenings(blueprint) {
  const issues = [];
  const walls = blueprint.geometry.elements.filter(e => e.type === 'wall');
  const openings = blueprint.geometry.elements.filter(e => e.type === 'opening');
  
  for (const opening of openings) {
    const wall = walls.find(w => w.id === opening.parentWall);
    if (!wall || !wall.curve || wall.curve.type !== 'arc') continue;
    
    const center = wall.curve.center;
    const radius = Math.sqrt(
      Math.pow(wall.from[0] - center[0], 2) + 
      Math.pow(wall.from[2] - center[2], 2)
    );
    const circumference = 2 * Math.PI * radius;
    const sweep = wall.curve.sweep || 360;
    const arcLength = circumference * (sweep / 360);
    
    const openingPos = opening.from[0];
    if (openingPos < 0 || openingPos > arcLength) {
      issues.push({
        severity: 'error',
        message: `开口超出墙体范围: ${opening.id}, pos=${openingPos.toFixed(2)}, arcLength=${arcLength.toFixed(2)}`
      });
    }
    
    // 检查是否均匀分布（如果有多个门）
    const siblingOpenings = openings.filter(o => o.parentWall === opening.parentWall);
    if (siblingOpenings.length === 4) {
      const expectedInterval = arcLength / 4;
      const angles = siblingOpenings.map(o => (o.from[0] / arcLength) * 360);
      const sortedAngles = angles.sort((a, b) => a - b);
      
      for (let i = 0; i < sortedAngles.length; i++) {
        const expected = i * 90;
        const actual = sortedAngles[i];
        const error = Math.abs(actual - expected);
        
        if (error > 5) {
          issues.push({
            severity: 'warning',
            message: `开口角度不均匀: 预期${expected}°, 实际${actual.toFixed(1)}°, 误差${error.toFixed(1)}°`
          });
        }
      }
    }
  }
  
  return issues;
}

function distance3D(p1, p2) {
  return Math.sqrt(
    Math.pow(p2[0] - p1[0], 2) +
    Math.pow(p2[1] - p1[1], 2) +
    Math.pow(p2[2] - p1[2], 2)
  );
}

function validateBlueprint(name, filename) {
  console.log(`\n=== 验证 ${name} (${filename}) ===`);
  
  try {
    const blueprint = loadBlueprint(filename);
    console.log(`✓ 蓝图加载成功`);
    console.log(`  元素数量: ${blueprint.geometry.elements.length}`);
    
    const wallIssues = validateWallCorners(blueprint);
    const openingIssues = validateCircularWallOpenings(blueprint);
    
    const allIssues = [...wallIssues, ...openingIssues];
    const errors = allIssues.filter(i => i.severity === 'error');
    const warnings = allIssues.filter(i => i.severity === 'warning');
    
    if (errors.length === 0 && warnings.length === 0) {
      console.log(`✓ 没有发现问题`);
    } else {
      if (errors.length > 0) {
        console.log(`\n❌ 错误 (${errors.length}):`);
        errors.forEach(e => console.log(`  - ${e.message}`));
      }
      if (warnings.length > 0) {
        console.log(`\n⚠️  警告 (${warnings.length}):`);
        warnings.forEach(w => console.log(`  - ${w.message}`));
      }
    }
    
    return { errors: errors.length, warnings: warnings.length };
    
  } catch (error) {
    console.log(`❌ 验证失败: ${error.message}`);
    return { errors: 1, warnings: 0 };
  }
}

// 主函数
console.log('蓝图修复验证工具');
console.log('================\n');

const results = {
  cabin_v1: validateBlueprint('小木屋 (正常)', 'cabin_v1.wild'),
  bieshu: validateBlueprint('别墅 (已修复)', 'bieshu.wild'),
  tiantan: validateBlueprint('天坛 (已修复)', 'tiantan.wild')
};

console.log('\n=== 总结 ===');
let totalErrors = 0;
let totalWarnings = 0;

for (const [name, result] of Object.entries(results)) {
  const status = result.errors === 0 ? '✓' : '❌';
  console.log(`${status} ${name}: ${result.errors} 错误, ${result.warnings} 警告`);
  totalErrors += result.errors;
  totalWarnings += result.warnings;
}

console.log(`\n总计: ${totalErrors} 错误, ${totalWarnings} 警告`);

if (totalErrors === 0) {
  console.log('\n✅ 所有蓝图验证通过！');
  process.exit(0);
} else {
  console.log('\n❌ 存在错误，需要修复');
  process.exit(1);
}
