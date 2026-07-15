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
    let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity;
    let maxY = -Infinity;

    for (const wall of walls) {
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
    const totalDepth = Math.abs(stair.to[0] - stair.from[0]) + Math.abs(stair.to[2] - stair.from[2]);

    const targetStepHeight = 0.18;
    const targetStepDepth = 0.30;
    const minStepHeight = 0.15;
    const maxStepHeight = 0.20;
    const minStepDepth = 0.26;
    const maxStepDepth = 0.35;

    let bestCount = Math.round(totalRise / targetStepHeight);
    if (bestCount < 1) bestCount = 1;

    let stepHeight = totalRise / bestCount;
    let stepDepth = totalDepth / bestCount;

    if (stepHeight < minStepHeight || stepHeight > maxStepHeight) {
      bestCount = Math.max(1, Math.round(totalRise / targetStepHeight));
      stepHeight = totalRise / bestCount;
      stepDepth = totalDepth / bestCount;
    }

    stepHeight = Math.max(minStepHeight, Math.min(maxStepHeight, stepHeight));
    stepDepth = Math.max(minStepDepth, Math.min(maxStepDepth, stepDepth));

    stair.stepCount = bestCount;
    stair.stepHeight = stepHeight;
    stair.stepDepth = stepDepth;
  }
}

// ─── 柱网偏移 ────────────────────────────────

function resolveColumnOffsets(elements: GeometryElement[], index: SpatialIndex): void {
  const columns = elements.filter(e => e.type === 'column') as any[];
  const walls = elements.filter(e => e.type === 'wall') as any[];

  for (const col of columns) {
    const colR = col.bottomRadius || 0.1;
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

      // 检查柱子是否在墙体的厚度范围内（含柱子半径容差）
      const wallHalfThick = wall.thickness / 2;
      if (Math.abs(perpDist) > wallHalfThick + colR) continue;

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

/** 根据父墙体，在墙体上标记开孔信息，并计算开口世界坐标 */
function resolveOpenings(elements: GeometryElement[], index: SpatialIndex): void {
  for (const el of elements) {
    if (el.type !== 'opening') continue;
    const opening = el as any;
    const wall = index.byId.get(opening.parentWall);
    if (!wall || wall.type !== 'wall') continue;

    const wallFrom = (wall as any).from;
    const wallTo = (wall as any).to;
    const wallCurve = (wall as any).curve;

    // 在墙体上存储开孔信息（墙体生成器切孔用）
    if (!wall._cutouts) wall._cutouts = [];
    wall._cutouts.push({
      localX: opening.from[0],
      localY: opening.from[1],
      localW: opening.width,
      localH: opening.height,
    });

    if (wallCurve && wallCurve.type === 'arc') {
      // 弧形墙体：从弧参数计算门的准确位置
      const center = wallCurve.center;
      const radius = Math.sqrt((wallFrom[0]-center[0])**2 + (wallFrom[2]-center[2])**2);
      const startRad = Math.atan2(wallFrom[2]-center[2], wallFrom[0]-center[0]);
      const angle = startRad + opening.from[0] / radius;
      const nx = Math.cos(angle), nz = Math.sin(angle); // 径向（法线方向）
      const offset = opening.from[2] || 0;
      const worldX = center[0] + (radius + offset) * nx;
      const worldZ = center[2] + (radius + offset) * nz;
      opening._worldPos = [worldX, wallFrom[1] + opening.from[1], worldZ];
      opening._wallRotation = Math.atan2(nx, nz);
    } else {
      // 直线墙体
      const wallDx = wallTo[0] - wallFrom[0];
      const wallDz = wallTo[2] - wallFrom[2];
      const len = Math.sqrt(wallDx * wallDx + wallDz * wallDz);
      if (len < 0.001) continue;
      const dirX = wallDx / len, dirZ = wallDz / len;
      const nx = -dirZ, nz = dirX;
      const worldX = wallFrom[0] + opening.from[0] * dirX + opening.from[2] * nx;
      const worldZ = wallFrom[2] + opening.from[0] * dirZ + opening.from[2] * nz;
      opening._worldPos = [worldX, wallFrom[1] + opening.from[1], worldZ];
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