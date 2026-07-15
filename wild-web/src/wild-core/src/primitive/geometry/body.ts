import type { BodyParams, MeshData } from '../types';
import { indexTriList, finalizeCylinder } from './mesh-helper';

export function buildBody(params: BodyParams): MeshData[] {
  const { height, material } = params;
  const headRadius = height * 0.12;
  const bodyHeight = height * 0.4;
  const bodyRadius = height * 0.08;

  const { geometry: headGeo, indices: headIdx } = indexTriList(createSphereGeometry(headRadius, 12));
  const { geometry: bodyGeo, indices: bodyIdx } = finalizeCylinder(createCylinderGeometry(bodyRadius, bodyRadius, bodyHeight, 16), 16);

  return [
    {
      geometry: bodyGeo,
      indices: new Uint32Array(bodyIdx),
      transform: { position: [0, bodyHeight / 2, 0], rotation: [0, 0, 0], scale: [1, 1, 1] },
      materialRef: material || 'default'
    },
    {
      geometry: headGeo,
      indices: new Uint32Array(headIdx),
      transform: { position: [0, bodyHeight + headRadius, 0], rotation: [0, 0, 0], scale: [1, 1, 1] },
      materialRef: material || 'default'
    }
  ];
}

function createSphereGeometry(radius: number, seg: number): Float32Array {
  const v: number[] = [];
  for (let i = 0; i < seg; i++) {
    const lat1 = (i / seg) * Math.PI - Math.PI / 2;
    const lat2 = ((i + 1) / seg) * Math.PI - Math.PI / 2;
    for (let j = 0; j < seg; j++) {
      const lon1 = (j / seg) * Math.PI * 2;
      const lon2 = ((j + 1) / seg) * Math.PI * 2;
      const x1 = Math.cos(lat1) * Math.cos(lon1) * radius;
      const y1 = Math.sin(lat1) * radius;
      const z1 = Math.cos(lat1) * Math.sin(lon1) * radius;
      v.push(x1, y1, z1);
    }
  }
  return new Float32Array(v);
}

function createCylinderGeometry(r1: number, r2: number, h: number, seg: number): Float32Array {
  const v: number[] = [];
  const hh = h / 2;
  for (let i = 0; i <= seg; i++) {
    const angle = (i / seg) * Math.PI * 2;
    const x = Math.cos(angle);
    const z = Math.sin(angle);
    v.push(x * r1, -hh, z * r1);
    v.push(x * r2,  hh, z * r2);
  }
  return new Float32Array(v);
}