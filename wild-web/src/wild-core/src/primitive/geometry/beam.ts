import type { BeamParams, MeshData } from '../types';
import { indexTriList, stripToTriList } from './mesh-helper';
import { evalCurve, createBoxGeometry } from './wall';

export function buildBeam(params: BeamParams): MeshData[] {
  const { from, to, crossSection, width, height, material } = params;
  const curve = (params as any).curve;

  if (curve) return buildCurvedBeam(from, to, crossSection, width, height, material || 'default', curve);

  const dx = to[0] - from[0], dz = to[2] - from[2];
  const length = Math.sqrt(dx * dx + dz * dz + (to[1] - from[1]) ** 2);
  const geoFn = crossSection === 'circular' ? createCylinderGeometry(width / 2, length) : createBoxGeometry(width, height, length);
  const { geometry, indices } = crossSection === 'circular' ? stripToTriList(geoFn) : indexTriList(geoFn);
  const midX = (from[0] + to[0]) / 2, midY = (from[1] + to[1]) / 2, midZ = (from[2] + to[2]) / 2;
  return [{
    geometry, indices: new Uint32Array(indices),
    transform: { position: [midX, midY, midZ], rotation: [0, Math.atan2(dx, dz), 0], scale: [1, 1, 1] },
    materialRef: material || 'default'
  }];
}

function buildCurvedBeam(from: number[], to: number[], crossSection: string, width: number, height: number, material: string, curve: any): MeshData[] {
  const points = evalCurve(from as any, to as any, curve);
  const meshes: MeshData[] = [];
  for (let i = 0; i < points.length - 1; i++) {
    const [x1, z1] = points[i], [x2, z2] = points[i + 1];
    const segLen = Math.sqrt((x2 - x1) ** 2 + (z2 - z1) ** 2);
    if (segLen < 0.001) continue;
    const geoFn = crossSection === 'circular' ? createCylinderGeometry(width / 2, segLen) : createBoxGeometry(width, height, segLen);
    const { geometry, indices } = crossSection === 'circular' ? stripToTriList(geoFn) : indexTriList(geoFn);
    meshes.push({
      geometry, indices: new Uint32Array(indices),
      transform: { position: [(x1 + x2) / 2, (from[1] + to[1]) / 2, (z1 + z2) / 2], rotation: [0, Math.atan2(x2 - x1, z2 - z1), 0], scale: [1, 1, 1] },
      materialRef: material,
    });
  }
  return meshes;
}

function createCylinderGeometry(radius: number, length: number): Float32Array {
  const seg = 16, v: number[] = [];
  for (let i = 0; i <= seg; i++) {
    const angle = (i / seg) * Math.PI * 2;
    v.push(Math.cos(angle) * radius, Math.sin(angle) * radius, -length / 2);
    v.push(Math.cos(angle) * radius, Math.sin(angle) * radius, length / 2);
  }
  return new Float32Array(v);
}
