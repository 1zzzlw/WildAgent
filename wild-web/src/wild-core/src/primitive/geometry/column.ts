import type { ColumnParams, MeshData } from '../types';
import { finalizeCylinder } from './mesh-helper';

export function buildColumn(params: ColumnParams): MeshData[] {
  const { base, height, bottomRadius, topRadius, material } = params;
  const segments = params.flutes || 32;
  const { geometry, indices } = finalizeCylinder(createCylinderGeometry(bottomRadius, topRadius, height, segments), segments);

  return [{
    geometry,
    indices: new Uint32Array(indices),
    transform: {
      position: [base[0], base[1] + height / 2, base[2]],
      rotation: [0, 0, 0],
      scale: [1, 1, 1]
    },
    materialRef: material || 'default'
  }];
}

function createCylinderGeometry(r1: number, r2: number, h: number, seg: number): Float32Array {
  const vertices: number[] = [];
  const hh = h / 2;

  // 侧表面
  for (let i = 0; i <= seg; i++) {
    const angle = (i / seg) * Math.PI * 2;
    const x = Math.cos(angle);
    const z = Math.sin(angle);
    vertices.push(x * r1, -hh, z * r1);
    vertices.push(x * r2,  hh, z * r2);
  }

  // 顶面
  for (let i = 0; i <= seg; i++) {
    const angle = (i / seg) * Math.PI * 2;
    vertices.push(Math.cos(angle) * r2, hh, Math.sin(angle) * r2);
  }

  // 底面
  for (let i = 0; i <= seg; i++) {
    const angle = (i / seg) * Math.PI * 2;
    vertices.push(Math.cos(angle) * r1, -hh, Math.sin(angle) * r1);
  }

  return new Float32Array(vertices);
}