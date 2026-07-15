/**

 * 原语引擎入口 — reconstructEntity

 * 

 * 将 .wild 蓝图编译为可渲染的几何体与材质参数。

 * 这是引擎的唯一公开入口。

 */
import type { Blueprint, ReconstructedEntity, AABB, MeshData, MaterialParams } from './types';

import { expandTemplates, expandPlacements } from './expander';

import { resolveSpatialRelations } from './resolver';

import { buildWall, buildColumn, buildFloor, buildBeam, buildRoof, buildOpening, buildStair, buildFurniture, buildDenseBrick, buildBody } from './geometry';

import { applyMaterials } from './materials/apply';



export { parseBlueprint } from './parser';
export type { Blueprint, ReconstructedEntity, MeshData } from './types';



// ─── 世界空间包围盒计算 ─────────────────────────────

/** 对网格的所有顶点应用 TRS 变换，返回世界空间包围盒 */

function computeWorldAABB(meshes: MeshData[]): AABB {

  let minX = Infinity, minY = Infinity, minZ = Infinity;

  let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;

  for (const m of meshes) {
    const { position, rotation, scale } = m.transform;
    const [sx, sy, sz] = scale;
    const [px, py, pz] = position;

    // 欧拉角 XYZ 顺序 → 旋转矩阵
    const rx = rotation[0], ry = rotation[1], rz = rotation[2];
    const cx = Math.cos(rx), sx_ = Math.sin(rx);
    const cy = Math.cos(ry), sy_ = Math.sin(ry);
    const cz = Math.cos(rz), sz_ = Math.sin(rz);

    // Ry * Rx * Rz (Three.js 默认 XYZ 顺序)
    const m00 = cy * cz;
    const m01 = -cy * sz_;
    const m02 = sy_;
    const m10 = sx_ * sy_ * cz + cx * sz_;
    const m11 = -sx_ * sy_ * sz_ + cx * cz;
    const m12 = -sx_ * cy;
    const m20 = -cx * sy_ * cz + sx_ * sz_;
    const m21 = cx * sy_ * sz_ + sx_ * cz;
    const m22 = cx * cy;

    const verts = m.geometry;
    for (let i = 0; i < verts.length; i += 3) {
      // 先缩放
      let x = verts[i] * sx;
      let y = verts[i + 1] * sy;
      let z = verts[i + 2] * sz;
      // 再旋转
      const wx = m00 * x + m01 * y + m02 * z + px;
      const wy = m10 * x + m11 * y + m12 * z + py;
      const wz = m20 * x + m21 * y + m22 * z + pz;

      if (wx < minX) minX = wx;
      if (wy < minY) minY = wy;
      if (wz < minZ) minZ = wz;
      if (wx > maxX) maxX = wx;
      if (wy > maxY) maxY = wy;
      if (wz > maxZ) maxZ = wz;
    }

  }

  return { min: [minX, minY, minZ], max: [maxX, maxY, maxZ] };

}

/** 简单 3D 噪声（用于程序化纹理）*/
function proceduralNoise(x: number, y: number, z: number): number {
  const d = x * 127.1 + y * 311.7 + z * 74.7;
  const frac = Math.abs(Math.sin(d) * 43758.5453);
  return frac - Math.floor(frac);
}

