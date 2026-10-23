import type { FurnitureParams, MeshData, Vec3 } from '../types';
import { indexTriList } from './mesh-helper';
import { createBoxGeometry } from './wall';
import { buildPrimitive } from './primitive';

/**
 * 家具几何：按 subtype 分派，再整体施加 position / rotation。
 *
 * 坐标语义（写进 KB 前必须一致）：
 * - 局部原点是**底面中心**：X/Z 以占地中心为 0，Y 以底面为 0（腿从 Y=0 起）；
 * - `position` 是底面锚点，`position[1]` 即家具底面世界 Y；
 * - `rotation` 是绕局部原点（底面中心）的欧拉角，因此转向不会把家具甩离落点，
 *   只是原地改朝向；
 * - 各 subtype 的"正面"由几何硬编码决定：chair / sofa 靠背在 **-Z** 侧，
 *   即正面朝 **+Z**。摆放时用 rotation[1] 把正面转向目标方向。
 */
export function buildFurniture(params: FurnitureParams): MeshData[] {
  const tileGrid = (params as any)._tileGrid;
  if (tileGrid) return [buildTileGrid(tileGrid, (params as any).material || 'roof_tile')];
  const { subtype, dimensions, material } = params;
  const { width, depth, height } = dimensions;
  const pos = params.position ?? [0, 0, 0];
  // 兜底：未走 normalizeBlueprintInput 的调用方可能还带着标量 rotation（度数），
  // 解构迭代会抛 "rotation is not iterable"，这里按“绕 Y 朝向角”语义救回。
  const rot = Array.isArray(params.rotation)
    ? params.rotation
    : typeof params.rotation === 'number' && Number.isFinite(params.rotation)
      ? ([0, (params.rotation * Math.PI) / 180, 0] as Vec3)
      : ([0, 0, 0] as Vec3);
  const ms = buildSubtype(subtype, width, depth, height, material || 'default');
  for (const m of ms) {
    const local = rotateEulerXYZ(m.transform.position, rot);
    m.transform.position = [pos[0] + local[0], pos[1] + local[1], pos[2] + local[2]];
    m.transform.rotation = [
      m.transform.rotation[0] + rot[0],
      m.transform.rotation[1] + rot[1],
      m.transform.rotation[2] + rot[2],
    ];
  }
  return ms;
}
function buildSubtype(s: string, w: number, d: number, h: number, mat: string): MeshData[] {
  switch (s) {
    case 'table': return buildTable(w, d, h, mat);
    case 'chair': return buildChair(w, d, h, mat);
    case 'sofa': return buildSofa(w, d, h, mat);
    case 'bookshelf': return buildBookshelf(w, d, h, mat);
    case 'bed': return buildBed(w, d, h, mat);
    case 'wardrobe': return buildWardrobe(w, d, h, mat);
    case 'nightstand': return buildNightstand(w, d, h, mat);
    case 'tv_cabinet': return buildTvCabinet(w, d, h, mat);
    case 'lamp': return buildLamp(w, d, h, mat);
    case 'tile': return [boxMesh(w, Math.max(h, 0.015), d, [0, Math.max(h, 0.015) / 2, 0], mat)];
    default: throw new Error(`Unsupported furniture subtype: ${s}`);
  }
}

interface TileGrid {
  bl: number[]; uAxis: number[]; vAxis: number[]; normal: number[];
  cols: number; rows: number; aTileW: number; aTileH: number;
  gapW: number; overlap: number; tileThickness: number; parentPos: number[];
  cellMaterials?: Record<string, string>;
  bpMaterials?: Record<string, any>;
}

