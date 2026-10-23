import type { FloorParams, MeshData } from '../types';
import { generateArchitecturalSurfaceAttributes, indexTriList } from './mesh-helper';
import { triangulatePolygon } from './polygon';
import { createBoxGeometry } from './wall';
import { subdivideBoxShared } from './face-surface';

export function buildFloor(params: FloorParams): MeshData[] {
  const { from, to, thickness, material } = params;
  const shape = (params as any).shape;

  if (shape === 'polygon') return buildPolygonFloor(params, params.polygon || [], params.holes);
  if (params.polygon?.length || params.holes?.length) throw new Error('floor polygon/holes requires shape="polygon"');

  // 圆形地板
  if (shape === 'circle') {
    return buildCircularFloor(params);
  }
  if (!to) {
    throw new Error('floor.to is required when shape is rect');
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
        transform: { position: [midX, from[1] + t/2, midZ], rotation: [0,0,0], scale: [1,1,1] },
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
    geometry, indices: new Uint32Array(indices), ...generateArchitecturalSurfaceAttributes(geometry),
    transform: { position: [midX, isSolid ? from[1] + effectiveThick/2 : from[1], midZ], rotation: [0,0,0], scale: [1,1,1] },
    materialRef: material || 'default'
  }];
}

/** 圆形地板：生成 segments 边形近似  */
function buildCircularFloor(params: FloorParams): MeshData[] {
  const radius = params.radius ?? 0;
  if (!Number.isFinite(radius) || radius <= 0) throw new Error('floor.radius must be positive');
  const seg = Math.max(3, Math.min(256, Math.round(params.segments || 32)));
  return buildPolygonFloor(params, Array.from({ length: seg }, (_, i) => {
    const angle = i / seg * Math.PI * 2;
    return [Math.cos(angle) * radius, Math.sin(angle) * radius];
  }));
}

function buildPolygonFloor(params: FloorParams, polygon: Array<[number, number]>, holes: Array<Array<[number, number]>> = []): MeshData[] {
  const { rings, points, triangles } = triangulatePolygon(polygon, holes);
  const thickness = params.thickness || 0;
  if (!Number.isFinite(thickness) || thickness < 0) throw new Error('floor.thickness must be non-negative');
  const verts: number[] = [];
  const push = (p: [number, number], y: number) => verts.push(p[0], y, p[1]);
  for (let i = 0; i < triangles.length; i += 3) {
    const a = points[triangles[i]], b = points[triangles[i + 1]], c = points[triangles[i + 2]];
    push(a, thickness); push(c, thickness); push(b, thickness);
    if (thickness > 0) { push(a, 0); push(b, 0); push(c, 0); }
  }
  if (thickness > 0) {
    for (const ring of rings) for (let i = 0; i < ring.length; i++) {
      const a = ring[i], b = ring[(i + 1) % ring.length];
      push(a, 0); push(a, thickness); push(b, thickness);
      push(a, 0); push(b, thickness); push(b, 0);
    }
  }
  const geometry = new Float32Array(verts);
  return [{
    geometry, indices: Uint32Array.from({ length: verts.length / 3 }, (_, i) => i),
    ...generateArchitecturalSurfaceAttributes(geometry),
    transform: { position: [...params.from], rotation: [0,0,0], scale: [1,1,1] },
    materialRef: params.material || 'default'
  }];
}

function createPlaneGeometry(w: number, d: number): Float32Array {
  const hw = w / 2, hd = d / 2;
  return new Float32Array([hw,0,-hd,-hw,0,-hd,hw,0,hd,-hw,0,hd,hw,0,hd,-hw,0,-hd]);
}
