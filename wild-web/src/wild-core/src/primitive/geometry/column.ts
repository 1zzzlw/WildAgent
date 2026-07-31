import type { ColumnParams, MeshData, Vec3 } from '../types';
import { buildPrimitive } from './primitive';

export function buildColumn(params: ColumnParams): MeshData[] {
  const { base, height, bottomRadius, topRadius, material, style } = params;
  if (height <= 0 || bottomRadius <= 0 || topRadius <= 0) {
    throw new Error('column height and radii must be greater than zero');
  }

  const materialRef = material || 'default';
  const fluteCount = params.flutes ?? defaultFlutes(style);
  const radialSegments = Math.max(24, fluteCount > 0 ? fluteCount * 4 : 32);
  const heightSegments = 16;
  const entasis = params.entasis ?? defaultEntasis(style, height);
  const inclination = params.inclination ?? 0;
  const inclinationDirection = directionToWorldOrigin(base);
  const vertices: number[] = [];
  const normals: number[] = [];
  const uvs: number[] = [];

  const ringPoint = (ring: number, segment: number): Vec3 => {
    const t = ring / heightSegments;
    const angle = segment / radialSegments * Math.PI * 2;
    const taperedRadius = bottomRadius + (topRadius - bottomRadius) * t;
    const bulge = Math.sin(Math.PI * t) * entasis;
    const fluteDepth = fluteCount > 0 ? Math.min(taperedRadius * 0.055, 0.018) : 0;
    const flute = fluteCount > 0
      ? fluteDepth * (0.5 + 0.5 * Math.cos(angle * fluteCount))
      : 0;
    const radius = Math.max(0.001, taperedRadius + bulge - flute);
    const offset = inclination * height * t;
    return [
      Math.cos(angle) * radius + inclinationDirection[0] * offset,
      t * height,
      Math.sin(angle) * radius + inclinationDirection[2] * offset,
    ];
  };

  const push = (point: Vec3, u: number, v: number) => {
    vertices.push(...point);
    const radial = normalize([point[0], 0, point[2]]);
    normals.push(...radial);
    uvs.push(u, v);
  };

  for (let ring = 0; ring < heightSegments; ring++) {
    const v0 = ring / heightSegments;
    const v1 = (ring + 1) / heightSegments;
    for (let segment = 0; segment < radialSegments; segment++) {
      const u0 = segment / radialSegments;
      const u1 = (segment + 1) / radialSegments;
      const p00 = ringPoint(ring, segment);
      const p10 = ringPoint(ring, segment + 1);
      const p11 = ringPoint(ring + 1, segment + 1);
      const p01 = ringPoint(ring + 1, segment);
      push(p00, u0, v0);
      push(p11, u1, v1);
      push(p10, u1, v0);
      push(p00, u0, v0);
      push(p01, u0, v1);
      push(p11, u1, v1);
    }
  }

  const shaft: MeshData = {
    geometry: new Float32Array(vertices),
    indices: Uint32Array.from({ length: vertices.length / 3 }, (_, index) => index),
    normals: new Float32Array(normals),
    uvs: new Float32Array(uvs),
    transform: { position: [...base], rotation: [0, 0, 0], scale: [1, 1, 1] },
    materialRef,
  };

  return [shaft, ...buildStyleDetails(params, materialRef, inclinationDirection)];
}

function buildStyleDetails(
  params: ColumnParams,
  materialRef: string,
  inclinationDirection: Vec3,
): MeshData[] {
  const { base, height, bottomRadius, topRadius, style } = params;
  if (style === 'modern') return [];

  const detailHeight = Math.min(height * 0.06, Math.max(bottomRadius * 0.35, 0.04));
  const topOffset = (params.inclination ?? 0) * height;
  const topCenter: Vec3 = [
    base[0] + inclinationDirection[0] * topOffset,
    base[1] + height - detailHeight / 2,
    base[2] + inclinationDirection[2] * topOffset,
  ];
  const bottomCenter: Vec3 = [base[0], base[1] + detailHeight / 2, base[2]];
  const details: MeshData[] = [];

  const addCylinder = (radius: number, partHeight: number, position: Vec3) => {
    details.push(...buildPrimitive({
      type: 'primitive',
      id: `${params.id}_detail`,
      shape: 'cylinder',
      radius,
      height: partHeight,
      segments: 32,
      position,
      material: materialRef,
    }));
  };

  if (style === 'doric') {
    addCylinder(bottomRadius * 1.22, detailHeight, bottomCenter);
    addCylinder(topRadius * 1.35, detailHeight, topCenter);
  } else if (style === 'ionic') {
    addCylinder(bottomRadius * 1.25, detailHeight, bottomCenter);
    addCylinder(topRadius * 1.55, detailHeight, topCenter);
    addCylinder(topRadius * 1.25, detailHeight * 0.55, [
      topCenter[0], topCenter[1] - detailHeight * 0.65, topCenter[2],
    ]);
  } else if (style === 'corinthian') {
    addCylinder(bottomRadius * 1.3, detailHeight, bottomCenter);
    addCylinder(topRadius * 1.65, detailHeight, topCenter);
    addCylinder(topRadius * 1.42, detailHeight * 0.8, [
      topCenter[0], topCenter[1] - detailHeight * 0.8, topCenter[2],
    ]);
    addCylinder(topRadius * 1.2, detailHeight * 0.65, [
      topCenter[0], topCenter[1] - detailHeight * 1.45, topCenter[2],
    ]);
  } else if (style === 'chinese_wooden') {
    addCylinder(bottomRadius * 1.18, detailHeight * 0.65, bottomCenter);
    addCylinder(topRadius * 1.22, detailHeight * 0.55, topCenter);
  }

  return details;
}

function defaultFlutes(style: ColumnParams['style']): number {
  if (style === 'doric') return 20;
  if (style === 'ionic' || style === 'corinthian') return 24;
  return 0;
}

function defaultEntasis(style: ColumnParams['style'], height: number): number {
  if (style === 'doric' || style === 'chinese_wooden') return height * 0.004;
  return 0;
}

function directionToWorldOrigin(base: Vec3): Vec3 {
  const length = Math.hypot(base[0], base[2]);
  if (length < 1e-6) return [0, 0, 0];
  return [-base[0] / length, 0, -base[2] / length];
}

function normalize(value: Vec3): Vec3 {
  const length = Math.hypot(value[0], value[1], value[2]);
  if (length < 1e-8) return [1, 0, 0];
  return [value[0] / length, value[1] / length, value[2] / length];
}