function buildTileGrid(grid: TileGrid, mat: string): MeshData {
  const { bl, uAxis, vAxis, normal, cols, rows, aTileW, aTileH, gapW, overlap, tileThickness, parentPos } = grid;
  const uStep = aTileW + gapW;
  const vStep = aTileH - overlap;
  const verts: number[] = [], colsList: number[] = [], idxList: number[] = [];

  function addQuad(a: number[], b: number[], c: number[], d: number[], color: [number, number, number]) {
    const base = verts.length / 3;
    for (const p of [a, b, c, a, c, d]) { verts.push(p[0], p[1], p[2]); colsList.push(color[0], color[1], color[2]); }
    for (let k = 0; k < 6; k++) idxList.push(base + k);
  }

  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const u = c * uStep + aTileW / 2;
      const v = r * vStep + aTileH / 2;
      const cx = bl[0] + u*uAxis[0] + v*vAxis[0] + parentPos[0];
      const cy = bl[1] + u*uAxis[1] + v*vAxis[1] + parentPos[1];
      const cz = bl[2] + u*uAxis[2] + v*vAxis[2] + parentPos[2];

      const hw = aTileW / 2, hd = aTileH / 2;
      const p0 = [cx - hw*uAxis[0] - hd*vAxis[0], cy - hw*uAxis[1] - hd*vAxis[1], cz - hw*uAxis[2] - hd*vAxis[2]];
      const p1 = [cx + hw*uAxis[0] - hd*vAxis[0], cy + hw*uAxis[1] - hd*vAxis[1], cz + hw*uAxis[2] - hd*vAxis[2]];
      const p2 = [cx + hw*uAxis[0] + hd*vAxis[0], cy + hw*uAxis[1] + hd*vAxis[1], cz + hw*uAxis[2] + hd*vAxis[2]];
      const p3 = [cx - hw*uAxis[0] + hd*vAxis[0], cy - hw*uAxis[1] + hd*vAxis[1], cz - hw*uAxis[2] + hd*vAxis[2]];

      const baseOff = Math.max(tileThickness, 0.05);
      const offBtm = (p: number[]) => [p[0] + normal[0]*baseOff, p[1] + normal[1]*baseOff, p[2] + normal[2]*baseOff];
      const offTop = (p: number[]) => [p[0] + normal[0]*baseOff*0.25, p[1] + normal[1]*baseOff*0.25, p[2] + normal[2]*baseOff*0.25];
      const q0 = offBtm(p0), q1 = offBtm(p1);
      const q2 = offTop(p2), q3 = offTop(p3);

      const cellMatName = grid.cellMaterials?.[`${r}_${c}`];
      const cellMat = cellMatName ? grid.bpMaterials?.[cellMatName] : null;
      const crackI = cellMat?.effects?.find((e: any) => e.type === 'weathering')?.crackIntensity ?? 0;
      const cracked = crackI >= 0.7;

      if (!cracked) {
        addQuad(q0, q1, q2, q3, [1, 1, 1]);
        addQuad(q0, q1, p1, p0, [0, 0, 0]);
        addQuad(q2, q3, p3, p2, [0, 0, 0]);
        addQuad(q3, q0, p0, p3, [0, 0, 0]);
        addQuad(q1, q2, p2, p1, [0, 0, 0]);
      } else {
        // 真正的裂开：从中线切开，外边缘不动，只有中缝偏移
        const halfGap = 0.025;
        const lift = 0.02;
        const centerU = (a: number[], b: number[]) => [(a[0]+b[0])/2, (a[1]+b[1])/2, (a[2]+b[2])/2];
        const pMid0 = centerU(p0, p1);
        const pMid3 = centerU(p3, p2);
        const qMid0 = centerU(q0, q1);
        const qMid3 = centerU(q3, q2);
        // 左半：左边缘不动，中缝向左偏移 halfGap
        const p0L=p0, p1C=[pMid0[0]-uAxis[0]*halfGap,pMid0[1]-uAxis[1]*halfGap,pMid0[2]-uAxis[2]*halfGap];
        const p3L=p3, p2C=[pMid3[0]-uAxis[0]*halfGap,pMid3[1]-uAxis[1]*halfGap,pMid3[2]-uAxis[2]*halfGap];
        const q0L=q0, q1C=[qMid0[0]-uAxis[0]*halfGap,qMid0[1]-uAxis[1]*halfGap,qMid0[2]-uAxis[2]*halfGap];
        const q3L=q3, q2C=[qMid3[0]-uAxis[0]*halfGap,qMid3[1]-uAxis[1]*halfGap,qMid3[2]-uAxis[2]*halfGap];
        addQuad(q0L,q1C,q2C,q3L,[1,1,1]); addQuad(q0L,q1C,p1C,p0L,[0,0,0]);
        addQuad(q3L,q2C,p2C,p3L,[0,0,0]); addQuad(q3L,q0L,p0L,p3L,[0,0,0]);
        // 右半：右边缘不动，中缝向右偏移 halfGap + 抬升
        const p0C=[pMid0[0]+uAxis[0]*halfGap+normal[0]*lift,pMid0[1]+uAxis[1]*halfGap+normal[1]*lift,pMid0[2]+uAxis[2]*halfGap+normal[2]*lift];
        const p1R=p1, p2R=p2;
        const p3C=[pMid3[0]+uAxis[0]*halfGap+normal[0]*lift,pMid3[1]+uAxis[1]*halfGap+normal[1]*lift,pMid3[2]+uAxis[2]*halfGap+normal[2]*lift];
        const q0C=[qMid0[0]+uAxis[0]*halfGap+normal[0]*lift,qMid0[1]+uAxis[1]*halfGap+normal[1]*lift,qMid0[2]+uAxis[2]*halfGap+normal[2]*lift];
        const q1R=q1, q2R=q2;
        const q3C=[qMid3[0]+uAxis[0]*halfGap+normal[0]*lift,qMid3[1]+uAxis[1]*halfGap+normal[1]*lift,qMid3[2]+uAxis[2]*halfGap+normal[2]*lift];
        addQuad(q0C,q1R,q2R,q3C,[1,1,1]); addQuad(q0C,q1R,p1R,p0C,[0,0,0]);
        addQuad(q3C,q2R,p2R,p3C,[0,0,0]); addQuad(q1R,q2R,p2R,p1R,[0,0,0]);
      }
    }
  }

  const hasCM = grid.cellMaterials && Object.keys(grid.cellMaterials).length > 0;
  const refMat = hasCM ? Object.values(grid.cellMaterials!)[0] : mat;
  const ga = new Float32Array(verts), ia = new Uint32Array(idxList);
  return {
    geometry: ga, indices: ia, normals: computeTileNormals(verts, idxList),
    vertexColors: new Float32Array(colsList),
    transform: { position: [0, 0, 0], rotation: [0, 0, 0], scale: [1, 1, 1] },
    materialRef: refMat, patternMortarColor: [0.15, 0.1, 0.08],
  };
}

