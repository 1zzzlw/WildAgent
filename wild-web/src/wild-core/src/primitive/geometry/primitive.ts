import type { MeshData, PrimitiveParams, Vec3 } from '../types';
import { createBoxGeometry } from './wall';
import { generatePlanarUVs, indexTriList } from './mesh-helper';

type Vec2 = [number, number];

interface GeometryBuffers {
  geometry: Float32Array;
  indices: Uint32Array;
  normals?: Float32Array;
  uvs?: Float32Array;
}

export function buildPrimitive(params: PrimitiveParams): MeshData[] {
  const materialRef = params.material || 'default';
  const transform = {
    position: params.position || [0, 0, 0] as Vec3,
    rotation: params.rotation || [0, 0, 0] as Vec3,
    scale: params.scale || [1, 1, 1] as Vec3,
  };

  let buffers: GeometryBuffers;
  switch (params.shape) {
    case 'box':
      buffers = buildBox(params);
      break;
    case 'sphere':
      buffers = buildSphere(params);
      break;
    case 'cylinder':
      buffers = buildCylinder(params);
      break;
    case 'profile_sweep':
      buffers = buildProfileSweep(params);
      break;
    default:
      throw new Error(`Unsupported primitive shape: ${(params as any).shape}`);
  }

  return [{
    ...buffers,
    transform,
    materialRef,
  }];
}

function buildBox(params: PrimitiveParams): GeometryBuffers {
  const dimensions = params.dimensions || [1, 1, 1];
  if (!Array.isArray(dimensions) || dimensions.length !== 3) {
    throw new Error(
      'primitive box dimensions must be [width, height, depth] with three positive finite numbers',
    );
  }
  const [width, height, depth] = dimensions;
  assertPositive(width, 'dimensions[0]');
  assertPositive(height, 'dimensions[1]');
  assertPositive(depth, 'dimensions[2]');
  const indexed = indexTriList(createBoxGeometry(width, height, depth));
  return {
    geometry: indexed.geometry,
    indices: new Uint32Array(indexed.indices),
    uvs: generatePlanarUVs(indexed.geometry),
  };
}

function buildSphere(params: PrimitiveParams): GeometryBuffers {
  const radius = params.radius ?? 0.5;
  const widthSegments = clampInteger(params.segments ?? 32, 8, 128);
  const heightSegments = clampInteger(params.heightSegments ?? Math.round(widthSegments / 2), 4, 64);
  assertPositive(radius, 'radius');

  const vertices: number[] = [];
  const normals: number[] = [];
  const uvs: number[] = [];

  const point = (u: number, v: number): Vec3 => {
    const longitude = u * Math.PI * 2;
    const latitude = (v - 0.5) * Math.PI;
    const cosLatitude = Math.cos(latitude);
    return [
      Math.cos(longitude) * cosLatitude * radius,
      Math.sin(latitude) * radius,
      Math.sin(longitude) * cosLatitude * radius,
    ];
  };

  const pushVertex = (p: Vec3, u: number, v: number) => {
    vertices.push(p[0], p[1], p[2]);
    const invRadius = 1 / radius;
    normals.push(p[0] * invRadius, p[1] * invRadius, p[2] * invRadius);
    uvs.push(u, v);
  };

  for (let y = 0; y < heightSegments; y++) {
    const v0 = y / heightSegments;
    const v1 = (y + 1) / heightSegments;
    for (let x = 0; x < widthSegments; x++) {
      const u0 = x / widthSegments;
      const u1 = (x + 1) / widthSegments;
      const p00 = point(u0, v0);
      const p10 = point(u1, v0);
      const p11 = point(u1, v1);
      const p01 = point(u0, v1);

      // 经度方向 × 纬度方向的自然绕序朝内，因此这里反转三角形绕序。
      pushVertex(p00, u0, v0);
      pushVertex(p11, u1, v1);
      pushVertex(p10, u1, v0);
      pushVertex(p00, u0, v0);
      pushVertex(p01, u0, v1);
      pushVertex(p11, u1, v1);
    }
  }

  return sequentialBuffers(vertices, normals, uvs);
}

function buildCylinder(params: PrimitiveParams): GeometryBuffers {
  const radiusBottom = params.radiusBottom ?? params.radius ?? 0.5;
  const radiusTop = params.radiusTop ?? params.radius ?? radiusBottom;
  const height = params.height ?? 1;
  const segments = clampInteger(params.segments ?? 32, 3, 128);
  assertPositive(radiusBottom, 'radiusBottom');
  assertPositive(radiusTop, 'radiusTop');
  assertPositive(height, 'height');

  const vertices: number[] = [];
  const normals: number[] = [];
  const uvs: number[] = [];
  const halfHeight = height / 2;

  const push = (p: Vec3, n: Vec3, uv: Vec2) => {
    vertices.push(...p);
    normals.push(...n);
    uvs.push(...uv);
  };

  for (let i = 0; i < segments; i++) {
    const u0 = i / segments;
    const u1 = (i + 1) / segments;
    const a0 = u0 * Math.PI * 2;
    const a1 = u1 * Math.PI * 2;
    const n0: Vec3 = [Math.cos(a0), 0, Math.sin(a0)];
    const n1: Vec3 = [Math.cos(a1), 0, Math.sin(a1)];
    const b0: Vec3 = [n0[0] * radiusBottom, -halfHeight, n0[2] * radiusBottom];
    const b1: Vec3 = [n1[0] * radiusBottom, -halfHeight, n1[2] * radiusBottom];
    const t0: Vec3 = [n0[0] * radiusTop, halfHeight, n0[2] * radiusTop];
    const t1: Vec3 = [n1[0] * radiusTop, halfHeight, n1[2] * radiusTop];

    push(b0, n0, [u0, 0]);
    push(t1, n1, [u1, 1]);
    push(b1, n1, [u1, 0]);
    push(b0, n0, [u0, 0]);
    push(t0, n0, [u0, 1]);
    push(t1, n1, [u1, 1]);

    const topNormal: Vec3 = [0, 1, 0];
    const bottomNormal: Vec3 = [0, -1, 0];
    push([0, halfHeight, 0], topNormal, [0.5, 0.5]);
    push(t1, topNormal, [(n1[0] + 1) / 2, (n1[2] + 1) / 2]);
    push(t0, topNormal, [(n0[0] + 1) / 2, (n0[2] + 1) / 2]);
    push([0, -halfHeight, 0], bottomNormal, [0.5, 0.5]);
    push(b0, bottomNormal, [(n0[0] + 1) / 2, (n0[2] + 1) / 2]);
    push(b1, bottomNormal, [(n1[0] + 1) / 2, (n1[2] + 1) / 2]);
  }

  return sequentialBuffers(vertices, normals, uvs);
}