/** 逐顶点烘焙程序化纹理：基于世界坐标噪声，为每个顶点生成颜色变化 */
function bakeProceduralColors(meshes: MeshData[], materialParams: MaterialParams[]): void {
  for (let mi = 0; mi < meshes.length; mi++) {
    const m = meshes[mi];
    const mp = materialParams[mi];
    if (!mp) continue;
    // 已有 surface 系统着色的网格（stone_block），用 baseColor 和 mortarColor 着色
    if (m.vertexColors) {
      const bc = mp.baseColor;
      const mc = m.patternMortarColor ?? [bc[0] * 0.3, bc[1] * 0.28, bc[2] * 0.25];
      const colors = m.vertexColors;
      for (let i = 0; i < colors.length; i += 3) {
        const isStone = colors[i] > 0.5; // binary mask: 1=stone, 0=joint
        if (isStone) {
          colors[i] = bc[0]; colors[i + 1] = bc[1]; colors[i + 2] = bc[2];
        } else {
          colors[i] = mc[0]; colors[i + 1] = mc[1]; colors[i + 2] = mc[2];
        }
      }
      continue;
    }

    // 读取 grain 参数
    const grainFx = mp.effects?.find((e: any) => e.type === 'grain') as any;
    const grainIntensity = grainFx?.intensity ?? 0.25;
    const grainScale = grainFx?.scale ?? 0.04;
    const { position, rotation, scale } = m.transform;
    const [sx, sy, sz] = scale;
    const [px, py, pz] = position;
    // 旋转矩阵（同 computeWorldAABB）
    const rx = rotation[0], ry = rotation[1], rz = rotation[2];
    const cx = Math.cos(rx), sx_ = Math.sin(rx);
    const cy = Math.cos(ry), sy_ = Math.sin(ry);
    const cz = Math.cos(rz), sz_ = Math.sin(rz);
    const m00 = cy * cz, m01 = -cy * sz_, m02 = sy_;
    const m10 = sx_ * sy_ * cz + cx * sz_, m11 = -sx_ * sy_ * sz_ + cx * cz, m12 = -sx_ * cy;
    const m20 = -cx * sy_ * cz + sx_ * sz_, m21 = cx * sy_ * sz_ + sx_ * cz, m22 = cx * cy;
    const verts = m.geometry;
    const colors = new Float32Array(verts.length);
    const hasMoss = mp.effects?.some((e: any) => e.type === 'moss');
    const moss = hasMoss ? mp.effects!.find((e: any) => e.type === 'moss') as any : null;

    // 计算网格的 Y 范围（用于高度渐变）
    let minWy = Infinity, maxWy = -Infinity;

    for (let i = 0; i < verts.length; i += 3) {
      let x = verts[i] * sx, y = verts[i + 1] * sy, z = verts[i + 2] * sz;
      const wy = m10 * x + m11 * y + m12 * z + py;
      if (wy < minWy) minWy = wy;
      if (wy > maxWy) maxWy = wy;
    }
    const yRange = Math.max(maxWy - minWy, 0.01);

    for (let i = 0; i < verts.length; i += 3) {
      let x = verts[i] * sx, y = verts[i + 1] * sy, z = verts[i + 2] * sz;
      const wx = m00 * x + m01 * y + m02 * z + px;
      const wy = m10 * x + m11 * y + m12 * z + py;
      const wz = m20 * x + m21 * y + m22 * z + pz;

      // 双频噪声（使用 grain 参数控制）
      const freq = 1 / Math.max(grainScale, 0.001);
      const n1 = proceduralNoise(wx * freq, wy * freq, wz * freq);
      const n2 = proceduralNoise(wx * freq * 2, wy * freq * 2, wz * freq * 2);
      const noise = (n1 * 0.6 + n2 * 0.4);

      // 高度渐变因子 (0=底 1=顶)
      const yf = (wy - minWy) / yRange;

      const bc = mp.baseColor;

      // 基础噪声调制 → 由 grainIntensity 控制幅度
      const variation = (noise - 0.5) * grainIntensity;
      let r = Math.max(0, Math.min(1, bc[0] + variation));
      let g = Math.max(0, Math.min(1, bc[1] + variation));
      let b = Math.max(0, Math.min(1, bc[2] + variation));

      // 高度渐变：底部暗、顶部亮
      const hf = (yf - 0.5) * 0.15;
      r = Math.max(0, Math.min(1, r + hf));
      g = Math.max(0, Math.min(1, g + hf));
      b = Math.max(0, Math.min(1, b + hf));

      // 苔藓：base_up 模式（底部密集）
      if (moss && moss.pattern === 'base_up') {
        const mossProb = (1 - yf) * moss.coverage * 2.5;
        if (noise < mossProb) {
          const blend = (mossProb - noise) / mossProb;
          r = r * (1 - blend) + moss.mossColor[0] * blend;
          g = g * (1 - blend) + moss.mossColor[1] * blend;
          b = b * (1 - blend) + moss.mossColor[2] * blend;
        }
      } else if (moss && moss.pattern === 'patchy') {
        // 随机斑块
        if (noise > 1 - moss.coverage * 1.2) {
          const blend = Math.min(1, (noise - (1 - moss.coverage * 1.2)) * 5);
          r = r * (1 - blend) + moss.mossColor[0] * blend;
          g = g * (1 - blend) + moss.mossColor[1] * blend;
          b = b * (1 - blend) + moss.mossColor[2] * blend;
        }
      }
      colors[i] = r;
      colors[i + 1] = g;
      colors[i + 2] = b;
    }
    m.vertexColors = colors;
  }
}