function computeTileNormals(verts: number[], idx: number[]): Float32Array {
  const n = new Float32Array(verts.length);
  for (let i = 0; i < idx.length; i += 3) {
    const ia = idx[i]*3, ib = idx[i+1]*3, ic = idx[i+2]*3;
    const ax=verts[ia],ay=verts[ia+1],az=verts[ia+2];
    const bx=verts[ib],by=verts[ib+1],bz=verts[ib+2];
    const cx=verts[ic],cy=verts[ic+1],cz=verts[ic+2];
    const ux=bx-ax,uy=by-ay,uz=bz-az,vx=cx-ax,vy=cy-ay,vz=cz-az;
    const nn=uy*vz-uz*vy,no=uz*vx-ux*vz,np=ux*vy-uy*vx;
    n[ia]+=nn;n[ia+1]+=no;n[ia+2]+=np; n[ib]+=nn;n[ib+1]+=no;n[ib+2]+=np; n[ic]+=nn;n[ic+1]+=no;n[ic+2]+=np;
  }
  for (let i = 0; i < n.length; i += 3) { const l = Math.sqrt(n[i]*n[i]+n[i+1]*n[i+1]+n[i+2]*n[i+2]); if(l>1e-6){n[i]/=l;n[i+1]/=l;n[i+2]/=l;} }
  return n;
}

function buildTable(w: number, d: number, h: number, mat: string): MeshData[] {
  const topThickness = Math.max(h * 0.1, 0.04);
  const legWidth = Math.max(Math.min(w, d) * 0.09, 0.035);
  const legHeight = Math.max(h - topThickness, 0.04);
  const insetX = Math.max(w / 2 - legWidth, 0);
  const insetZ = Math.max(d / 2 - legWidth, 0);
  return [
    boxMesh(w, topThickness, d, [0, h - topThickness / 2, 0], mat),
    ...cornerLegs(insetX, insetZ, legWidth, legHeight, mat),
  ];
}

function buildChair(w: number, d: number, h: number, mat: string): MeshData[] {
  const seatY = h * 0.45;
  const thickness = Math.max(h * 0.08, 0.035);
  const legWidth = Math.max(Math.min(w, d) * 0.1, 0.03);
  const insetX = Math.max(w / 2 - legWidth, 0);
  const insetZ = Math.max(d / 2 - legWidth, 0);
  return [
    boxMesh(w, thickness, d, [0, seatY, 0], mat),
    ...cornerLegs(insetX, insetZ, legWidth, seatY - thickness / 2, mat),
    boxMesh(w, h - seatY, thickness, [0, (h + seatY) / 2, -d / 2 + thickness / 2], mat),
  ];
}

