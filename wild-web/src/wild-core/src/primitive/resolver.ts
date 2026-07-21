/**
 * 空间关系解析层
 * 
 * 核心模块。接收展开后的构件列表，自动推导和修正几何坐标，
 * 确保建筑结构在空间上正确连接。
 */

import type { GeometryElement, SpatialIndex, Vec3 } from './types';

export function resolveSpatialRelations(elements: GeometryElement[]): GeometryElement[] {
  const index = buildSpatialIndex(elements);

  resolveWallJoints(elements, index);
  resolveBeamSupports(elements, index);
  resolveRoofBoundary(elements, index);
  resolveFloorRegions(elements, index);
  resolveStairSteps(elements);
  resolveColumnOffsets(elements, index);
  resolveOpenings(elements, index);

  return elements;
}

// ─── 空间索引 ────────────────────────────────
function buildSpatialIndex(elements: GeometryElement[]): SpatialIndex {
  const byId = new Map<string, GeometryElement>();
  const grid = new Map<string, Set<string>>();
  const cellSize = 5.0;

  for (const el of elements) {
    byId.set(el.id, el);
    const cell = getCellForElement(el, cellSize);
    if (!grid.has(cell)) grid.set(cell, new Set());
    grid.get(cell)!.add(el.id);
  }

  return { byId, grid, cellSize };
}

function getCellForElement(el: GeometryElement, cellSize: number): string {
  let x = 0, z = 0;
  switch (el.type) {
    case 'wall': case 'floor': case 'beam': case 'stair':
      x = Math.floor(el.from[0] / cellSize);
      z = Math.floor(el.from[2] / cellSize);
      break;
    case 'column':
      x = Math.floor(el.base[0] / cellSize);
      z = Math.floor(el.base[2] / cellSize);
      break;
    case 'roof': case 'furniture': case 'dense_brick': case 'body':
      x = Math.floor((el as any).position?.[0] / cellSize) || 0;
      z = Math.floor((el as any).position?.[2] / cellSize) || 0;
      break;
    case 'opening':
      x = Math.floor(el.from[0] / cellSize);
      z = Math.floor(el.from[2] / cellSize);
      break;
    default:
      break;
  }
  return `${x},${z}`;
}

// ─── 墙角连接 ────────────────────────────────
function resolveWallJoints(elements: GeometryElement[], index: SpatialIndex): void {
  const walls = elements.filter(e => e.type === 'wall') as any[];
  for (const wall of walls) {
    const fromKey = `${wall.from[0]},${wall.from[2]}`;
    const toKey = `${wall.to[0]},${wall.to[2]}`;
    const neighbors = findNeighborWalls(wall, walls);
    for (const neighbor of neighbors) {
      adjustWallJoint(wall, neighbor);
    }
  }
}

function findNeighborWalls(wall: any, walls: any[]): any[] {
  const tolerance = 0.01;
  return walls.filter(other => {
    if (other.id === wall.id) return false;
    const distFF = distance2D(other.from, wall.from);
    const distFT = distance2D(other.from, wall.to);
    const distTF = distance2D(other.to, wall.from);
    const distTT = distance2D(other.to, wall.to);
    return distFF < tolerance || distFT < tolerance || distTF < tolerance || distTT < tolerance;
  });
}

function adjustWallJoint(wall: any, neighbor: any): void {
  const dFF = distance2D(wall.from, neighbor.from);
  const dFT = distance2D(wall.from, neighbor.to);
  const dTF = distance2D(wall.to, neighbor.from);
  const dTT = distance2D(wall.to, neighbor.to);
  const tolerance = 0.01;

  // 墙角斜接：只合并 XZ，Y 各自保留（fromY 是墙底、toY 是墙顶，不能混用）
  if (dFF < tolerance) {
    joinXZ(wall.from, neighbor.from);
  } else if (dFT < tolerance) {
    joinXZ(wall.from, neighbor.to);
  } else if (dTF < tolerance) {
    joinXZ(wall.to, neighbor.from);
  } else if (dTT < tolerance) {
    joinXZ(wall.to, neighbor.to);
  }
}

