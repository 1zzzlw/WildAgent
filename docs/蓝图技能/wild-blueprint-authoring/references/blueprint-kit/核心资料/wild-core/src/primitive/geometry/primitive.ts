import type { MeshData, PrimitiveParams, Vec3 } from '../types';
import { createBoxGeometry } from './wall';
import { generateArchitecturalSurfaceAttributes, indexTriList } from './mesh-helper';
import { triangulatePolygon } from './polygon';
import type { LightElementBehavior, LightSourceDef } from '../../../types';

type Vec2 = [number, number];

interface GeometryBuffers {
  geometry: Float32Array;
  indices: Uint32Array;
  normals?: Float32Array;
  uvs?: Float32Array;
}

export function buildPrimitive(params: PrimitiveParams, metricUVs = false): MeshData[] {
  if (params.caps && params.shape !== 'profile_sweep') throw new Error('primitive.caps only applies to profile_sweep');
  if (params.label && (params.shape !== 'box' || typeof params.label.text !== 'string'
    || !params.label.text.trim() || params.label.text.length > 256)) {
    throw new Error('primitive.label 需要 box 外形和 1～256 字符的非空文字');
  }
  const interaction = params.lightSource ? resolveLightSource(params.lightSource) : undefined;
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
      buffers = buildSphere(params, metricUVs);
      break;
    case 'cylinder':
      buffers = buildCylinder(params, metricUVs);
      break;
    case 'profile_sweep':
      buffers = buildProfileSweep(params, metricUVs);
      break;
    default:
      throw new Error(`Unsupported primitive shape: ${(params as any).shape}`);
  }

  return [{
    ...buffers,
    transform,
    materialRef,
    label: params.label,
    interaction,
  }];
}

function resolveLightSource(source: LightSourceDef): LightElementBehavior {
  const intensity = source.intensity ?? 25;
  const distance = source.distance ?? 8;
  const angle = source.angle ?? 45;
  if (!Number.isFinite(intensity) || intensity < 0) throw new Error('lightSource.intensity 必须为非负有限数');
  assertPositive(distance, 'lightSource.distance');
  assertPositive(angle, 'lightSource.angle');
  if (angle > 90) throw new Error('lightSource.angle 不能超过 90 度');
  if (source.lightType && !['point', 'spot'].includes(source.lightType)) throw new Error('lightSource.lightType 必须为 point 或 spot');
  for (const [key, vector] of Object.entries({ color: source.color, offset: source.offset, direction: source.direction })) {
    if (vector && (vector.length !== 3 || !vector.every(Number.isFinite))) throw new Error(`lightSource.${key} 必须为三维有限数向量`);
  }
  if (source.color?.some(value => value < 0 || value > 1)) throw new Error('lightSource.color 必须在 0～1 之间');
  if (source.direction && Math.hypot(...source.direction) === 0) throw new Error('lightSource.direction 不能为零向量');
  return {
    kind: 'light', lightType: source.lightType ?? 'point', color: source.color ?? [1, 0.82, 0.58],
    lowIntensity: intensity, highIntensity: intensity * 3, distance, angle,
    initiallyOn: source.initiallyOn ?? true, offset: source.offset, direction: source.direction,
  };
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
    ...generateArchitecturalSurfaceAttributes(indexed.geometry),
  };
}