function buildBookshelf(w: number, d: number, h: number, mat: string): MeshData[] {
  const board = Math.max(Math.min(w, d) * 0.07, 0.035);
  const result = [
    boxMesh(board, h, d, [-w / 2 + board / 2, h / 2, 0], mat),
    boxMesh(board, h, d, [w / 2 - board / 2, h / 2, 0], mat),
    boxMesh(w, board, d, [0, board / 2, 0], mat),
    boxMesh(w, board, d, [0, h - board / 2, 0], mat),
    boxMesh(w - board * 2, h - board * 2, board, [0, h / 2, -d / 2 + board / 2], mat),
  ];
  for (const ratio of [0.33, 0.66]) {
    result.push(boxMesh(w - board * 2, board, d, [0, h * ratio, 0], mat));
  }
  return result;
}

function buildSofa(w: number, d: number, h: number, mat: string): MeshData[] {
  // 底座 + 整宽靠背 + 两侧扶手 + 三块坐垫（全部盒体近似，靠背朝 -Z）
  const baseHeight = Math.max(h * 0.32, 0.18);
  const armWidth = Math.max(w * 0.12, 0.12);
  const innerWidth = Math.max(w - armWidth * 2, w * 0.3);
  const cushionHeight = Math.max(h * 0.14, 0.1);
  const cushionWidth = innerWidth / 3 * 0.94;
  const backDepth = Math.max(d * 0.22, 0.14);
  const cushions = [-1, 0, 1].map((slot) => boxMesh(
    cushionWidth, cushionHeight, Math.max(d * 0.72, 0.3),
    [slot * (innerWidth / 3), baseHeight + cushionHeight / 2, d * 0.04],
    mat,
  ));
  return [
    boxMesh(w, baseHeight, d, [0, baseHeight / 2, 0], mat),
    boxMesh(w, h, backDepth, [0, h / 2, -d / 2 + backDepth / 2], mat),
    boxMesh(armWidth, h * 0.72, d, [-(w / 2 - armWidth / 2), h * 0.36, 0], mat),
    boxMesh(armWidth, h * 0.72, d, [w / 2 - armWidth / 2, h * 0.36, 0], mat),
    ...cushions,
  ];
}

function buildWardrobe(w: number, d: number, h: number, mat: string): MeshData[] {
  // 柜体 + 两扇柜门（略凸出正面）+ 踢脚缩进
  const plinthHeight = Math.max(h * 0.04, 0.04);
  const doorGap = Math.max(w * 0.004, 0.005);
  const doorWidth = (w - doorGap * 3) / 2;
  const doorDepth = Math.max(d * 0.04, 0.02);
  const bodyHeight = h - plinthHeight;
  return [
    boxMesh(w * 0.96, plinthHeight, d * 0.92, [0, plinthHeight / 2, 0], mat),
    boxMesh(w, bodyHeight, d, [0, plinthHeight + bodyHeight / 2, 0], mat),
    boxMesh(doorWidth, bodyHeight * 0.94, doorDepth, [-(doorWidth + doorGap) / 2, plinthHeight + bodyHeight / 2, d / 2 + doorDepth / 2], mat),
    boxMesh(doorWidth, bodyHeight * 0.94, doorDepth, [(doorWidth + doorGap) / 2, plinthHeight + bodyHeight / 2, d / 2 + doorDepth / 2], mat),
  ];
}

function buildNightstand(w: number, d: number, h: number, mat: string): MeshData[] {
  // 台面 + 柜体 + 一条抽屉分缝
  const topThickness = Math.max(h * 0.08, 0.03);
  const legHeight = Math.max(h * 0.12, 0.06);
  const bodyHeight = Math.max(h - topThickness - legHeight, 0.05);
  const bodyDepth = Math.max(d * 0.9, 0.1);
  return [
    boxMesh(w, topThickness, d, [0, h - topThickness / 2, 0], mat),
    boxMesh(w * 0.9, bodyHeight, bodyDepth, [0, legHeight + bodyHeight / 2, 0], mat),
    boxMesh(w * 0.88, topThickness * 0.5, Math.max(d * 0.04, 0.02), [0, legHeight + bodyHeight * 0.55, bodyDepth / 2], mat),
    ...cornerLegs(Math.max(w / 2 - Math.max(w * 0.08, 0.03), 0), Math.max(bodyDepth / 2 - Math.max(w * 0.08, 0.03), 0), Math.max(w * 0.08, 0.03), legHeight, mat),
  ];
}