// ─── 梁定位 ────────────────────────────────
function resolveBeamSupports(elements: GeometryElement[], index: SpatialIndex): void {
  const beams = elements.filter(e => e.type === 'beam') as any[];
  const columns = elements.filter(e => e.type === 'column') as any[];

  for (const beam of beams) {
    for (const col of columns) {
      const beamFrom = beam.from;
      const beamTo = beam.to;
      const colTop: Vec3 = [
        col.base[0],
        col.base[1] + col.height,
        col.base[2]
      ];
      const distFrom = distance2D(beamFrom, colTop);
      const distTo = distance2D(beamTo, colTop);
      const tolerance = col.bottomRadius + 0.05;

      if (distFrom < tolerance) {
        beam.from = [colTop[0], colTop[1], colTop[2]];
      }
      if (distTo < tolerance) {
        beam.to = [colTop[0], colTop[1], colTop[2]];
      }
    }
  }
}

// ─── 屋顶适配 ────────────────────────────────
function resolveRoofBoundary(elements: GeometryElement[], index: SpatialIndex): void {
  const roofs = elements.filter(e => e.type === 'roof') as any[];
  const walls = elements.filter(e => e.type === 'wall') as any[];

  for (const roof of roofs) {
    if (walls.length < 3) continue;

    // 计算所有墙的最大高度，用于过滤栏杆/装饰矮墙
    // 矮墙（如阳台栏杆 < 1.5m）不应参与屋顶包围盒计算，否则会导致屋顶偏移
    let maxWallHeight = 0;
    for (const wall of walls) {
      const h = Math.abs(wall.to[1] - wall.from[1]);
      if (h > maxWallHeight) maxWallHeight = h;
    }

    // 只取高度 >= 最大高度 50% 的结构墙，过滤栏杆等矮墙
    const heightThreshold = maxWallHeight * 0.5;
    const structuralWalls = walls.filter(w =>
      Math.abs(w.to[1] - w.from[1]) >= heightThreshold
    );

    // 过滤后墙太少（如凉亭只有矮墙），退回使用全部墙
    const effectiveWalls = structuralWalls.length >= 3 ? structuralWalls : walls;

    let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity;
    let maxY = -Infinity;

    for (const wall of effectiveWalls) {
      minX = Math.min(minX, wall.from[0], wall.to[0]);
      maxX = Math.max(maxX, wall.from[0], wall.to[0]);
      minZ = Math.min(minZ, wall.from[2], wall.to[2]);
      maxZ = Math.max(maxZ, wall.from[2], wall.to[2]);
      maxY = Math.max(maxY, wall.from[1], wall.to[1]);
    }

    roof.span = Math.max(roof.span, maxX - minX + 1.0);
    roof.depth = Math.max(roof.depth, maxZ - minZ + 1.0);
    const baseY = maxY;
    if (!(roof as any).position) {
      (roof as any).position = [(minX + maxX) / 2, baseY, (minZ + maxZ) / 2];
    }
  }
}

// ─── 地板填充 ────────────────────────────────
function resolveFloorRegions(elements: GeometryElement[], index: SpatialIndex): void {
  const existingFloors = elements.filter(e => e.type === 'floor') as any[];
  if (existingFloors.length > 0) return;

  const walls = elements.filter(e => e.type === 'wall') as any[];
  if (walls.length < 3) return;

  let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity;
  let baseY = Infinity;
  for (const wall of walls) {
    minX = Math.min(minX, wall.from[0], wall.to[0]);
    maxX = Math.max(maxX, wall.from[0], wall.to[0]);
    minZ = Math.min(minZ, wall.from[2], wall.to[2]);
    maxZ = Math.max(maxZ, wall.from[2], wall.to[2]);
    baseY = Math.min(baseY, wall.from[1], wall.to[1]);
  }

  const newFloor: any = {
    type: 'floor',
    id: `auto_floor_${elements.length}`,
    from: [minX, baseY, minZ],
    to: [maxX, baseY, maxZ],
    thickness: 0.2,
    material: 'default'
  };
  elements.push(newFloor);
}