function buildSphere(params: PrimitiveParams, metricUVs: boolean): GeometryBuffers {
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
    uvs.push(u * (metricUVs ? 2 * Math.PI * radius : 1), v * (metricUVs ? Math.PI * radius : 1));
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

function buildCylinder(params: PrimitiveParams, metricUVs: boolean): GeometryBuffers {
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
  const circumference = Math.PI * (radiusBottom + radiusTop);

  const push = (p: Vec3, n: Vec3, uv: Vec2) => {
    vertices.push(...p);
    normals.push(...n);
    uvs.push(...(metricUVs
      ? Math.abs(n[1]) > 0.5
        ? [p[0], p[2]]
        : [uv[0] * circumference, uv[1] * Math.hypot(height, radiusTop - radiusBottom)]
      : uv));
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

function buildProfileSweep(params: PrimitiveParams, metricUVs: boolean): GeometryBuffers {
  const path = params.path || [];
  if (path.length < 2) throw new Error('profile_sweep requires at least two path points');
  path.forEach((point, index) => assertFiniteVec3(point, `path[${index}]`));
  for (let index = 0; index < path.length - 1; index++) {
    if (distance(path[index], path[index + 1]) < 1e-6) {
      throw new Error(`profile_sweep path[${index}] and path[${index + 1}] must not overlap`);
    }
  }

  let profile = params.profile?.length
    ? params.profile
    : createCircularProfile(params.radius ?? 0.05, clampInteger(params.segments ?? 12, 3, 64));
  const closed = params.closedProfile !== false;
  if (params.caps && !closed) throw new Error('profile_sweep caps requires closedProfile=true');
  const capped = params.caps ? triangulatePolygon(profile) : undefined;
  // Side construction expects a clockwise profile. Preserve legacy uncapped sweeps.
  if (capped) profile = [...capped.rings[0]].reverse();
  if (profile.length < (closed ? 3 : 2)) {
    throw new Error(`profile_sweep requires at least ${closed ? 3 : 2} profile points`);
  }
  profile.forEach((point, index) => {
    if (!Array.isArray(point) || point.length !== 2 || !point.every(Number.isFinite)) {
      throw new Error(`profile_sweep profile[${index}] must contain two finite numbers`);
    }
  });

  const edgeCount = closed ? profile.length : profile.length - 1;
  const frames = path.map((_, index) => createPathFrame(path, index));
  const cumulative = [0];
  for (let i = 1; i < path.length; i++) {
    cumulative.push(cumulative[i - 1] + distance(path[i - 1], path[i]));
  }
  const totalLength = Math.max(cumulative[cumulative.length - 1], 1e-6);
  const profileDistances = [0];
  for (let i = 0; i < edgeCount; i++) {
    const a = profile[i], b = profile[(i + 1) % profile.length];
    profileDistances.push(profileDistances[i] + Math.hypot(b[0] - a[0], b[1] - a[1]));
  }

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
    const pathU0 = cumulative[pi] / (metricUVs ? 1 : totalLength);
    const pathU1 = cumulative[pi + 1] / (metricUVs ? 1 : totalLength);
    for (let pj = 0; pj < edgeCount; pj++) {
      const next = (pj + 1) % profile.length;
      const profileV0 = metricUVs ? profileDistances[pj] : pj / edgeCount;
      const profileV1 = metricUVs ? profileDistances[pj + 1] : (pj + 1) / edgeCount;
      const a = sweptPoint(pi, pj);
      const b = sweptPoint(pi + 1, pj);
      const c = sweptPoint(pi + 1, next);
      const d = sweptPoint(pi, next);
      pushTriangle(a, b, c, [pathU0, profileV0], [pathU1, profileV0], [pathU1, profileV1]);
      pushTriangle(a, c, d, [pathU0, profileV0], [pathU1, profileV1], [pathU0, profileV1]);
    }
  }

  if (capped) {
    const end = path.length - 1;
    const cap = triangulatePolygon(profile);
    for (let i = 0; i < cap.triangles.length; i += 3) {
      const ids = cap.triangles.slice(i, i + 3).map(index => profile.findIndex(p => p[0] === cap.points[index][0] && p[1] === cap.points[index][1]));
      const [a, b, c] = ids;
      pushTriangle(sweptPoint(0, a), sweptPoint(0, c), sweptPoint(0, b), profile[a], profile[c], profile[b]);
      pushTriangle(sweptPoint(end, a), sweptPoint(end, b), sweptPoint(end, c), profile[a], profile[b], profile[c]);
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

function assertFiniteVec3(value: Vec3, field: string): void {
  if (!Array.isArray(value) || value.length !== 3 || !value.every(Number.isFinite)) {
    throw new Error(`${field} must contain three finite numbers`);
  }
}

function clampInteger(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, Math.round(value)));
}
