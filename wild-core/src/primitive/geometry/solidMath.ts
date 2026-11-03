import type { Vec3, MeshData } from '../types';
export type Tri = [Vec3, Vec3, Vec3];
export const add = (a: Vec3, b: Vec3): Vec3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
export const sub = (a: Vec3, b: Vec3): Vec3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
export const mul = (a: Vec3, s: number): Vec3 => [a[0] * s, a[1] * s, a[2] * s];
export const dot = (a: Vec3, b: Vec3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
export const cross = (a: Vec3, b: Vec3): Vec3 => [
  a[1] * b[2] - a[2] * b[1],
  a[2] * b[0] - a[0] * b[2],
  a[0] * b[1] - a[1] * b[0]
];
export const length = (a: Vec3) => Math.hypot(...a);
export const unit = (a: Vec3): Vec3 => {
  const n = length(a);
  if (n < 1e-12) throw Error('degenerate direction');
  return mul(a, 1 / n);
};
export const mix = (a: Vec3, b: Vec3, t: number) => add(mul(a, 1 - t), mul(b, t));
export const rotateAxis = (p: Vec3, axis: Vec3, a: number): Vec3 =>
  add(
    add(mul(p, Math.cos(a)), mul(cross(axis, p), Math.sin(a))),
    mul(axis, dot(axis, p) * (1 - Math.cos(a)))
  );
export function transformPoint(p: Vec3, t: MeshData['transform']): Vec3 {
  const [x, y, z] = p.map((v, i) => v * t.scale[i]),
    [rx, ry, rz] = t.rotation,
    a = Math.cos(rx),
    b = Math.sin(rx),
    c = Math.cos(ry),
    d = Math.sin(ry),
    e = Math.cos(rz),
    f = Math.sin(rz);
  return add(
    [
      c * e * x - c * f * y + d * z,
      (b * d * e + a * f) * x + (-b * d * f + a * e) * y - b * c * z,
      (-a * d * e + b * f) * x + (a * d * f + b * e) * y + a * c * z
    ],
    t.position
  );
}
export function meshTriangles(meshes: MeshData[]): Tri[] {
  const out: Tri[] = [];
  for (const m of meshes) {
    const ids = m.indices ?? Uint32Array.from({ length: m.geometry.length / 3 }, (_, i) => i);
    for (let i = 0; i < ids.length; i += 3)
      out.push(
        [0, 1, 2].map(j =>
          transformPoint(
            Array.from(m.geometry.slice(ids[i + j] * 3, ids[i + j] * 3 + 3)) as Vec3,
            m.transform
          )
        ) as Tri
      );
  }
  return out;
}
export const signedVolume = (ts: Tri[]) => ts.reduce((s, [a, b, c]) => s + dot(a, cross(b, c)) / 6, 0);
function insideTri(p: Vec3, t: Tri, strict = false): boolean {
  const u = sub(t[1], t[0]),
    v = sub(t[2], t[0]),
    w = sub(p, t[0]);
  const a = dot(u, u),
    b = dot(u, v),
    c = dot(v, v),
    d = dot(w, u),
    e = dot(w, v),
    den = a * c - b * b;
  if (Math.abs(den) < 1e-20) return false;
  const x = (c * d - b * e) / den,
    y = (a * e - b * d) / den;
  const eps = strict ? 1e-8 : -1e-8;
  return x > eps && y > eps && x + y < 1 - eps;
}
export function pointOnTriangle(p: Vec3, t: Tri, eps: number): boolean {
  const n = cross(sub(t[1], t[0]), sub(t[2], t[0]));
  return Math.abs(dot(sub(p, t[0]), n)) <= eps * length(n) && insideTri(p, t);
}
function intersectTriangles(a: Tri, b: Tri, eps: number): boolean {
  const shared = a.filter(p => b.some(q => length(sub(p, q)) < eps)),
    na = cross(sub(a[1], a[0]), sub(a[2], a[0])),
    nb = cross(sub(b[1], b[0]), sub(b[2], b[0]));
  const atShared = (p: Vec3) => {
    if (shared.some(q => length(sub(p, q)) < eps * 4)) return true;
    if (shared.length === 2) {
      const d = sub(shared[1], shared[0]),
        w = sub(p, shared[0]),
        l = dot(d, d),
        t = dot(w, d) / l;
      return t >= -1e-8 && t <= 1 + 1e-8 && length(sub(w, mul(d, t))) < eps * 4;
    }
    return false;
  };
  if (
    length(cross(na, nb)) < 1e-9 * length(na) * length(nb) &&
    Math.abs(dot(na, sub(b[0], a[0]))) < eps * length(na)
  ) {
    if (
      insideTri(mul(add(add(a[0], a[1]), a[2]), 1 / 3), b, true) ||
      insideTri(mul(add(add(b[0], b[1]), b[2]), 1 / 3), a, true)
    )
      return true;
    const axis =
      Math.abs(na[0]) > Math.abs(na[1])
        ? Math.abs(na[0]) > Math.abs(na[2])
          ? 0
          : 2
        : Math.abs(na[1]) > Math.abs(na[2])
          ? 1
          : 2;
    const proj = (p: Vec3) => p.filter((_, i) => i !== axis),
      orient = (p: number[], q: number[], r: number[]) =>
        (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0]);
    for (let i = 0; i < 3; i++)
      for (let j = 0; j < 3; j++) {
        const p = proj(a[i]),
          q = proj(a[(i + 1) % 3]),
          r = proj(b[j]),
          s = proj(b[(j + 1) % 3]);
        if (orient(p, q, r) * orient(p, q, s) < -1e-16 && orient(r, s, p) * orient(r, s, q) < -1e-16)
          return true;
      }
    return false;
  }
  for (const [t, u, n] of [
    [a, b, nb],
    [b, a, na]
  ] as [Tri, Tri, Vec3][]) {
    for (let i = 0; i < 3; i++) {
      const p = t[i],
        q = t[(i + 1) % 3],
        d = sub(q, p),
        den = dot(n, d);
      if (Math.abs(den) < 1e-14) continue;
      const f = dot(n, sub(u[0], p)) / den;
      if (f < -1e-8 || f > 1 + 1e-8) continue;
      const hit = add(p, mul(d, f));
      if (!atShared(hit) && insideTri(hit, u)) return true;
    }
  }
  return false;
}
/** Closed edge topology plus nonadjacent triangle intersections; resource bounds are explicit. */
export function validateTriangles(input: Tri[], eps = 1e-7, selfCheck = true): Tri[] {
  if (input.length > 24000) throw Error('solid triangle budget exceeded (24000)');
  let ts = input.filter(t => length(cross(sub(t[1], t[0]), sub(t[2], t[0]))) > 1e-13);
  if (!ts.length) return [];
  if (ts.some(t => t.some(p => p.some(v => !Number.isFinite(v) || Math.abs(v) > 1e7))))
    throw Error('solid has non-finite or excessive coordinates');
  const key = (p: Vec3) => p.map(v => Math.round(v / eps)).join(','),
    edges = new Map<string, [number, number]>();
  for (const t of ts)
    for (let i = 0; i < 3; i++) {
      const a = key(t[i]),
        b = key(t[(i + 1) % 3]);
      if (a === b) throw Error('solid has a collapsed edge at tolerance');
      const k = a < b ? a + '/' + b : b + '/' + a;
      const v = edges.get(k) ?? [0, 0];
      v[0]++;
      v[1] += a < b ? 1 : -1;
      edges.set(k, v);
    }
  if ([...edges.values()].some(([n, b]) => n !== 2 || b !== 0))
    throw Error('solid is not a closed oriented 2-manifold');
  const volume = signedVolume(ts);
  if (Math.abs(volume) < 1e-12) throw Error('solid volume is zero');
  if (volume < 0) ts = ts.map(([a, b, c]) => [a, c, b]);
  if (selfCheck) {
    const boxes = ts
      .map((t, i) => ({
        i,
        min: [0, 1, 2].map(k => Math.min(...t.map(p => p[k]))),
        max: [0, 1, 2].map(k => Math.max(...t.map(p => p[k])))
      }))
      .sort((a, b) => a.min[0] - b.min[0]);
    let pairs = 0;
    for (let i = 0; i < boxes.length; i++)
      for (let j = i + 1; j < boxes.length && boxes[j].min[0] <= boxes[i].max[0] + eps; j++) {
        const a = boxes[i],
          b = boxes[j];
        if (
          a.max[1] < b.min[1] - eps ||
          b.max[1] < a.min[1] - eps ||
          a.max[2] < b.min[2] - eps ||
          b.max[2] < a.min[2] - eps
        )
          continue;
        if (++pairs > 3000000) throw Error('solid intersection-check budget exceeded');
        if (intersectTriangles(ts[a.i], ts[b.i], eps)) throw Error('solid has self-intersecting faces');
      }
  }
  return ts;
}
export function trianglesToMeshes(
  ts: Tri[],
  material = 'default',
  transform?: MeshData['transform']
): MeshData[] {
  const out: MeshData[] = [];
  for (let start = 0; start < ts.length; start += 12000) {
    const geometry: number[] = [],
      normals: number[] = [];
    for (const t of ts.slice(start, start + 12000)) {
      const n = unit(cross(sub(t[1], t[0]), sub(t[2], t[0])));
      for (const p of t) {
        geometry.push(...p);
        normals.push(...n);
      }
    }
    out.push({
      geometry: new Float32Array(geometry),
      indices: Uint32Array.from({ length: geometry.length / 3 }, (_, i) => i),
      normals: new Float32Array(normals),
      materialRef: material,
      transform: transform ?? { position: [0, 0, 0], rotation: [0, 0, 0], scale: [1, 1, 1] }
    });
  }
  return out;
}
