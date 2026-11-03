import type { SolidParams, SolidProfile, Vec3, MeshData } from '../types';
import { triangulatePolygon } from './polygon';
import {
  add,
  sub,
  mul,
  dot,
  cross,
  length,
  unit,
  mix,
  rotateAxis,
  validateTriangles,
  trianglesToMeshes,
  type Tri
} from './solidMath';
type P2 = [number, number];
interface Profile {
  rings: P2[][];
  points: P2[];
  triangles: number[];
}
function positive(n: number | undefined, name: string): number {
  if (!Number.isFinite(n) || n! <= 0) throw Error(`${name} must be positive`);
  return n!;
}
function profile(p: SolidProfile | undefined): Profile {
  if (!p) throw Error('missing profile');
  const t = triangulatePolygon(p.outer, p.holes ?? []);
  // Preserve the user's first corresponding vertex when normalizing winding.
  const inputs = [p.outer, ...(p.holes ?? [])];
  const rings = t.rings.map((r, i) => {
    const first = inputs[i][0],
      j = r.findIndex(q => q[0] === first[0] && q[1] === first[1]);
    return [...r.slice(j), ...r.slice(0, j)] as P2[];
  });
  return triangulatePolygon(rings[0], rings.slice(1)) as Profile;
}
function match(a: Profile, b: Profile) {
  if (a.rings.length !== b.rings.length || a.rings.some((r, i) => r.length !== b.rings[i].length))
    throw Error('section topology/count/order must correspond');
}
function budget(layers: number, vertices: number) {
  if (layers * vertices * 2 > 24000) throw Error('solid tessellation budget exceeded (24000 triangles)');
}
function layered(layers: Vec3[][], a: Profile, b: Profile, closed = false): Tri[] {
  const out: Tri[] = [];
  const tri = (x: Vec3, y: Vec3, z: Vec3) => out.push([x, y, z]);
  for (let l = 0; l < layers.length - 1; l++) {
    let off = 0;
    for (const ring of a.rings) {
      for (let j = 0; j < ring.length; j++) {
        const k = off + j,
          n = off + ((j + 1) % ring.length),
          A = layers[l][k],
          B = layers[l][n],
          C = layers[l + 1][n],
          D = layers[l + 1][k];
        tri(A, D, C);
        tri(A, C, B);
      }
      off += ring.length;
    }
  }
  if (!closed)
    for (const [p, layer, reverse] of [
      [a, layers[0], false],
      [b, layers[layers.length - 1], true]
    ] as [Profile, Vec3[], boolean][]) {
      for (let i = 0; i < p.triangles.length; i += 3) {
        const [x, y, z] = p.triangles.slice(i, i + 3).map(k => layer[k]);
        tri(x, reverse ? z : y, reverse ? y : z);
      }
    }
  return out;
}
function transformed(p: Profile, y: number, offset: P2 = [0, 0], twist = 0): Vec3[] {
  const c = Math.cos(twist),
    s = Math.sin(twist);
  return p.points.map(([x, z]) => [x * c + z * s + offset[0], y, -x * s + z * c + offset[1]]);
}
function convex(points: P2[]) {
  let sign = 0;
  for (let i = 0; i < points.length; i++) {
    const a = points[i],
      b = points[(i + 1) % points.length],
      c = points[(i + 2) % points.length],
      v = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]);
    if (Math.abs(v) < 1e-10) continue;
    if (sign && Math.sign(v) !== sign) throw Error('pyramid base must be convex');
    sign = Math.sign(v);
  }
  // The local axis must originate inside the convex base.
  const signs = points
    .map((a, i) => {
      const b = points[(i + 1) % points.length];
      return Math.sign((b[0] - a[0]) * -a[1] - (b[1] - a[1]) * -a[0]);
    })
    .filter(x => x !== 0);
  if (signs.some(v => v !== signs[0])) throw Error('pyramid local origin must lie inside its base');
}
function shapeTriangles(s: SolidParams): Tri[] {
  if (s.kind === 'cone' || s.kind === 'pyramid') {
    const h = positive(s.height, 'height');
    let base: P2[];
    if (s.kind === 'cone') {
      const r = positive(s.radius, 'radius'),
        n = s.segments ?? 48;
      base = Array.from({ length: n }, (_, i) => [
        r * Math.cos((i * 2 * Math.PI) / n),
        r * Math.sin((i * 2 * Math.PI) / n)
      ]);
    } else {
      base = s.base!;
      convex(base);
    }
    const p = profile({ outer: base }),
      offset = s.apexOffset ?? [0, 0];
    budget(2, p.points.length);
    return layered([transformed(p, 0), p.points.map(() => [offset[0], h, offset[1]])], p, p);
  }
  if (s.kind === 'frustum') {
    const a = profile(s.bottom),
      b = profile(s.top),
      h = positive(s.height, 'height');
    match(a, b);
    budget(2, a.points.length);
    return layered([transformed(a, 0), transformed(b, h, s.topOffset)], a, b);
  }
  if (s.kind === 'wedge') {
    const w = positive(s.width, 'width'),
      d = positive(s.depth, 'depth'),
      [h0, h1] = s.endHeights!;
    if (h0 < 0 || h1 < 0 || h0 + h1 <= 0) throw Error('wedge must have positive volume');
    const p = profile({
      outer: [
        [-w / 2, -d / 2],
        [w / 2, -d / 2],
        [w / 2, d / 2],
        [-w / 2, d / 2]
      ]
    });
    return layered(
      [transformed(p, 0), p.points.map(([x, z]) => [x, h0 + ((z + d / 2) / d) * (h1 - h0), z])],
      p,
      p
    );
  }
  if (s.kind === 'extrude') {
    const p = profile(s.profile),
      v = s.vector!;
    if (Math.abs(v[1]) < 1e-12) throw Error('extrusion vector must leave profile plane');
    budget(2, p.points.length);
    const a = transformed(p, 0);
    return layered([a, a.map(q => add(q, v))], p, p);
  }
  if (s.kind === 'revolve') {
    const p = profile(s.section),
      angle = s.angle!,
      start = s.startAngle ?? 0,
      n = s.segments ?? 64,
      full = Math.abs(angle - Math.PI * 2) < 1e-10;
    if (p.points.some(([r]) => r < 0) || Math.max(...p.points.map(([r]) => r)) <= 0)
      throw Error('revolve radius must be nonnegative with positive radial extent');
    budget(n + 1, p.points.length);
    const layers = Array.from({ length: n + 1 }, (_, i) => {
      const a = start + (angle * i) / n;
      return p.points.map(([r, y]): Vec3 => [r * Math.cos(a), y, -r * Math.sin(a)]);
    });
    if (full) layers[n] = layers[0].map(p => [...p]);
    return layered(layers, p, p, full);
  }
  if (s.kind === 'loft') {
    const ss = s.sections!,
      pp = ss.map(v => profile(v.profile)),
      layers: Vec3[][] = [];
    for (let i = 1; i < ss.length; i++) {
      if (ss[i].height! <= ss[i - 1].height!) throw Error('loft heights must be strictly increasing');
      match(pp[0], pp[i]);
    }
    const n = s.segmentsPerSpan ?? 1;
    budget((ss.length - 1) * n + 1, pp[0].points.length);
    for (let i = 0; i < ss.length - 1; i++) {
      const a = transformed(pp[i], ss[i].height!, ss[i].offset, ss[i].twist),
        b = transformed(pp[i + 1], ss[i + 1].height!, ss[i + 1].offset, ss[i + 1].twist);
      for (let j = 0; j < n; j++) layers.push(a.map((p, k) => mix(p, b[k], j / n)));
      if (i === ss.length - 2) layers.push(b);
    }
    return layered(layers, pp[0], pp[pp.length - 1]);
  }
  if (s.kind === 'sweep') return sweep(s);
  throw Error('boolean solids require the blueprint dependency evaluator');
}
function sweep(s: SolidParams): Tri[] {
  const path = s.path!.map(p => [...p] as Vec3),
    closed = !!s.closedPath;
  if (closed) {
    if (path.length < 3 || length(sub(path[0], path[path.length - 1])) < 1e-9)
      throw Error('closed sweep needs 3 distinct path points without repeating first');
    path.push([...path[0]]);
  }
  const lengths = [0];
  for (let i = 1; i < path.length; i++) {
    const d = length(sub(path[i], path[i - 1]));
    if (d < 1e-9) throw Error('repeated sweep path point');
    lengths.push(lengths[i - 1] + d);
  }
  const total = lengths[lengths.length - 1],
    stations = lengths.map(x => x / total);
  for (let i = 1; i < path.length - 1; i++)
    if (dot(unit(sub(path[i], path[i - 1])), unit(sub(path[i + 1], path[i]))) < -0.999999)
      throw Error('sweep path reverses by 180 degrees');
  if (!!s.profile === !!s.sections) throw Error('sweep needs exactly one profile or section list');
  const ss = s.sections ?? [
      { t: 0, profile: s.profile! },
      { t: 1, profile: s.profile! }
    ],
    pp = ss.map(v => profile(v.profile));
  if (ss[0].t !== 0 || ss[ss.length - 1].t !== 1) throw Error('sweep sections must cover t=0..1');
  for (let i = 1; i < ss.length; i++) {
    if (ss[i].t! <= ss[i - 1].t!) throw Error('sweep section stations must increase');
    match(pp[0], pp[i]);
  }
  if (
    closed &&
    (JSON.stringify(pp[0].rings) !== JSON.stringify(pp[pp.length - 1].rings) ||
      Math.abs(Math.sin(((ss[ss.length - 1].twist ?? 0) - (ss[0].twist ?? 0)) / 2)) > 1e-8)
  )
    throw Error('closed sweep end profiles/twist must match');
  const tt = [...stations, ...ss.map(v => v.t!)]
    .sort((a, b) => a - b)
    .filter((v, i, a) => i === 0 || v - a[i - 1] > 1e-10);
  budget(tt.length, pp[0].points.length);
  const positions = tt.map(t => {
    let i = 0;
    while (i < stations.length - 2 && stations[i + 1] < t - 1e-12) i++;
    return mix(path[i], path[i + 1], (t - stations[i]) / (stations[i + 1] - stations[i]));
  });
  const tangents = positions.map((p, i) => {
    if (closed && (i === 0 || i === positions.length - 1))
      return unit(add(unit(sub(positions[1], p)), unit(sub(p, positions[positions.length - 2]))));
    if (i === 0) return unit(sub(positions[1], p));
    if (i === positions.length - 1) return unit(sub(p, positions[i - 1]));
    return unit(add(unit(sub(p, positions[i - 1])), unit(sub(positions[i + 1], p))));
  });
  const rights: Vec3[] = [],
    ups: Vec3[] = [];
  const ref: Vec3 = Math.abs(tangents[0][1]) < 0.95 ? [0, 1, 0] : [1, 0, 0];
  rights.push(unit(cross(ref, tangents[0])));
  for (let i = 1; i < tt.length; i++) {
    const axis = cross(tangents[i - 1], tangents[i]),
      n = length(axis);
    if (n < 1e-10) {
      if (dot(tangents[i - 1], tangents[i]) < 0) throw Error('sweep frame reversal');
      rights.push(rights[i - 1]);
    } else
      rights.push(
        rotateAxis(rights[i - 1], mul(axis, 1 / n), Math.atan2(n, dot(tangents[i - 1], tangents[i])))
      );
  }
  if (closed) {
    const end = rights.length - 1,
      correction = Math.atan2(dot(tangents[0], cross(rights[end], rights[0])), dot(rights[end], rights[0]));
    for (let i = 0; i < rights.length; i++)
      rights[i] = rotateAxis(rights[i], tangents[i], correction * tt[i]);
    rights[end] = [...rights[0]];
  }
  for (let i = 0; i < tt.length; i++) ups.push(unit(cross(tangents[i], rights[i])));
  const layers = tt.map((t, i) => {
    let j = 0;
    while (j < ss.length - 2 && ss[j + 1].t! < t - 1e-12) j++;
    const f = (t - ss[j].t!) / (ss[j + 1].t! - ss[j].t!),
      twist = (ss[j].twist ?? 0) * (1 - f) + (ss[j + 1].twist ?? 0) * f,
      U = rotateAxis(rights[i], tangents[i], twist),
      V = rotateAxis(ups[i], tangents[i], twist);
    return pp[j].points.map((p, k) => {
      const q = pp[j + 1].points[k],
        u = p[0] * (1 - f) + q[0] * f,
        v = p[1] * (1 - f) + q[1] * f;
      return add(positions[i], add(mul(U, u), mul(V, v)));
    });
  });
  if (closed) layers[layers.length - 1] = layers[0].map(p => [...p]);
  return layered(layers, pp[0], pp[pp.length - 1], closed);
}
export function buildSolid(s: SolidParams): MeshData[] {
  if (s.scale?.some(v => !Number.isFinite(v) || v <= 0)) throw Error('solid scale must be positive');
  const ts = validateTriangles(shapeTriangles(s));
  return trianglesToMeshes(ts, s.material, {
    position: s.position ?? [0, 0, 0],
    rotation: s.rotation ?? [0, 0, 0],
    scale: s.scale ?? [1, 1, 1]
  });
}