// ─── 主入口 ───────────────────────────────────────
export async function reconstructEntity(bp: Blueprint): Promise<ReconstructedEntity> {
  // 1. 展开模板
  let elements = expandTemplates(bp);

  // 2. 空间关系解析
  elements = resolveSpatialRelations(elements);

  // 2.5 展开 placement（此时父构件已定位）
  expandPlacements(bp, elements);


  // 收集 physics constraints 的目标构件 ID（用于标记交互）
  const constrainedTargets = new Set<string>();
  if (bp.behaviors?.physics?.constraints) {
    for (const c of bp.behaviors.physics.constraints) {
      constrainedTargets.add(c.target);

    }
  }

  // 3. 同步重建每种构件的几何体 + 绑定 elementId
  const rawEntries: { elId: string; meshes: MeshData[] }[] = [];

  for (const el of elements) {
    let meshes: MeshData[];

    switch (el.type) {
      case 'wall': meshes = buildWall(el); break;
      case 'floor': meshes = buildFloor(el); break;
      case 'column': meshes = buildColumn(el); break;
      case 'beam': meshes = buildBeam(el); break;
      case 'roof': meshes = buildRoof(el); break;
      case 'opening': meshes = buildOpening(el); break;
      case 'stair': meshes = buildStair(el); break;
      case 'furniture': meshes = buildFurniture(el); break;
      case 'dense_brick': meshes = buildDenseBrick(el); break;
      case 'body': meshes = buildBody(el); break;
      default: console.warn(`Unknown element type: ${(el as any).type}`); continue;
    }

    // 为每个网格绑定 elementId 和 interactive 标记
    const isInteractive = constrainedTargets.has(el.id);

    for (const m of meshes) {
      m.elementId = el.id;
      if (isInteractive) m.interactive = true;
    }

    rawEntries.push({ elId: el.id, meshes });

  }

  const rawMeshes = rawEntries.flatMap(e => e.meshes);

  // 3.5 合并瓦片网格（materialRef=roof_tile）。
  // 网格瓦片（_tileGrid）已由 buildTileGrid 合并为一个世界坐标网格，
  // 直接放行；单个瓦片需要合并为一个大网格以减少 draw call。
  const tileVerts: number[] = [], tileIdx: number[] = [], tileCols: number[] = [], tileNorms: number[] = [];
  let tileMortarColor: [number, number, number] | undefined;

  const otherMeshes: MeshData[] = [];

  for (const m of rawMeshes) {
    if (m.materialRef === 'roof_tile' && m.transform.position) {
      const [px, py, pz] = m.transform.position;

      // 若已经在世界坐标中（批处理合并的网格），直接保留
      if (px === 0 && py === 0 && pz === 0 && m.geometry.length > 1000) {
        otherMeshes.push(m);
        continue;
      }

      const base = tileVerts.length / 3;

      for (let i = 0; i < m.geometry.length; i += 3) {
        tileVerts.push(m.geometry[i] + px, m.geometry[i + 1] + py, m.geometry[i + 2] + pz);
      }

      for (let i = 0; i < m.indices!.length; i++) tileIdx.push(m.indices![i] + base);
      if (m.vertexColors) for (let i = 0; i < m.vertexColors.length; i++) tileCols.push(m.vertexColors[i]);
      if (m.normals) for (let i = 0; i < m.normals.length; i++) tileNorms.push(m.normals[i]);
      if (m.patternMortarColor && !tileMortarColor) tileMortarColor = m.patternMortarColor;
    } else {
      otherMeshes.push(m);
    }
  }

  if (tileVerts.length > 0) {
    otherMeshes.push({
      geometry: new Float32Array(tileVerts),
      indices: new Uint32Array(tileIdx),
      normals: tileNorms.length > 0 ? new Float32Array(tileNorms) : undefined,
      vertexColors: tileCols.length > 0 ? new Float32Array(tileCols) : undefined,
      transform: { position: [0, 0, 0], rotation: [0, 0, 0], scale: [1, 1, 1] },
      materialRef: 'roof_tile',
      patternMortarColor: tileMortarColor,
    });
  }
  const meshes = otherMeshes;

  // 4. 材质应用（效果层烘焙：调色类）
  const materialParams = applyMaterials(bp.materials || {}, meshes);
  // 5. 计算世界空间包围盒
  const boundingBox = computeWorldAABB(meshes);
  // 6. 烘焙逐顶点程序化纹理颜色
  bakeProceduralColors(meshes, materialParams);
  return {
    meshes,
    materialParams,
    boundingBox,
    physics: bp.behaviors?.physics,
    scripts: bp.behaviors?.scripts,
    animation: bp.behaviors?.animation
  };

}