// ─── 楼梯步数计算 ─────────────────────────────
function resolveStairSteps(elements: GeometryElement[]): void {
  const stairs = elements.filter(e => e.type === 'stair') as any[];
  for (const stair of stairs) {
    if (stair.stepCount && stair.stepCount > 0) continue;

    const totalRise = stair.to[1] - stair.from[1];
    // 欧几里得水平距离（之前是 Manhattan 距离，对角线楼梯会偏大 ~41%）
    const totalDepth = Math.sqrt(
      Math.pow(stair.to[0] - stair.from[0], 2) + Math.pow(stair.to[2] - stair.from[2], 2)
    );

    const targetStepHeight = 0.18;
    const targetStepDepth = 0.30;

    // 总升幅太小：单步即可
    if (totalRise <= 0.25 || totalDepth <= 0.25) {
      stair.stepCount = 1;
      stair.stepHeight = Math.max(0.05, totalRise);
      stair.stepDepth = Math.max(0.05, totalDepth);
      continue;
    }

    // 从步高和步深两个维度分别估算步数，取平均以平衡二者
    const countByRise = Math.max(1, Math.round(totalRise / targetStepHeight));
    const countByDepth = Math.max(1, Math.round(totalDepth / targetStepDepth));
    let bestCount = Math.round((countByRise + countByDepth) / 2);
    if (bestCount < 1) bestCount = 1;

    // stepHeight * count == totalRise, stepDepth * count == totalDepth
    // 不 clamp 单个值——保持这个恒等式，踏步尺寸与间距始终一致
    // 否则 stair builder 中 step box 尺寸与 step spacing 脱节，产生重叠/缝隙
    stair.stepCount = bestCount;
    stair.stepHeight = totalRise / bestCount;
    stair.stepDepth = totalDepth / bestCount;
  }
}

// ─── 柱网偏移 ────────────────────────────────
function resolveColumnOffsets(elements: GeometryElement[], index: SpatialIndex): void {
  const columns = elements.filter(e => e.type === 'column') as any[];
  const walls = elements.filter(e => e.type === 'wall') as any[];

  for (const col of columns) {
    for (const wall of walls) {
      const wx = wall.from[0], wz = wall.from[2];
      const dx = wall.to[0] - wx, dz = wall.to[2] - wz;
      const len = Math.sqrt(dx * dx + dz * dz);
      if (len < 0.001) continue;

      // 单位方向 + 法线（沿墙看向 to 时，右侧为外）
      const dirLen = 1 / len;
      const nx = -dz * dirLen, nz = dx * dirLen; // 法线（右手方向）

      // 柱子 base 到墙中心线的有符号垂直距离
      const perpDist = ((col.base[0] - wx) * nx + (col.base[2] - wz) * nz);

      // 仅当柱子中心在墙体厚度范围内（嵌入墙内）时才对齐到中心线
      // 之前用 wallHalfThick + colR 容差过大，会把门廊柱等有意 offset 的柱子吸入墙内
      const wallHalfThick = wall.thickness / 2;
      if (Math.abs(perpDist) > wallHalfThick + 0.02) continue;

      // 检查柱子 XZ 投影是否在墙体线段范围内
      const alongT = ((col.base[0] - wx) * dx + (col.base[2] - wz) * dz) / (len * len);
      if (alongT < -0.1 || alongT > 1.1) continue;

      // 在墙内：将柱子中心对齐到墙体中心线
      const offset = perpDist; // 正值表示偏外侧，负值表示偏内侧
      col.base[0] -= offset * nx;
      col.base[2] -= offset * nz;
      break; // 一个柱子只需适配一面墙
    }
  }
}

// ─── 开口定位 ───────────────────────────────
/**
 * 根据父墙体，在墙体上标记开孔信息，并计算开口世界坐标。
 *
 * opening.from 格式：[沿墙距离, 开口底部世界Y坐标, 法向偏移]
 *   - from[0]: 从墙起点沿墙方向的距离（米），不是世界X/Z坐标
 *   - from[1]: 开口底部的世界Y坐标（米）
 *   - from[2]: 法向偏移（米），通常为0（在墙面中心线上）
 *
 * 直线墙的沿墙距离计算：distance = dot(opening_world_pos - wall_from, wall_direction)
 */
