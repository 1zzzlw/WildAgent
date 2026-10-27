import earcut, { deviation } from 'earcut';

type Point2 = [number, number];
const EPS = 1e-8;

/** Simple outer ring and disjoint interior holes. Coordinates and UVs stay in metres. */
export function triangulatePolygon(outer: Point2[], holes: Point2[][] = []) {
  const rings = [outer, ...holes].map((input, index) => {
    const ring = input.map(point => [...point] as Point2);
    if (ring.length > 1 && same(ring[0], ring[ring.length - 1])) ring.pop();
    if (ring.length < 3 || ring.some(p => p.length !== 2 || !p.every(Number.isFinite))) {
      throw new Error(`polygon ring ${index} needs at least three finite [x,z] points`);
    }
    for (let i = 0; i < ring.length; i++) {
      if (same(ring[i], ring[(i + 1) % ring.length])) throw new Error('polygon has a zero-length edge');
      for (let j = i + 1; j < ring.length; j++) {
        if (j === i + 1 || (i === 0 && j === ring.length - 1)) continue;
        if (intersects(ring[i], ring[(i + 1) % ring.length], ring[j], ring[(j + 1) % ring.length])) {
          throw new Error('polygon ring must not self-intersect');
        }
      }
    }
    const area = ring.reduce((sum, p, i) => {
      const q = ring[(i + 1) % ring.length];
      return sum + p[0] * q[1] - q[0] * p[1];
    }, 0);
    if (Math.abs(area) < EPS) throw new Error('polygon ring must have positive area');
    if ((area > 0) !== (index === 0)) ring.reverse();
    return ring;
  });
  for (let i = 1; i < rings.length; i++) {
    if (!inside(rings[i][0], rings[0])) throw new Error('polygon hole must be inside the outer ring');
    for (let j = 0; j < i; j++) {
      const a = rings[i], b = rings[j];
      for (let ai = 0; ai < a.length; ai++) for (let bi = 0; bi < b.length; bi++) {
        if (intersects(a[ai], a[(ai + 1) % a.length], b[bi], b[(bi + 1) % b.length])) {
          throw new Error('polygon rings must not cross or touch');
        }
      }
      if (j > 0 && (inside(a[0], b) || inside(b[0], a))) throw new Error('polygon holes must not overlap or nest');
    }
  }
  const points = rings.flat();
  const data = points.flat();
  let count = rings[0].length;
  const holeIndices = rings.slice(1).map(ring => { const start = count; count += ring.length; return start; });
  const triangles = earcut(data, holeIndices, 2);
  if (!triangles.length || deviation(data, holeIndices, 2, triangles) > 1e-6) {
    throw new Error('polygon triangulation failed to preserve its area');
  }
  return { rings, points, triangles };
}

function same(a: Point2, b: Point2): boolean {
  return Math.abs(a[0] - b[0]) < EPS && Math.abs(a[1] - b[1]) < EPS;
}

function cross(a: Point2, b: Point2, c: Point2): number {
  return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
}

function intersects(a: Point2, b: Point2, c: Point2, d: Point2): boolean {
  const on = (p: Point2, q: Point2, r: Point2) => Math.abs(cross(p, q, r)) < EPS
    && r[0] >= Math.min(p[0], q[0]) - EPS && r[0] <= Math.max(p[0], q[0]) + EPS
    && r[1] >= Math.min(p[1], q[1]) - EPS && r[1] <= Math.max(p[1], q[1]) + EPS;
  return (cross(a, b, c) * cross(a, b, d) < -EPS && cross(c, d, a) * cross(c, d, b) < -EPS)
    || on(a, b, c) || on(a, b, d) || on(c, d, a) || on(c, d, b);
}

function inside(p: Point2, ring: Point2[]): boolean {
  let result = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const a = ring[i], b = ring[j];
    if ((a[1] > p[1]) !== (b[1] > p[1]) && p[0] < (b[0] - a[0]) * (p[1] - a[1]) / (b[1] - a[1]) + a[0]) result = !result;
  }
  return result;
}