function buildTvCabinet(w: number, d: number, h: number, mat: string): MeshData[] {
  // 台面 + 柜体 + 中间设备格
  const topThickness = Math.max(h * 0.08, 0.03);
  const plinthHeight = Math.max(h * 0.1, 0.05);
  const bodyHeight = Math.max(h - topThickness - plinthHeight, 0.06);
  const bayWidth = Math.max(w * 0.32, 0.2);
  const sideWidth = (w - bayWidth) / 2;
  const bodyCenterY = plinthHeight + bodyHeight / 2;
  return [
    boxMesh(w, topThickness, d, [0, h - topThickness / 2, 0], mat),
    boxMesh(w * 0.98, plinthHeight, d * 0.9, [0, plinthHeight / 2, 0], mat),
    boxMesh(sideWidth, bodyHeight, d, [-(bayWidth + sideWidth) / 2, bodyCenterY, 0], mat),
    boxMesh(sideWidth, bodyHeight, d, [(bayWidth + sideWidth) / 2, bodyCenterY, 0], mat),
    boxMesh(bayWidth, bodyHeight, Math.max(d * 0.9, 0.1), [0, bodyCenterY, 0], mat),
  ];
}

function buildBed(w: number, d: number, h: number, mat: string): MeshData[] {
  const frameHeight = Math.max(h * 0.28, 0.12);
  const mattressHeight = Math.max(h * 0.32, 0.12);
  return [
    boxMesh(w, frameHeight, d, [0, frameHeight / 2, 0], mat),
    boxMesh(w * 0.94, mattressHeight, d * 0.94, [0, frameHeight + mattressHeight / 2, 0], mat),
    boxMesh(w, h, Math.max(d * 0.06, 0.06), [0, h / 2, -d / 2], mat),
  ];
}

function buildLamp(w: number, d: number, h: number, mat: string): MeshData[] {
  const radius = Math.max(Math.min(w, d) / 2, 0.04);
  const baseHeight = Math.max(h * 0.08, 0.03);
  return [
    ...buildPrimitive({ type: 'primitive', id: 'lamp_base', shape: 'cylinder', radius, height: baseHeight, position: [0, baseHeight / 2, 0], material: mat }),
    ...buildPrimitive({ type: 'primitive', id: 'lamp_stand', shape: 'cylinder', radius: radius * 0.12, height: h * 0.62, position: [0, h * 0.36, 0], material: mat }),
    ...buildPrimitive({
      type: 'primitive', id: 'lamp_shade', shape: 'cylinder',
      radiusBottom: radius, radiusTop: radius * 0.55, height: h * 0.3,
      position: [0, h * 0.82, 0], material: mat,
    }),
  ];
}

function cornerLegs(insetX: number, insetZ: number, width: number, height: number, mat: string): MeshData[] {
  const y = height / 2;
  return [
    boxMesh(width, height, width, [-insetX, y, -insetZ], mat),
    boxMesh(width, height, width, [insetX, y, -insetZ], mat),
    boxMesh(width, height, width, [-insetX, y, insetZ], mat),
    boxMesh(width, height, width, [insetX, y, insetZ], mat),
  ];
}

function boxMesh(
  width: number,
  height: number,
  depth: number,
  position: [number, number, number],
  materialRef: string,
): MeshData {
  const indexed = indexTriList(createBoxGeometry(
    Math.max(width, 0.001),
    Math.max(height, 0.001),
    Math.max(depth, 0.001),
  ));
  return {
    geometry: indexed.geometry,
    indices: new Uint32Array(indexed.indices),
    transform: { position, rotation: [0, 0, 0], scale: [1, 1, 1] },
    materialRef,
  };
}

function rotateEulerXYZ(
  point: [number, number, number],
  rotation: [number, number, number],
): [number, number, number] {
  const [x, y, z] = point;
  const [rx, ry, rz] = rotation;
  const cx = Math.cos(rx), sx = Math.sin(rx);
  const cy = Math.cos(ry), sy = Math.sin(ry);
  const cz = Math.cos(rz), sz = Math.sin(rz);
  return [
    cy * cz * x - cy * sz * y + sy * z,
    (sx * sy * cz + cx * sz) * x + (-sx * sy * sz + cx * cz) * y - sx * cy * z,
    (-cx * sy * cz + sx * sz) * x + (cx * sy * sz + sx * cz) * y + cx * cy * z,
  ];
}