function resolveOpenings(elements: GeometryElement[], index: SpatialIndex): void {
  for (const el of elements) {
    if (el.type !== 'opening') continue;
    const opening = el as any;
    const wall = index.byId.get(opening.parentWall);
    if (!wall || wall.type !== 'wall') continue;

    const wallFrom = (wall as any).from;
    const wallTo = (wall as any).to;
    const wallCurve = (wall as any).curve;

    if (wallCurve && wallCurve.type === 'arc') {
      // 弧形墙体：opening.from[0] 已经是弧长，不需要转换
      if (!wall._cutouts) wall._cutouts = [];
      wall._cutouts.push({
        localX: opening.from[0],
        localY: opening.from[1],  // 弧形墙：from[1] 是相对墙底偏移
        localW: opening.width,
        localH: opening.height,
      });

      // 弧形墙体：从弧参数计算门的准确世界位置
      const center = wallCurve.center;
      const radius = Math.sqrt((wallFrom[0] - center[0]) ** 2 + (wallFrom[2] - center[2]) ** 2);
      const startRad = Math.atan2(wallFrom[2] - center[2], wallFrom[0] - center[0]);
      const angle = startRad + opening.from[0] / radius;
      const nx = Math.cos(angle), nz = Math.sin(angle); // 径向（法线方向）
      const offset = opening.from[2] || 0;
      const worldX = center[0] + (radius + offset) * nx;
      const worldZ = center[2] + (radius + offset) * nz;
      opening._worldPos = [worldX, wallFrom[1] + opening.from[1], worldZ];
      opening._wallRotation = Math.atan2(nx, nz);
    } else {
      // ─── 直线墙 ─────────────────────────────
      // opening.from[0] = 沿墙距离（局部坐标）
      // opening.from[1] = 开口底部的世界Y坐标
      // opening.from[2] = 法向偏移（通常为0）

      const wallDx = wallTo[0] - wallFrom[0];
      const wallDz = wallTo[2] - wallFrom[2];
      const wallLen = Math.sqrt(wallDx * wallDx + wallDz * wallDz);
      if (wallLen < 0.001) continue;

      // 墙方向单位向量
      const dirX = wallDx / wallLen;
      const dirZ = wallDz / wallLen;
      // 墙法线方向（右手法则：沿墙方向看时右侧为法线正方向）
      const nx = -dirZ, nz = dirX;

      // 1. 在墙体上存储开孔信息（墙体生成器 boxWithHoles 使用局部坐标）
      //    from[0] 已经是沿墙距离，from[1] 是世界Y需要转为相对墙底偏移
      const localX = opening.from[0];        // 沿墙距离（局部坐标）
      const localY = opening.from[1] - wallFrom[1]; // 开口底部相对墙底高度

      if (!wall._cutouts) wall._cutouts = [];
      wall._cutouts.push({
        localX: localX,
        localY: localY,
        localW: opening.width,
        localH: opening.height,
      });

      // 2. 计算开口实体的世界位置
      //    世界位置 = 墙起点 + 沿墙投影 + 法向偏移
      const worldX = wallFrom[0] + localX * dirX + opening.from[2] * nx;
      const worldZ = wallFrom[2] + localX * dirZ + opening.from[2] * nz;
      //    from[1] 是世界Y坐标（开口底部），直接使用
      opening._worldPos = [worldX, opening.from[1], worldZ];
      opening._wallRotation = Math.atan2(nx, nz);
    }
  }
}

// ─── 辅助函数 ────────────────────────────────
function distance2D(a: Vec3, b: Vec3): number {
  const dx = a[0] - b[0];
  const dz = a[2] - b[2];
  return Math.sqrt(dx * dx + dz * dz);
}

function averageVec3(a: Vec3, b: Vec3): Vec3 {
  return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2];
}

/** 只平均 XZ 坐标，Y 各自保留（用于墙角连接） */
function joinXZ(a: Vec3, b: Vec3): void {
  const mx = (a[0] + b[0]) / 2;
  const mz = (a[2] + b[2]) / 2;
  a[0] = mx; a[2] = mz;
  b[0] = mx; b[2] = mz;
}