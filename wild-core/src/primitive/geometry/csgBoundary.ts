import type { Vec3 } from '../types';
import { add, sub, mul, dot, cross, length, type Tri } from './solidMath';
/** Weld numeric aliases and split every polygon edge at shared boundary vertices before triangulation. */
export function csgBoundaryTriangles(
  polygons: Array<{
    vertices: Vec3[];
  }>,
  epsilon: number
): Tri[] {
  const points: Vec3[] = [],
    cells = new Map<string, number[]>();
  function weld(p: Vec3): number {
    const c = p.map(v => Math.floor(v / epsilon));
    let best = -1,
      distance = epsilon;
    for (let x = -1; x <= 1; x++)
      for (let y = -1; y <= 1; y++)
        for (let z = -1; z <= 1; z++)
          for (const i of cells.get([c[0] + x, c[1] + y, c[2] + z].join(',')) ?? []) {
            const d = length(sub(p, points[i]));
            if (d <= distance) {
              best = i;
              distance = d;
            }
          }
    if (best >= 0) return best;
    const id = points.length;
    points.push([...p]);
    const key = c.join(',');
    const list = cells.get(key) ?? [];
    list.push(id);
    cells.set(key, list);
    return id;
  }
  const faces = polygons.map(p => [...new Set(p.vertices.map(weld))]).filter(v => v.length >= 3);
  if (faces.reduce((n, p) => n + p.length, 0) * points.length > 50000000)
    throw Error('CSG boundary repair budget exceeded');
  const out: Tri[] = [];
  for (const ids of faces) {
    const boundary: number[] = [];
    for (let i = 0; i < ids.length; i++) {
      const a = points[ids[i]],
        b = points[ids[(i + 1) % ids.length]],
        d = sub(b, a),
        l2 = dot(d, d),
        L = Math.sqrt(l2);
      if (L <= epsilon) continue;
      const cuts: Array<[number, number]> = [[0, ids[i]]];
      for (let k = 0; k < points.length; k++) {
        if (k === ids[i] || k === ids[(i + 1) % ids.length]) continue;
        const w = sub(points[k], a),
          t = dot(w, d) / l2;
        if (t <= epsilon / L || t >= 1 - epsilon / L) continue;
        if (length(sub(w, mul(d, t))) <= epsilon * 2) cuts.push([t, k]);
      }
      cuts.sort((a, b) => a[0] - b[0]);
      for (const [, k] of cuts) if (boundary[boundary.length - 1] !== k) boundary.push(k);
    }
    if (boundary.length < 3) continue;
    const center = mul(
      boundary.reduce((p, i) => add(p, points[i]), [0, 0, 0] as Vec3),
      1 / boundary.length
    );
    for (let i = 0; i < boundary.length; i++) {
      const a = points[boundary[i]],
        b = points[boundary[(i + 1) % boundary.length]];
      if (length(cross(sub(a, center), sub(b, center))) > 1e-13) out.push([center, a, b]);
    }
  }
  return out;
}