function buildProfileSweep(params: PrimitiveParams): GeometryBuffers {
  const path = params.path || [];
  if (path.length < 2) throw new Error('profile_sweep requires at least two path points');

  const profile = params.profile?.length
    ? params.profile
    : createCircularProfile(params.radius ?? 0.05, clampInteger(params.segments ?? 12, 3, 64));
  if (profile.length < 2) throw new Error('profile_sweep requires at least two profile points');

  const closed = params.closedProfile !== false;
  const edgeCount = closed ? profile.length : profile.length - 1;
  const frames = path.map((_, index) => createPathFrame(path, index));
  const cumulative = [0];
  for (let i = 1; i < path.length; i++) {
    cumulative.push(cumulative[i - 1] + distance(path[i - 1], path[i]));
  }
  const totalLength = Math.max(cumulative[cumulative.length - 1], 1e-6);

  const vertices: number[] = [];
  const normals: number[] = [];
  const uvs: number[] = [];

  const sweptPoint = (pathIndex: number, profileIndex: number): Vec3 => {
    const [u, v] = profile[profileIndex];
    const frame = frames[pathIndex];
    const origin = path[pathIndex];
    return [
      origin[0] + frame.right[0] * u + frame.up[0] * v,
      origin[1] + frame.right[1] * u + frame.up[1] * v,
      origin[2] + frame.right[2] * u + frame.up[2] * v,
    ];
  };

  const pushTriangle = (a: Vec3, b: Vec3, c: Vec3, uvA: Vec2, uvB: Vec2, uvC: Vec2) => {
    const normal = normalize(cross(subtract(b, a), subtract(c, a)));
    for (const [point, uv] of [[a, uvA], [b, uvB], [c, uvC]] as Array<[Vec3, Vec2]>) {
      vertices.push(...point);
      normals.push(...normal);
      uvs.push(...uv);
    }
  };

  for (let pi = 0; pi < path.length - 1; pi++) {
    const pathU0 = cumulative[pi] / totalLength;
    const pathU1 = cumulative[pi + 1] / totalLength;
    for (let pj = 0; pj < edgeCount; pj++) {
      const next = (pj + 1) % profile.length;
      const profileV0 = pj / edgeCount;
      const profileV1 = (pj + 1) / edgeCount;
      const a = sweptPoint(pi, pj);
      const b = sweptPoint(pi + 1, pj);
      const c = sweptPoint(pi + 1, next);
      const d = sweptPoint(pi, next);
      pushTriangle(a, b, c, [pathU0, profileV0], [pathU1, profileV0], [pathU1, profileV1]);
      pushTriangle(a, c, d, [pathU0, profileV0], [pathU1, profileV1], [pathU0, profileV1]);
    }
  }

  return sequentialBuffers(vertices, normals, uvs);
}

function createCircularProfile(radius: number, segments: number): Vec2[] {
  assertPositive(radius, 'radius');
  return Array.from({ length: segments }, (_, index) => {
    const angle = index / segments * Math.PI * 2;
    return [Math.cos(angle) * radius, Math.sin(angle) * radius];
  });
}

function createPathFrame(path: Vec3[], index: number): { right: Vec3; up: Vec3 } {
  const previous = path[Math.max(0, index - 1)];
  const next = path[Math.min(path.length - 1, index + 1)];
  const tangent = normalize(subtract(next, previous));
  const referenceUp: Vec3 = Math.abs(tangent[1]) < 0.95 ? [0, 1, 0] : [1, 0, 0];
  const right = normalize(cross(referenceUp, tangent));
  const up = normalize(cross(tangent, right));
  return { right, up };
}

function sequentialBuffers(vertices: number[], normals: number[], uvs: number[]): GeometryBuffers {
  const vertexCount = vertices.length / 3;
  return {
    geometry: new Float32Array(vertices),
    indices: Uint32Array.from({ length: vertexCount }, (_, index) => index),
    normals: new Float32Array(normals),
    uvs: new Float32Array(uvs),
  };
}

function subtract(a: Vec3, b: Vec3): Vec3 {
  return [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
}

function cross(a: Vec3, b: Vec3): Vec3 {
  return [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0],
  ];
}

function normalize(value: Vec3): Vec3 {
  const length = Math.hypot(value[0], value[1], value[2]);
  if (length < 1e-8) return [1, 0, 0];
  return [value[0] / length, value[1] / length, value[2] / length];
}

function distance(a: Vec3, b: Vec3): number {
  return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
}

function assertPositive(value: number, field: string): void {
  if (!Number.isFinite(value) || value <= 0) {
    throw new Error(`${field} must be a positive finite number`);
  }
}

function clampInteger(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, Math.round(value)));
}
