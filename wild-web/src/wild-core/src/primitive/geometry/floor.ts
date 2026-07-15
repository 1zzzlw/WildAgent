import type { FloorParams, MeshData } from '../types';
import { indexTriList } from './mesh-helper';
import { createBoxGeometry } from './wall';
import { subdivideBoxShared } from './face-surface';

export function buildFloor(params: FloorParams): MeshData[] {
  const { from, to, thickness, material } = params;
  const shape = (params as any).shape;

  // 圆形地板
  if (shape === 'circle') {
    return buildCircularFloor(params);
  }

  const surfaces = (params as any).surfaces;
  if (surfaces) {
    const patMap: Record<string, number> = { front:0, back:1, top:2, bottom:3, right:4, left:5 };
    const pat: any[] = [];
    for (let i = 0; i < 6; i++) pat[i] = null;
    for (const [name, p] of Object.entries(surfaces)) {
      const idx = patMap[name];
      if (idx !== undefined) pat[idx] = p;
    }
    const w = Math.abs(to[0] - from[0]), d = Math.abs(to[2] - from[2]), t = thickness || 0;
    if (t > 0.01) {
      const sb = subdivideBoxShared(w, t, d, pat);
      const midX = (from[0] + to[0]) / 2, midZ = (from[2] + to[2]) / 2;
      return [{ geometry: sb.geometry, indices: sb.indices, vertexColors: sb.vertexColors,
        transform: { position: [midX, from[1]-t/2, midZ], rotation: [0,0,0], scale: [1,1,1] },
        materialRef: material || 'default', patternMortarColor: sb.mortarColor }];
    }
  }

  const width = Math.abs(to[0] - from[0]);
  const depth = Math.abs(to[2] - from[2]);
  const effectiveThick = thickness || 0;
  const isSolid = effectiveThick > 0.01;
  const raw = isSolid ? createBoxGeometry(width, effectiveThick, depth) : createPlaneGeometry(width, depth);
  const { geometry, indices } = indexTriList(raw);
  const midX = (from[0] + to[0]) / 2;
  const midZ = (from[2] + to[2]) / 2;
  return [{
    geometry, indices: new Uint32Array(indices),
    transform: { position: [midX, isSolid ? from[1]-effectiveThick/2 : from[1], midZ], rotation: [0,0,0], scale: [1,1,1] },
    materialRef: material || 'default'
  }];
}

/** 圆形地板：生成 segments 边形近似  */
function buildCircularFloor(params: FloorParams): MeshData[] {
  const { from, thickness, material } = params;
  const p = params as any;
  const radius = p.radius;
  const seg = p.segments || 32;
  const effectiveThick = thickness || 0;
  const isSolid = effectiveThick > 0.01;
  const cx = from[0], cz = from[2];
  const centerY = from[1] - effectiveThick / 2; // 顶面 Y 居中
  const yBot = from[1] - effectiveThick;
  const verts: number[] = [];
  const idx: number[] = [];

  // 顶面扇形
  for (let i = 0; i < seg; i++) {
    const a1 = (i / seg) * Math.PI * 2;
    const a2 = ((i + 1) / seg) * Math.PI * 2;
    const x1 = cx + radius * Math.cos(a1), z1 = cz + radius * Math.sin(a1);
    const x2 = cx + radius * Math.cos(a2), z2 = cz + radius * Math.sin(a2);
    verts.push(cx, isSolid ? centerY : from[1], cz, x1, isSolid ? centerY : from[1], z1, x2, isSolid ? centerY : from[1], z2);
  }

  if (isSolid) {
    // 底面扇形
    const botStart = verts.length / 3;
    for (let i = 0; i < seg; i++) {
      const a1 = (i / seg) * Math.PI * 2;
      const a2 = ((i + 1) / seg) * Math.PI * 2;
      const x1 = cx + radius * Math.cos(a1), z1 = cz + radius * Math.sin(a1);
      const x2 = cx + radius * Math.cos(a2), z2 = cz + radius * Math.sin(a2);
      verts.push(cx, yBot, cz, x2, yBot, z2, x1, yBot, z1);
    }
    // 侧壁
    const sideStart = verts.length / 3;
    for (let i = 0; i < seg; i++) {
      const a1 = (i / seg) * Math.PI * 2;
      const a2 = ((i + 1) / seg) * Math.PI * 2;
      const x1=cx+radius*Math.cos(a1), z1=cz+radius*Math.sin(a1);
      const x2=cx+radius*Math.cos(a2), z2=cz+radius*Math.sin(a2);
      verts.push(x1, centerY, z1, x2, centerY, z2, x2, yBot, z2);
      verts.push(x1, centerY, z1, x2, yBot, z2, x1, yBot, z1);
    }
  }

  for (let i = 0; i < verts.length / 3; i++) idx.push(i);
  return [{
    geometry: new Float32Array(verts), indices: new Uint32Array(idx),
    transform: { position: [0,0,0], rotation: [0,0,0], scale: [1,1,1] },
    materialRef: material || 'default'
  }];
}

function createPlaneGeometry(w: number, d: number): Float32Array {
  const hw = w / 2, hd = d / 2;
  return new Float32Array([hw,0,-hd,-hw,0,-hd,hw,0,hd,-hw,0,hd,hw,0,hd,-hw,0,-hd]);
}
