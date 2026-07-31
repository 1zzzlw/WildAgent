import type { BeamParams, MeshData } from '../types';
import { indexTriList, stripToTriList } from './mesh-helper';
import { evalCurve, createBoxGeometry } from './wall';

export function buildBeam(params: BeamParams): MeshData[] {
  const { from, to, crossSection, width, height, material } = params;
  const curve = (params as any).curve;

  if (curve) return buildCurvedBeam(from, to, crossSection, width, height, material || 'default', curve);

  const dx = to[0] - from[0], dy = to[1] - from[1], dz = to[2] - from[2];
  const length = Math.sqrt(dx * dx + dy * dy + dz * dz);
  if (length < 0.001) throw new Error('beam from/to distance must be greater than zero');
  const midX = (from[0] + to[0]) / 2, midY = (from[1] + to[1]) / 2, midZ = (from[2] + to[2]) / 2;
  const rotation = directionRotation(dx, dy, dz);
  const transform = { position: [midX, midY, midZ] as [number, number, number], rotation, scale: [1, 1, 1] as [number, number, number] };

  if (crossSection === 'i-beam') {
    const flangeHeight = Math.max(height * 0.16, 0.01);
    const webWidth = Math.max(width * 0.18, 0.01);
    return [
      boxMesh(width, flangeHeight, length, [0, height / 2 - flangeHeight / 2, 0], transform, material || 'default'),
      boxMesh(width, flangeHeight, length, [0, -height / 2 + flangeHeight / 2, 0], transform, material || 'default'),
      boxMesh(webWidth, Math.max(height - flangeHeight * 2, 0.01), length, [0, 0, 0], transform, material || 'default'),
    ];
  }

  const geoFn = crossSection === 'circular'
    ? createCylinderGeometry(width / 2, length)
    : createBoxGeometry(width, height, length);
  const { geometry, indices } = crossSection === 'circular' ? stripToTriList(geoFn) : indexTriList(geoFn);
  return [{
    geometry,
    indices: new Uint32Array(indices),
    transform,
    materialRef: material || 'default',
  }];
}

function buildCurvedBeam(from: number[], to: number[], crossSection: string, width: number, height: number, material: string, curve: any): MeshData[] {
  const points = evalCurve(from as any, to as any, curve);
  const meshes: MeshData[] = [];
  for (let i = 0; i < points.length - 1; i++) {
    const [x1, z1] = points[i], [x2, z2] = points[i + 1];
    const y1 = from[1] + (to[1] - from[1]) * (i / (points.length - 1));
    const y2 = from[1] + (to[1] - from[1]) * ((i + 1) / (points.length - 1));
    const dx = x2 - x1, dy = y2 - y1, dz = z2 - z1;
    const segLen = Math.sqrt(dx ** 2 + dy ** 2 + dz ** 2);
    if (segLen < 0.001) continue;
    const baseTransform = {
      position: [(x1 + x2) / 2, (y1 + y2) / 2, (z1 + z2) / 2] as [number, number, number],
      rotation: directionRotation(dx, dy, dz),
      scale: [1, 1, 1] as [number, number, number],
    };
    if (crossSection === 'i-beam') {
      const flangeHeight = Math.max(height * 0.16, 0.01);
      const webWidth = Math.max(width * 0.18, 0.01);
      meshes.push(
        boxMesh(width, flangeHeight, segLen, [0, height / 2 - flangeHeight / 2, 0], baseTransform, material),
        boxMesh(width, flangeHeight, segLen, [0, -height / 2 + flangeHeight / 2, 0], baseTransform, material),
        boxMesh(webWidth, Math.max(height - flangeHeight * 2, 0.01), segLen, [0, 0, 0], baseTransform, material),
      );
    } else {
      const geoFn = crossSection === 'circular' ? createCylinderGeometry(width / 2, segLen) : createBoxGeometry(width, height, segLen);
      const { geometry, indices } = crossSection === 'circular' ? stripToTriList(geoFn) : indexTriList(geoFn);
      meshes.push({ geometry, indices: new Uint32Array(indices), transform: baseTransform, materialRef: material });
    }
  }
  return meshes;
}

function directionRotation(dx: number, dy: number, dz: number): [number, number, number] {
  const horizontal = Math.hypot(dx, dz);
  return [-Math.atan2(dy, horizontal), Math.atan2(dx, dz), 0];
}

function boxMesh(
  width: number,
  height: number,
  length: number,
  localOffset: [number, number, number],
  parentTransform: MeshData['transform'],
  materialRef: string,
): MeshData {
  const indexed = indexTriList(createBoxGeometry(width, height, length));
  const rotatedOffset = rotateEulerXYZ(localOffset, parentTransform.rotation);
  return {
    geometry: indexed.geometry,
    indices: new Uint32Array(indexed.indices),
    transform: {
      position: [
        parentTransform.position[0] + rotatedOffset[0],
        parentTransform.position[1] + rotatedOffset[1],
        parentTransform.position[2] + rotatedOffset[2],
      ],
      rotation: [...parentTransform.rotation],
      scale: [1, 1, 1],
    },
    materialRef,
  };
}

function rotateEulerXYZ(point: [number, number, number], rotation: [number, number, number]): [number, number, number] {
  const [x, y, z] = point;
  const [rx, ry] = rotation;
  const cx = Math.cos(rx), sx = Math.sin(rx);
  const cy = Math.cos(ry), sy = Math.sin(ry);
  const y1 = y * cx - z * sx;
  const z1 = y * sx + z * cx;
  return [x * cy + z1 * sy, y1, -x * sy + z1 * cy];
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
